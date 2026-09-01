"""The Elo model: the scale, the update step, and the two formulas (SPEC-phase1 3).

The whole model is a rating per team, one update rule and two formulas. Anything
more sophisticated is Phase 2 and has to beat this to justify existing.

**Three of these constants are now fitted rather than conventional**, which is
the change SPEC-phase1 12 was waiting on and SPEC-phase2 4 delivers.
``ELO_PER_POINT``, ``K`` and ``MOV_DENOMINATOR_FLOOR`` come from a grid search
over the 2015-2025 backfill; ``MOV_DAMPING``'s 2.2 is still conventional and says
so at its own definition. They stay pinned by ``tests/test_elo.py`` against
hand-worked cases, because a fitted constant is still a constant that should not
move without a visible diff.

**A constant is a property of a season, not of this module** (SPEC-phase2 4.1).
Refitting ``ELO_PER_POINT`` rescales every rating, so a state written at 20 and a
state written at 16 are not comparable and ``cfb elo replay`` would go red against
every object in ``elo/`` the moment the module moved. ``ModelConstants`` is what
each state document records about itself, ``constants_for`` says which set a season
runs under, and ``constants_of`` reads them back off a stored document. Replay
checks a document against the constants *it* was written under, never against
whatever this module currently holds.

``seed`` lives in ``cfb.elo.seed`` and is deliberately not re-exported here: it
reads ``ELO_PER_POINT`` from this module, and a re-export at the bottom of this
file would make the import order between the two load-bearing.

**Ratings are a plain ``dict[str, float]``.** A wrapper class would buy a type
name and cost every caller the ability to compare, copy and serialise a mapping
with the language's own operators -- which is exactly what ``cfb.replay`` does to
check a rebuild against a stored state, and what makes that check a two-line
equality rather than a method someone has to trust.
"""

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb.errors import EloDomainError, UnratedTeamError

__all__ = [
    "ELO_PER_POINT",
    "FITTED",
    "FIRST_FITTED_SEASON",
    "K",
    "ModelConstants",
    "PHASE_1",
    "constants_for",
    "constants_of",
    "MOV_DAMPING",
    "MOV_DENOMINATOR_FLOOR",
    "mov_denominator",
    "SCHEMA_VERSION",
    "EloState",
    "Game",
    "Prediction",
    "Ratings",
    "predict",
    "state_key",
    "state_prefix",
    "update",
    "win_probability",
]

#: SPEC-phase1 3.1, refitted by SPEC-phase2 4.2. One constant converts both ways:
#: it turns a Sagarin rating difference into Elo when seeding, and an Elo gap back
#: into a predicted margin.
#:
#: **16.0, and it is the first value here that was measured rather than argued.**
#: The history is worth keeping because both previous values were reasoned to. It
#: was 28 on an inference that ran backwards, then 20 on the observation that
#: college margins scatter with a standard deviation of 14 to 16 -- correct, and
#: still an argument from a reference curve rather than from this sport's games.
#: SPEC-phase2 4.2's grid search over 2015-2025 minimising mean absolute error of
#: predicted margin lands at 16.0, which sits at the wide end of that same range.
#: The earlier reasoning was pointing the right way and stopped short.
#:
#: **The fit is not contaminated by the seeding difference it might have been.**
#: SPEC-phase2 4.4 flags that the constants are fitted on a model seeded from a
#: uniform 1500 while the live model is seeded from Sagarin, and singles this
#: constant out as the one the backfill measures cleanly for both -- because
#: SPEC-phase1 3.2 proves it cancels between ``seed()`` and ``predict()``. The
#: sensitivity fit excluding weeks 1-3 returned 16.0 as well, which is the
#: diagnostic 4.4 asks for: had September contamination mattered, this is the
#: constant that would have moved between the two fits.
#:
#: **Only the ratio to ``_LOGISTIC_DIVISOR`` matters.** ``(16, 400)`` and
#: ``(8, 200)`` are the same model. Anyone adjusting one is adjusting the other's
#: meaning.
#:
#: SPEC-phase2 4.3 replaces SPEC-phase1 3.1's reference-curve table with measured
#: win rates, and ``test_the_spec_4_3_measured_table`` pins them -- so changing
#: this invalidates a measurement loudly rather than a hypothesis quietly.
ELO_PER_POINT = 16.0

#: SPEC-phase1 3.4, refitted by SPEC-phase2 4.2.
#:
#: **Coupled to ``ELO_PER_POINT``, and the coupling is easy to miss.** What K
#: controls is Elo movement, but what anyone reasoning about the model cares
#: about is *points of predicted margin* moved per game, which is
#: ``K / ELO_PER_POINT``. At 30 over 16 that is 1.875 points, against 1.0 at the
#: previous pair -- so the refit made the model substantially more responsive per
#: game, and it did so as a decision this time rather than as a side effect of
#: rescaling something else.
#:
#: **This is the constant SPEC-phase2 4.4 warns about, and the warning survives
#: the fit.** K is fitted on a model seeded from a uniform 1500, which has more to
#: learn each September than the Sagarin-seeded live model ever does, biasing it
#: upward. 4.4's tie-break asks for the sensitivity fit that excludes weeks 1-3
#: when the two disagree by more than 0.25 held-out MAE. They did not disagree at
#: all -- both fits returned K=30.0 -- so the primary fit ships and the bias 4.4
#: describes is bounded by that agreement rather than by assertion.
#:
#: The residual caveat is 4.4's own and is not resolved by the fit: K does not
#: enter a week-1 prediction at all, its influence is largest across weeks 2-4,
#: and the sensitivity fit sees only the last of those. 2026 is the live test.
K = 30.0

#: The margin-of-victory damping constant (SPEC-phase1 3.4). Without the term it
#: sits in, a strong team running up the score on a weak one gains more than the
#: result warrants and the top of the table inflates.
MOV_DAMPING = 2.2

#: The floor under that term's denominator (SPEC-phase1 3.4), refitted by
#: SPEC-phase2 4.2.
#:
#: The denominator is ``elo_diff_winner * 0.001 + 2.2`` and ``elo_diff_winner`` is
#: signed, so a large enough upset drives it toward zero and then through it. Past
#: zero the multiplier inverts and **a bigger win lowers the winner's rating** --
#: the model silently running backwards on the most informative result of the
#: season. The floor makes that arithmetically impossible.
#:
#: **0.05 rather than 0.25, and the guard is doing less work than it looks.** The
#: floor was never the interesting number; the raise standing in front of it is.
#: ``update`` refuses a game whose *unclamped* denominator is under the floor, so
#: lowering the floor does not admit enormous updates -- it narrows the band in
#: which the run raises instead of proceeding. What the fit found is that the
#: quarter-point floor was rejecting legitimate results: real upsets that belong
#: in the training signal, on a scale where the seed now spans a narrower range.
#:
#: At 0.05 the multiplier's ceiling is 44 and a ten-point win could move a rating
#: by up to 3165 Elo -- which sounds alarming and is exactly why the raise, not
#: the clamp, is the guard. No call to ``update`` divides by a clamped value; the
#: ceiling describes an update the code refuses to perform.
#:
#: **Reachability changed with the scale.** At ``ELO_PER_POINT`` 20 the 2026 seed
#: spanned 579 to 2204 and no pairing reached the old floor. At 16 the seed spans
#: 763 to 2063, a narrower spread, and the widest gap leaves the denominator at
#: 0.90 -- comfortably clear of 0.05. As with the previous rescale this is a side
#: effect rather than a decision about the floor, and ``mov_denominator`` stays
#: public and directly exercised precisely because the guard does not fire from
#: the seed.
MOV_DENOMINATOR_FLOOR = 0.05

#: The divisor of the standard Elo logistic. Textbook, and unchanged.
_LOGISTIC_DIVISOR = 400

#: SPEC-phase1 6.2's envelope version, for the stored state document below.
#:
#: **2 since SPEC-phase2 4.1.** ``EloState`` gained a ``model`` block, and this is
#: the case 6.2 reserves a bump for: a field whose meaning changed. A state that
#: does not say which scale it was written on meant one thing when only one scale
#: had ever existed and means something much weaker now. The site contract
#: (``PUBLISHED_SCHEMA_VERSION``) is untouched -- no published document gains,
#: loses or renames a field.
SCHEMA_VERSION = 2

#: A canonical team id to its Elo rating. See the module docstring for why this
#: is a type alias and not a class.
Ratings = dict[str, float]

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


class ModelConstants(BaseModel):
    """The constants one set of ratings was produced under (SPEC-phase2 4.1).

    **This exists so that a rating can be read.** ``ELO_PER_POINT`` is a scale, and
    a number on an unnamed scale is not a measurement. Before this block a state
    document recorded 2204 for Ohio State and there was exactly one scale in the
    world, so the omission cost nothing; the moment a second scale exists the same
    file means 2204-at-20 or 2204-at-16 and nothing in it can say which.

    Carried on the document rather than looked up by season, even though
    ``constants_for`` can answer for every season this project has run. A lookup
    table is the current opinion about the past and can be edited; the document is
    what was actually used, and ``replay`` needs the second one. That is the whole
    difference between reproducing a state and asserting one.
    """

    model_config = _STRICT

    elo_per_point: float = Field(gt=0)
    k: float = Field(gt=0)
    mov_damping: float = Field(gt=0)
    mov_denominator_floor: float = Field(gt=0)
    #: ``None`` on a live season, and that is not a missing value. The live model
    #: reseeds from Sagarin's preseason page every year and never carries a season
    #: forward (SPEC-phase1 3.2), so the fitted carry-forward coefficient has no
    #: live counterpart at all -- SPEC-phase2 4.4 says so in as many words. A
    #: number here would describe an operation the live pipeline does not perform.
    regression_to_mean: float | None = None
    #: ``None`` on a live season, where HFA is read per-run from the Sagarin
    #: manifest (SPEC-phase1 3.3) and therefore is not a constant of the season.
    #: A fitted scalar only on a backfilled season, which has no Sagarin page.
    hfa: float | None = None
    #: Where the HFA came from: ``"sagarin"`` on a live season, ``"fitted"`` on a
    #: backfilled one. Named rather than inferred from ``hfa`` being null, because
    #: "read per-run from a manifest" and "nobody recorded it" are different facts
    #: and only one of them is fine.
    hfa_source: str = Field(min_length=1)


#: The Phase 1 constants, and what ``constants_of`` reports for a state written
#: before SPEC-phase2 4.1 gave documents a ``model`` block.
#:
#: **It is the best available answer for such a state, not a certain one, and the
#: difference is worth stating.** A ``schema_version`` 1 document records no
#: scale, so nothing in it can be interrogated; this is an assumption about when
#: it was written. The assumption is already known to be wrong for at least one
#: real object: ``elo/season=2026/week=preseason/2026-08-28T223403Z.json`` was
#: written at ``ELO_PER_POINT`` 28, before SPEC-phase1 3.1's rescale to 20, and
#: reports as ``PHASE_1`` here. That is the cost of the field not having existed.
#:
#: Nothing reads it wrongly today, and the reason is structural rather than lucky.
#: ``newest_state_key`` and ``previous_state`` both select the newest state for a
#: week, so a superseded document is never the target of a verify and never the
#: base of a prediction. If one ever were, ``verify`` refuses the comparison and
#: names both scales rather than reporting a rescale as 266 rating drifts -- which
#: is the whole reason that guard is a separate check ahead of the ratings.
#:
#: The lesson is the one 4.1 draws: a rating on an unnamed scale cannot be read,
#: and no amount of care afterwards recovers what the document did not record.
PHASE_1 = ModelConstants(
    elo_per_point=20.0,
    k=20.0,
    mov_damping=2.2,
    mov_denominator_floor=0.25,
    hfa_source="sagarin",
)

#: SPEC-phase2 4.2's fitted set, and what this module currently holds.
#:
#: Built from the module constants rather than repeating their values, so the two
#: cannot drift into disagreeing about what "current" means.
FITTED = ModelConstants(
    elo_per_point=ELO_PER_POINT,
    k=K,
    mov_damping=MOV_DAMPING,
    mov_denominator_floor=MOV_DENOMINATOR_FLOOR,
    hfa_source="sagarin",
)

#: The first live season run on the fitted constants (SPEC-phase2 4.2).
#:
#: **2026, and it is a boundary the refit reached two days late.** SPEC-phase2 4.1
#: freezes constants within a season and lands a refit between seasons, because a
#: record accumulating on one scale must not be republished on another halfway
#: through. The fit completed on 2026-08-31, after the season's first Saturday.
#:
#: It applies to 2026 anyway, and the reason is that the harm 4.1 names had barely
#: begun. At the switch nothing had been scored -- ``scored/`` was empty and
#: ``accuracy.json`` read ``games: 0`` -- and no week had been advanced, so ``K``
#: and ``MOV_DENOMINATOR_FLOOR`` had never touched a stored rating. Week 2 was
#: still ahead of its kickoffs and is regenerated on the new constants before it.
#:
#: **What it does cost, stated rather than buried: week 1's Brier.** Week 1's 144
#: forecasts are logged at 20 and cannot be reforecast -- the games are played and
#: the log is append-only. SPEC-phase1 3.2 proves ``ELO_PER_POINT`` cancels
#: between ``seed()`` and ``predict()``, so their *margins* are exactly what the
#: refit would have produced and the season's MAE is untouched. Win probability is
#: not a margin: it is the logistic of one *times this constant*, so those 144
#: probabilities sit ~3.2 points from where 16 would have put them (max 5.0). The
#: 2026 Brier therefore blends one week at 20 with the rest at 16, and it is a
#: blend of two weeks' worth of nothing if the season is instead run entire on
#: constants the backfill says are worse.
#:
#: 3.2 records the same manoeuvre being made once before, when the scale went 28
#: to 20 in-season -- and the week 2 log still carried ``elo_per_point: 28`` when
#: this landed, so the 2026 log already spanned two scales before it spanned three.
FIRST_FITTED_SEASON = 2026


def constants_for(season: int) -> ModelConstants:
    """Which constants ``season`` runs under (SPEC-phase2 4.1).

    Frozen within a season by construction: this is a function of the season and
    of nothing else -- not of the current week, not of when it is called.
    """
    return FITTED if season >= FIRST_FITTED_SEASON else PHASE_1


class Game(BaseModel):
    """One game, as the model sees it.

    Canonical ids, never vendor names (SPEC-phase1 4.2) -- ``cfbd_game_id`` is the
    single exception, and it is here because SPEC-phase1 5.1 makes it the join key
    for matching a result to the prediction that anticipated it.

    ``home_points`` and ``away_points`` are nullable because an unplayed game is a
    legal ``Game``: ``predict`` is handed one before kickoff. ``update`` is not,
    and refuses a game with no result rather than reading a null as a zero.

    ``kickoff`` is optional because nothing in ``update`` or ``predict`` reads it
    -- the arithmetic is a function of ratings, points and site. It is on the
    model because ordering is the one property of a season that Elo cannot
    recover on its own, and ``cfb.replay`` refuses a game without one.
    """

    model_config = _STRICT

    cfbd_game_id: int
    home: str = Field(min_length=1)
    away: str = Field(min_length=1)
    home_points: int | None = None
    away_points: int | None = None
    #: SPEC-phase1 4.2: at a neutral site "home" is whatever CFBD says, which
    #: makes the designation arbitrary. Nothing here awards an advantage to it.
    neutral_site: bool = False
    kickoff: datetime | None = None

    @property
    def is_complete(self) -> bool:
        """Whether both scores are present.

        One score present and the other missing is not this: that is a malformed
        row rather than an unplayed game, and ``update`` raises on it.
        """
        return self.home_points is not None and self.away_points is not None


class Prediction(BaseModel):
    """What the model says about one game, always from the **home** perspective.

    One convention, stated once, including at neutral sites -- so nothing
    downstream carries sign-flipping logic (SPEC-phase1 4.2).

    ``win_probability`` is unclamped. SPEC-phase1 3.7's ``[0.001, 0.999]`` clamp
    is presentational and applied at publish time; the stored prediction keeps
    what the model actually said, because the Brier scores of SPEC-phase1 5.3 are
    computed on that.
    """

    model_config = _STRICT

    predicted_margin: float
    win_probability: float


class EloState(BaseModel):
    """The stored state document (SPEC-phase1 3.5).

    ``elo/season=2026/week=04/2026-09-14T120500Z.json``, write-once and
    timestamped like everything else. It exists to give the write-up a visible
    ratings history and to make a run cheap, **not because the pipeline depends
    on it** -- ``cfb.replay`` rebuilds the same numbers from ``raw/`` alone, and
    ``cfb elo replay`` fails the run when the two disagree.

    ``extra="forbid"`` for the same reason ``Manifest`` forbids: ``schema_version``
    is how this document grows a field, and an unrecognised key means the writer
    and the reader disagree about the schema. A state object that is quietly half
    understood is worse than one that will not load.
    """

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    season: int = Field(ge=1869)
    #: The partition this state is the end of: ``"01"``-``"15"``, ``"preseason"``
    #: before any game has been applied, or ``"postseason"``.
    week: str = Field(min_length=1)
    generated_at: datetime
    #: The ``raw/sagarin/`` key the season was seeded from. A state that cannot
    #: name its own seed cannot be rebuilt, which is the whole claim of §3.5.
    seeded_from: str = Field(min_length=1)
    #: How many completed games are folded into ``ratings``. Not decoration: a
    #: replay that agrees on every rating but not on this has applied something
    #: twice in a way that cancelled out, which no rating comparison would show.
    games_applied: int = Field(ge=0)
    #: The earliest kickoff this state folded, when the season's opening games
    #: could not be priced and were left out. ``None`` when the accumulation
    #: covers the season entire, which is every ordinary season.
    #:
    #: **The same idea as ``PredictionLog.forecast_from`` (§4.4), on the scoring
    #: side, and deliberately the same shape of name.** A forecast cannot cover a
    #: game that has already kicked off; an accumulation cannot cover a game that
    #: kicked off before any Sagarin page carrying an HFA had been captured. Two
    #: names for one concept is how the next reader concludes they are different
    #: things.
    #:
    #: **Derived on every run, never written down as a date.** ``replay`` computes
    #: it from the manifests in ``raw/`` the same way each time, so it is a
    #: restatement of the evidence rather than a second source of truth -- which
    #: §3.5's "state is a cache" argument depends on there not being one.
    #:
    #: It is compared by ``verify``: a replay and an advance that disagree about
    #: which games they folded is exactly what §11 step 5 exists to catch, and it
    #: cannot catch it if neither says what it folded.
    folded_from: datetime | None = None

    #: The kickoff of the last game folded in, or ``None`` when none has been.
    #:
    #: This is what makes the state say *when* it is as of, and it is load-bearing
    #: rather than descriptive: ``cfb.replay.advance`` uses it to select the games
    #: it has not already applied. Without it an incremental chain has no way to
    #: know where it stopped, and a game postponed out of an already-written week
    #: is either skipped forever or applied in the wrong order -- both of which put
    #: the chain permanently out of step with a rebuild.
    through_kickoff: datetime | None = None
    #: The constants these ratings were produced under (SPEC-phase2 4.1).
    #:
    #: ``None`` only on a ``schema_version`` 1 document, which predates the block
    #: entirely. Read it through ``constants_of`` rather than directly: the null
    #: has a specific meaning -- ``PHASE_1`` -- and a caller that reads the field
    #: raw is one ``or`` away from silently replaying a 20-scale state at 16.
    model: ModelConstants | None = None
    ratings: Ratings

    @model_validator(mode="after")
    def the_block_matches_the_version(self) -> "EloState":
        """A schema 2 document carries its constants; a schema 1 document cannot.

        Both directions, because both are a writer and a reader disagreeing about
        the schema. A version 2 state without the block is the document SPEC-phase2
        4.1 exists to abolish, and it would read back as ``PHASE_1`` -- silently
        claiming a scale it may never have been written on. A version 1 state
        *with* one is a document some other writer produced under this project's
        name, and guessing which half to believe is not this model's job.
        """
        if self.schema_version >= 2 and self.model is None:
            raise ValueError(
                f"schema_version {self.schema_version} state for season {self.season} "
                f"week {self.week!r} carries no model block. Since SPEC-phase2 4.1 a state "
                f"records the constants it was written under, and one that does not cannot "
                f"be replayed: its ratings are on an unnamed scale"
            )
        if self.schema_version < 2 and self.model is not None:
            raise ValueError(
                f"schema_version {self.schema_version} state for season {self.season} "
                f"week {self.week!r} carries a model block, which that version has no field "
                f"for. The version and the document disagree about the schema"
            )
        return self


def constants_of(state: EloState) -> ModelConstants:
    """The constants ``state`` was written under (SPEC-phase2 4.1).

    The one supported way to read ``EloState.model``. A ``schema_version`` 1
    document has no block and resolves to ``PHASE_1``, which is a fact about when
    it was written rather than a default -- see ``PHASE_1``.

    **Never falls back to the current module constants.** That is the single
    mistake this function exists to make unavailable: it would make every stored
    state agree with every future refit by definition, and turn SPEC-phase1 11
    step 5 from a check into a tautology.
    """
    return state.model or PHASE_1


#: Second resolution and no colons, matching ``cfb.manifest``: the stamp is a
#: literal path segment, and colons make an object miserable to handle from the
#: shell that SPEC-phase1 11's verification commands run in.
_STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"

_NAMED_WEEKS = frozenset({"preseason", "postseason"})


def _check_week(week: str) -> str:
    if week in _NAMED_WEEKS:
        return week
    if len(week) == 2 and week.isdigit() and 1 <= int(week) <= 15:
        return week
    raise ValueError(
        f"week {week!r} is not a legal partition value: expected '01'-'15' zero-padded "
        f"or one of {sorted(_NAMED_WEEKS)}"
    )


def state_prefix(*, season: int, week: str) -> str:
    """Everything stored for one season-week.

    The stamp inside is fixed-width and zero-padded, so keys under one prefix sort
    lexicographically into the order they were written. ``cfb.replay`` relies on
    that to find the newest state without reading every object under it.
    """
    return f"elo/season={season}/week={_check_week(week)}/"


def state_key(*, season: int, week: str, generated_at: datetime) -> str:
    """The key for one stored state object (SPEC-phase1 3.5)."""
    return f"{state_prefix(season=season, week=week)}{generated_at.strftime(_STAMP_FORMAT)}.json"


def win_probability(predicted_margin: float, *, constants: ModelConstants = FITTED) -> float:
    """The home team's win probability for a predicted margin (SPEC-phase1 3.1).

    Derived from the margin rather than computed alongside it, and that is the
    point. The PRD requires that the two numbers cannot disagree, and the only way
    to state that as an identity rather than a hope is to make one a function of
    the other. A refactor that computed them from separate quantities would break
    ``test_margin_and_probability_cannot_disagree`` and nothing else.
    """
    return 1 / (1 + 10 ** (-(predicted_margin * constants.elo_per_point) / _LOGISTIC_DIVISOR))


def predict(
    ratings: Ratings, game: Game, *, hfa: float, constants: ModelConstants = FITTED
) -> Prediction:
    """The model's forecast for one game, from the home team's perspective.

    ``hfa`` is a keyword because it belongs to the Sagarin snapshot the run read
    (SPEC-phase1 3.3) rather than to the game. Putting it on ``Game`` would hang a
    per-run value off a per-fixture object, and the first thing to serialise a
    ``Game`` would carry it into a document with no business asserting it.
    """
    gap = _rating(ratings, game.home, game) - _rating(ratings, game.away, game)
    margin = gap / constants.elo_per_point + _home_edge(game, hfa)
    return Prediction(
        predicted_margin=margin,
        win_probability=win_probability(margin, constants=constants),
    )


def update(
    ratings: Ratings, game: Game, *, hfa: float, constants: ModelConstants = FITTED
) -> Ratings:
    """Apply one completed game. Returns new ratings; ``ratings`` is untouched.

    Standard Elo with the margin-of-victory multiplier of SPEC-phase1 3.4::

        expected  = 1 / (1 + 10 ** (-(elo_home + hfa*ELO_PER_POINT - elo_away) / 400))
        actual    = 1.0 if home won else 0.0
        mov_mult  = ln(|margin| + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))
        elo_home += K * mov_mult * (actual - expected)
        elo_away -= K * mov_mult * (actual - expected)

    **``elo_diff_winner`` is signed: the winner's rating minus the loser's.**
    Positive when the favourite won, negative when the underdog did. Signed, an
    upset shrinks the denominator below 2.2 and moves ratings further.

    The reason is informational. An upset is a low-probability event, a
    low-probability event carries more information than a likely one, and a
    result the model did not expect should change it more than a result it did.
    That argument is about the *loser* of the expectation, so it settles the upset
    case directly.

    The autocorrelation reading does not. Damping exists so a strong team running
    up the score on a weak one cannot farm rating off it -- a statement about what
    the term does for favourites, which leaves the underdog direction unspecified
    rather than decided. Read as an absolute value the term would damp both
    identically, which would mean Massachusetts beating Ohio State by 20 taught
    the model exactly as much as the reverse. ``test_an_upset_uses_the_signed_gap``
    fails under that reading.

    **Returning rather than mutating** is the project's frozen-evidence idiom
    applied to the one thing here that is not frozen. A rating is what the model
    believed at a moment; a function that edited in place would make the
    before-state unrecoverable, and a replay folding over a season would have no
    way to stop part-way and compare.
    """
    if not game.is_complete:
        raise EloDomainError(
            f"game {game.cfbd_game_id} ({game.away} at {game.home}) has "
            f"home_points={game.home_points} away_points={game.away_points}; the update step "
            f"applies completed games only (SPEC-phase1 3.4) and a null score is not a zero"
        )

    home = _rating(ratings, game.home, game)
    away = _rating(ratings, game.away, game)

    diff = home + _home_edge(game, hfa) * constants.elo_per_point - away
    expected = 1 / (1 + 10 ** (-diff / _LOGISTIC_DIVISOR))

    margin = game.home_points - game.away_points
    if margin == 0:
        # College football has decided games in overtime since 1996, so a tie is
        # not a result -- it is a cancelled or unplayed game recorded as 0-0.
        # §3.4's `actual = 1.0 if home won else 0.0` has no value for one and
        # would score it silently as an away win. SPEC-phase1 12 owns the
        # cancellation signal this is waiting on.
        raise EloDomainError(
            f"game {game.cfbd_game_id} ({game.away} at {game.home}) is recorded as a "
            f"{game.home_points}-{game.away_points} tie. SPEC-phase1 3.4 defines no outcome "
            f"for one, and reading it as an away win is the silent coercion this project "
            f"exists to prevent"
        )

    actual = 1.0 if margin > 0 else 0.0
    signed = diff if margin > 0 else -diff

    # Clamped first, so the arithmetic below cannot invert whatever reaches it, and
    # only then checked, so a clamped update never happens quietly. The two are
    # deliberately both here and the order is the point: the clamp is what keeps a
    # rating from running backwards, and the raise is what keeps anyone from
    # finding out months later that it nearly did. Same defence-in-depth shape as
    # the model validators of SPEC-phase0 4.7 -- if a later phase decides a clamped
    # update is acceptable and drops the raise, what is left is still correct
    # arithmetic rather than a silent sign flip.
    unclamped = _raw_mov_denominator(signed, constants=constants)
    denominator = mov_denominator(signed, constants=constants)
    if unclamped < constants.mov_denominator_floor:
        clamped_move = (
            constants.k
            * math.log(abs(margin) + 1)
            * (constants.mov_damping / constants.mov_denominator_floor)
        )
        raise EloDomainError(
            f"game {game.cfbd_game_id} ({game.away} at {game.home}) was won from "
            f"{-signed:.0f} Elo of disadvantage, putting SPEC-phase1 3.4's multiplier "
            f"denominator at {unclamped:.4f}, under the {constants.mov_denominator_floor} "
            f"floor. Clamped it would still move a rating by up to {clamped_move:.0f} "
            f"Elo from one result; unclamped and below zero it would move it the wrong "
            f"way. Either the ratings have diverged or the scale needs refitting "
            f"(SPEC-phase1 12) -- neither is something to apply a game through"
        )

    mov_mult = math.log(abs(margin) + 1) * (constants.mov_damping / denominator)
    delta = constants.k * mov_mult * (actual - expected)

    # Zero-sum by construction. Elo that leaks or creates rating drifts the whole
    # scale, and the drift is invisible in any single game.
    return {**ratings, game.home: home + delta, game.away: away - delta}


def _raw_mov_denominator(
    elo_diff_winner: float, *, constants: ModelConstants = FITTED
) -> float:
    """SPEC-phase1 3.4's denominator exactly as written, floor and all removed.

    Split out so the formula appears once. ``update`` needs both this and the
    floored value -- one to decide whether to raise, one to divide by -- and two
    copies of an expression that must agree is how they stop agreeing.
    """
    return elo_diff_winner * 0.001 + constants.mov_damping


def mov_denominator(
    elo_diff_winner: float, *, constants: ModelConstants = FITTED
) -> float:
    """The same denominator, floored (SPEC-phase1 3.4). Never inverts the multiplier.

    Public and separately tested because it is the half of the guard that
    ``update`` cannot demonstrate. The raise stands in front of the clamp, so no
    call to ``update`` ever divides by a clamped value -- which means a test that
    only went through ``update`` would pass with the clamp deleted, and the
    defence-in-depth §3.4 claims would be a comment rather than a property.

    Deleting the clamp fails ``test_the_clamp_holds_on_its_own``.
    """
    return max(
        _raw_mov_denominator(elo_diff_winner, constants=constants),
        constants.mov_denominator_floor,
    )


def _home_edge(game: Game, hfa: float) -> float:
    """The home advantage in points, which a neutral site does not get.

    SPEC-phase1 3.4, and it applies to ``predict`` and ``update`` alike. §4.2 makes
    the home designation at a neutral site "whatever CFBD says" -- arbitrary -- so
    an edge awarded on it is not a small error in one direction. It is noise in
    both, worth ~2.4 points either way depending on which side the vendor happened
    to list first, in the games most likely to decide a playoff.

    One function rather than a term in each formula, so the prediction and the
    result are scored against the same idea of the game.
    """
    return 0.0 if game.neutral_site else hfa


def _rating(ratings: Ratings, canonical: str, game: Game) -> float:
    """One team's rating, or a red run.

    Never a default. A missing rating means the seed did not cover this team, and
    1500 would silently rate it exactly average for the rest of the season -- the
    same class of failure as an unmapped name, and just as invisible.
    """
    try:
        return ratings[canonical]
    except KeyError:
        raise UnratedTeamError(
            f"no rating for {canonical!r}, named by game {game.cfbd_game_id} "
            f"({game.away} at {game.home}). The seed covers every team on the Sagarin page "
            f"(SPEC-phase1 3.2); a canonical id it does not hold means the seed and this "
            f"game resolved against different crosswalks"
        ) from None
