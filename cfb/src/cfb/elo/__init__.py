"""The Elo model: the scale, the update step, and the two formulas (SPEC-phase1 3).

The whole model is a rating per team, one update rule and two formulas. Anything
more sophisticated is Phase 2 and has to beat this to justify existing.

**Every constant here is conventional rather than fitted**, and SPEC-phase1 12
says so plainly: ``ELO_PER_POINT``, ``K`` and the multiplier's ``2.2`` have no
source outside the decision to use them. They are pinned by ``tests/test_elo.py``
against hand-worked cases so that changing one is a deliberate act with a visible
diff rather than a tuning session.

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

from pydantic import BaseModel, ConfigDict, Field

from cfb.errors import EloDomainError, UnratedTeamError

__all__ = [
    "ELO_PER_POINT",
    "K",
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

#: SPEC-phase1 3.1. One constant converts both ways: it turns a Sagarin rating
#: difference into Elo when seeding, and an Elo gap back into a predicted margin.
#:
#: 28 rather than the conventional 25 because college margins are far wider than
#: the NFL ones the 25 figure came from. It is a number with no source outside
#: that decision, and ``test_the_spec_3_1_calibration_table`` pins the win
#: probabilities it produces so that changing it invalidates the spec's argument
#: loudly rather than quietly.
ELO_PER_POINT = 28

#: SPEC-phase1 3.4. Conventional, not fitted.
K = 20

#: The margin-of-victory damping constant (SPEC-phase1 3.4). Without the term it
#: sits in, a strong team running up the score on a weak one gains more than the
#: result warrants and the top of the table inflates.
MOV_DAMPING = 2.2

#: The floor under that term's denominator (SPEC-phase1 3.4).
#:
#: The denominator is ``elo_diff_winner * 0.001 + 2.2`` and ``elo_diff_winner`` is
#: signed, so a large enough upset drives it toward zero and then through it. Past
#: zero the multiplier inverts and **a bigger win lowers the winner's rating** --
#: the model silently running backwards on the most informative result of the
#: season. The floor makes that arithmetically impossible.
#:
#: 0.25 rather than something just above zero, because the interesting boundary is
#: not the sign flip but the size of the swing. At 0.25 the multiplier is 8.8 and a
#: ten-point win moves a rating by up to 422 Elo -- 15 points of Sagarin rating from
#: one game, on a scale whose whole FBS spread is 67. A single result worth that
#: much is not a rating update, it is a reseed.
#:
#: **This is reachable on the current scale, not only after a Phase 2 refit.** The
#: 2026 preseason seed spans 211 to 2486, so 39 of the top team's possible
#: opponents would cross this floor by beating it and 5 would carry the
#: denominator negative. SPEC-phase1 12 refitting ``ELO_PER_POINT`` widens that,
#: it does not create it.
MOV_DENOMINATOR_FLOOR = 0.25

#: The divisor of the standard Elo logistic. Textbook, and unchanged.
_LOGISTIC_DIVISOR = 400

#: SPEC-phase1 6.2's envelope version, for the stored state document below.
SCHEMA_VERSION = 1

#: A canonical team id to its Elo rating. See the module docstring for why this
#: is a type alias and not a class.
Ratings = dict[str, float]

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


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
    ratings: Ratings


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


def win_probability(predicted_margin: float) -> float:
    """The home team's win probability for a predicted margin (SPEC-phase1 3.1).

    Derived from the margin rather than computed alongside it, and that is the
    point. The PRD requires that the two numbers cannot disagree, and the only way
    to state that as an identity rather than a hope is to make one a function of
    the other. A refactor that computed them from separate quantities would break
    ``test_margin_and_probability_cannot_disagree`` and nothing else.
    """
    return 1 / (1 + 10 ** (-(predicted_margin * ELO_PER_POINT) / _LOGISTIC_DIVISOR))


def predict(ratings: Ratings, game: Game, *, hfa: float) -> Prediction:
    """The model's forecast for one game, from the home team's perspective.

    ``hfa`` is a keyword because it belongs to the Sagarin snapshot the run read
    (SPEC-phase1 3.3) rather than to the game. Putting it on ``Game`` would hang a
    per-run value off a per-fixture object, and the first thing to serialise a
    ``Game`` would carry it into a document with no business asserting it.
    """
    gap = _rating(ratings, game.home, game) - _rating(ratings, game.away, game)
    margin = gap / ELO_PER_POINT + _home_edge(game, hfa)
    return Prediction(predicted_margin=margin, win_probability=win_probability(margin))


def update(ratings: Ratings, game: Game, *, hfa: float) -> Ratings:
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

    diff = home + _home_edge(game, hfa) * ELO_PER_POINT - away
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
    unclamped = _raw_mov_denominator(signed)
    denominator = mov_denominator(signed)
    if unclamped < MOV_DENOMINATOR_FLOOR:
        raise EloDomainError(
            f"game {game.cfbd_game_id} ({game.away} at {game.home}) was won from "
            f"{-signed:.0f} Elo of disadvantage, putting SPEC-phase1 3.4's multiplier "
            f"denominator at {unclamped:.4f}, under the {MOV_DENOMINATOR_FLOOR} floor. "
            f"Clamped it would still move a rating by up to "
            f"{K * math.log(abs(margin) + 1) * (MOV_DAMPING / MOV_DENOMINATOR_FLOOR):.0f} "
            f"Elo from one result; unclamped and below zero it would move it the wrong "
            f"way. Either the ratings have diverged or the scale needs refitting "
            f"(SPEC-phase1 12) -- neither is something to apply a game through"
        )

    mov_mult = math.log(abs(margin) + 1) * (MOV_DAMPING / denominator)
    delta = K * mov_mult * (actual - expected)

    # Zero-sum by construction. Elo that leaks or creates rating drifts the whole
    # scale, and the drift is invisible in any single game.
    return {**ratings, game.home: home + delta, game.away: away - delta}


def _raw_mov_denominator(elo_diff_winner: float) -> float:
    """SPEC-phase1 3.4's denominator exactly as written, floor and all removed.

    Split out so the formula appears once. ``update`` needs both this and the
    floored value -- one to decide whether to raise, one to divide by -- and two
    copies of an expression that must agree is how they stop agreeing.
    """
    return elo_diff_winner * 0.001 + MOV_DAMPING


def mov_denominator(elo_diff_winner: float) -> float:
    """The same denominator, floored (SPEC-phase1 3.4). Never inverts the multiplier.

    Public and separately tested because it is the half of the guard that
    ``update`` cannot demonstrate. The raise stands in front of the clamp, so no
    call to ``update`` ever divides by a clamped value -- which means a test that
    only went through ``update`` would pass with the clamp deleted, and the
    defence-in-depth §3.4 claims would be a comment rather than a property.

    Deleting the clamp fails ``test_the_clamp_holds_on_its_own``.
    """
    return max(_raw_mov_denominator(elo_diff_winner), MOV_DENOMINATOR_FLOOR)


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
