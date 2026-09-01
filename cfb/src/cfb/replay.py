"""Rebuild a season's Elo state from ``raw/`` (SPEC-phase1 3.5).

Elo is a pure function of the seed and the completed games, and both are already
in ``raw/``. This module is that function, spelled out: it reads snapshots, never
the network, and never the stored state it exists to check.

    seed ......... the *first* preseason Sagarin snapshot of the season
    games ........ the newest CFBD /games capture of each week partition
    hfa .......... per game, from the newest Sagarin manifest before its kickoff
    order ........ every completed game by kickoff, across weeks

**Why this exists.** SPEC-phase1 3.5 keeps a state object under
``elo/season=2026/week=04/<ts>.json`` to give the write-up a visible ratings
history and to make a run cheap. A state file that could drift from the snapshots
it was derived from would be a second source of truth; one that can be
regenerated and checked is a cache. ``verify`` is what makes the difference real
rather than asserted, and it is step 5 of SPEC-phase1 11.

**Kickoff order is the whole correctness argument.** Elo is path-dependent: the
rating a team carries into a game is the sum of everything before it, so applying
a week's games in the order ``/games`` happens to return them produces a season
that is wrong in a way nothing downstream can see. ``/games`` is not sorted by
``startDate``, the sort here is global rather than per-week -- a game moved for
weather is filed under the week it was scheduled in and played after games in the
following one (SPEC-phase1 5.1) -- and ``tests/test_replay.py`` fails if the sort
is dropped.

**Nothing in ``replay`` reads ``elo/``.** It takes the store and produces ratings
from ``raw/`` alone; ``verify`` is a separate call that loads the stored object
afterwards and compares. Folding the two together would make it possible for a
stored value to leak into the rebuild, which would leave the check comparing a
number against itself.

## Two ways to reach the same ratings, and that is the point

``advance`` is the other one. It is what the Sunday run of SPEC-phase1 8 calls:
take last week's stored state, apply the games it has not seen yet, write the
result. Incremental, and it never folds more than one week's worth of arithmetic.

It is not cheaper in *reads* -- both walk every week's newest ``/games`` capture,
because a game postponed out of its week can appear under any of them. The
difference that matters is the accumulation path, not the I/O.

``replay`` and ``advance`` must agree, and **they must not agree by construction.**
A writer implemented as ``replay() -> write`` would make SPEC-phase1 11 step 5
compare a replay against a replay, which verifies nothing at all -- the exact
tautology §3.5's "a cache, not a source of truth" is written to rule out. So the
two accumulate differently on purpose:

    replay    seed, then every completed game of the season in kickoff order
    advance   last week's stored ratings, then this week's completed games

They share the rules that must not drift -- which games count, what order they go
in, which snapshot the HFA comes from -- through ``_applied_games``, and nothing
else. When they disagree it is because the accumulated state missed something the
raw data has: a week whose scoring run never ran, a score corrected after the
fact, a game postponed into a week whose state was already written. Every one of
those is a stale cache, and a red run is the correct response to it.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import (
    SCHEMA_VERSION,
    EloState,
    Game,
    ModelConstants,
    Ratings,
    constants_for,
    constants_of,
    update,
)
from cfb.elo.seed import seed
from cfb.elo.state import StoredState, load_state, newest_state_key, previous_state
from cfb.errors import ReplayError, StateMismatchError
from cfb.models import Manifest
from cfb.sources import (
    HFA_COLUMN,
    RawGame,
    completed_games,
    hfa_for,
    hfa_manifests,
    sagarin_manifests,
    sagarin_snapshot,
    seed_manifest,
    week_position,
)
from cfb.storage import SnapshotStore

__all__ = [
    "Advance",
    "Replay",
    "advance",
    # Re-exported from `cfb.elo.state`, which owns them. They are named here
    # because reading a state to check a rebuild is a replay concern, and a caller
    # doing that should not have to know which module holds the reader.
    "load_state",
    "newest_state_key",
    "replay",
    "seed_state",
    "verify",
]

#: How many rating disagreements a mismatch report lists before it stops. Enough
#: to see whether one team drifted or the whole season did; a full 266-line diff
#: in an Actions log is not read by anyone.
_MISMATCH_SAMPLE = 10


class _Applied(NamedTuple):
    """One game in the replay, with the provenance the run has to be able to name."""

    game: Game
    kickoff: datetime
    partition: str
    #: The game's position in the season, ``(0|1, week)``. Not the same ordering
    #: as ``kickoff``: a game postponed out of its week is played after games in
    #: the following one, so the last game by kickoff is not the furthest week.
    order: tuple[int, int]
    hfa: float
    #: The ``raw/cfbd/`` key the row was read from, and the ``raw/sagarin/``
    #: manifest the HFA came from. SPEC-phase1 4.2 requires a prediction to name
    #: the exact snapshot behind every number; a replay owes the same.
    games_key: str
    hfa_key: str


@dataclass(frozen=True)
class Replay:
    """A season rebuilt from ``raw/``, and the evidence it was rebuilt from."""

    season: int
    #: The partition the rebuild ends at, and the one whose stored state it is
    #: comparable to. ``through_week`` when the caller named one -- a week with no
    #: completed games is still that week -- otherwise the last applied game's, or
    #: ``"preseason"`` when the season has none yet.
    week: str
    ratings: Ratings
    #: The ``raw/sagarin/`` snapshot key the season was seeded from.
    seeded_from: str
    applied: tuple[_Applied, ...]
    #: Every ``raw/cfbd/`` games key read, newest capture first.
    games_keys: tuple[str, ...]
    #: The constants this rebuild used (SPEC-phase2 4.1).
    #:
    #: Required rather than defaulted, and that is deliberate: a rebuild that does
    #: not know its own scale is the exact object this field exists to prevent, and
    #: a default would let one be constructed. ``verify`` refuses to compare
    #: against a state written on another scale rather than reporting a rescale as
    #: 266 separate rating drifts.
    constants: ModelConstants
    #: The earliest kickoff this rebuild folded, when the season's opening games
    #: could not be priced. ``None`` when it covered the season entire. See
    #: ``EloState.folded_from``.
    folded_from: datetime | None = None

    @property
    def games_applied(self) -> int:
        return len(self.applied)

    @property
    def through_kickoff(self) -> datetime | None:
        """The kickoff of the last game applied. ``applied`` is in kickoff order."""
        return self.applied[-1].kickoff if self.applied else None

    def as_state(self, *, generated_at: datetime) -> EloState:
        """The state document this rebuild would write (SPEC-phase1 3.5).

        ``replay`` does not write it -- SPEC-phase1 8 gives that to the Sunday
        scoring run -- but the document has one definition, and it is this one, so
        a writer and this reader cannot drift into two shapes of the same object.
        """
        return EloState(
            schema_version=SCHEMA_VERSION,
            season=self.season,
            week=self.week,
            generated_at=generated_at,
            seeded_from=self.seeded_from,
            games_applied=self.games_applied,
            folded_from=self.folded_from,
            through_kickoff=self.through_kickoff,
            model=self.constants,
            ratings=dict(self.ratings),
        )


def replay(
    *,
    store: SnapshotStore,
    season: int,
    through_week: str | None = None,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
    constants: ModelConstants | None = None,
) -> Replay:
    """Rebuild ``season``'s Elo ratings from stored snapshots. No network, no state.

    ``through_week`` is a partition value (``"04"``, ``"postseason"``) and cuts the
    season off *inclusively* at that week, so the result is comparable to
    ``elo/season=2026/week=04/``. ``None`` replays everything ``raw/`` holds.

    The crosswalk is injected for the same reason the collectors inject it: the
    committed one is what production uses, and a test that could not substitute
    another could not exercise a mapping gap at all.

    ``constants`` defaults to the set ``season`` runs under (SPEC-phase2 4.1).
    Pass one explicitly to rebuild on the scale a *stored* state was written on,
    which is what verifying a state from before a refit requires -- and is the
    only reason this is a parameter rather than a lookup.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)
    constants = constants or constants_for(season)

    manifests = sagarin_manifests(store, season)
    seed_from = seed_manifest(manifests, season)
    ratings = seed(sagarin_snapshot(store, seed_from), resolver, constants=constants)

    cutoff = week_position(through_week, label="--through-week")
    applied, games_keys, folded_from = _applied_games(
        store,
        season=season,
        resolver=resolver,
        manifests=hfa_manifests(manifests),
        keep=lambda raw_game: cutoff is None or raw_game.order <= cutoff,
    )

    for entry in applied:
        ratings = update(ratings, entry.game, hfa=entry.hfa, constants=constants)

    return Replay(
        season=season,
        constants=constants,
        # The furthest week reached, not the last game by kickoff -- see
        # `_Applied.order`. A season whose week 1 finished late still ran through
        # week 2, and naming it "01" would compare against the wrong stored state.
        week=through_week
        or (max(applied, key=lambda e: e.order).partition if applied else "preseason"),
        ratings=ratings,
        seeded_from=seed_from.snapshot_key,
        applied=tuple(applied),
        games_keys=tuple(games_keys),
        folded_from=folded_from,
    )


def seed_state(
    *,
    store: SnapshotStore,
    season: int,
    now: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> EloState:
    """Build the season's opening state from the preseason page. Does not write it.

    SPEC-phase1 9's ``cfb elo seed``. The result is the ``week=preseason`` state:
    266 teams, no games applied, naming the snapshot it came from.

    §3.2's "refuses in-season" is enforced twice over on this path, and neither is
    redundant. ``_seed_manifest`` will only return a manifest whose ``page_state``
    is ``preseason``, so an in-season page cannot reach ``seed()`` from here at
    all; ``seed()`` raises ``SeedStateError`` on one anyway, because it is also
    called from places that have not selected the snapshot.
    """
    seed_from = seed_manifest(sagarin_manifests(store, season), season)
    constants = constants_for(season)
    ratings = seed(
        sagarin_snapshot(store, seed_from),
        crosswalk or load_crosswalk(season, data_dir=crosswalk_dir),
        constants=constants,
    )
    return EloState(
        schema_version=SCHEMA_VERSION,
        season=season,
        week="preseason",
        generated_at=now,
        seeded_from=seed_from.snapshot_key,
        games_applied=0,
        through_kickoff=None,
        model=constants,
        ratings=ratings,
    )


@dataclass(frozen=True)
class Advance:
    """One week folded onto the previous state, and what it was folded onto."""

    state: EloState
    #: The state this started from. Named because a wrong answer here is almost
    #: always a wrong predecessor rather than wrong arithmetic.
    previous: StoredState
    applied: tuple[_Applied, ...]
    games_keys: tuple[str, ...]

    @property
    def games_applied(self) -> int:
        """This week's games. ``state.games_applied`` is the season running total."""
        return len(self.applied)


def advance(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> Advance:
    """Apply one week's completed games to the previous state. Does not write it.

    The incremental path of SPEC-phase1 3.5 and the Elo half of SPEC-phase1 8's
    Sunday run. It folds one week's games onto ratings it did not compute, which is
    why it is not the thing that can be trusted on its own -- ``replay`` is the
    check on it, and the two only mean something because they accumulate
    differently.

    **It starts from the nearest earlier state, not from week minus one.** A week
    whose run never happened leaves a hole, and refusing to proceed would make one
    missed Sunday block every Sunday after it. Building on the older state is the
    answer that keeps the pipeline moving *and* stays detectable: the result is
    missing a week of games, so it disagrees with a rebuild, and step 5 says so.

    **A game postponed out of an already-written week heals on the next run.**
    Week 1's state is written the Sunday after week 1, before a week 1 game played
    the following Thursday exists. Week 2's advance picks it up anyway: it is a
    week 1 game, so it passes the season cut, and its kickoff is after week 1's
    cutoff, so it passes the freshness cut -- and it sorts into kickoff order with
    week 2's games rather than ahead of them. Week 1's own state stays stale, which
    is honest, and ``cfb elo replay --through-week 01`` will say so.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)

    previous = previous_state(store, season=season, week=week)
    if previous is None:
        raise ReplayError(
            f"no stored Elo state before week {week!r} of season {season}, so there is "
            f"nothing to advance from. Seed the season first: "
            f"uv run cfb elo seed --season {season}"
        )

    # Two bounds, and both are necessary. `order <= target` says how far into the
    # season this state runs; `kickoff > previous` says which of those games the
    # previous state has not already absorbed. Together they make each advance the
    # next contiguous block of the season *in kickoff order*, so the chain composes
    # to exactly the sequence `replay` produces in one pass.
    #
    # Selecting on the week alone cannot do that. A week 1 game postponed past week
    # 2 would be applied in week 1's batch -- before week 2's games -- while a
    # replay sorts it after them, and Elo is path-dependent, so the two would
    # disagree permanently with no re-run able to reconcile them.
    target = week_position(week)
    since = previous.state.through_kickoff
    applied, games_keys, batch_bound = _applied_games(
        store,
        season=season,
        resolver=resolver,
        manifests=hfa_manifests(sagarin_manifests(store, season)),
        keep=lambda raw_game: (
            raw_game.order <= target and (since is None or raw_game.start_date > since)
        ),
    )

    ratings = dict(previous.state.ratings)

    # The chain's scale, not the season's. `advance` builds on the previous state,
    # so it must move those ratings the way they were built -- a refit that landed
    # between two states would otherwise apply the new K to old-scale ratings and
    # produce a state that is neither. `verify` catches the result; this stops it
    # from being produced. A season whose states straddle a refit is a season to
    # rebuild from the seed, which is what SPEC-phase2 4.1's freeze exists to make
    # unnecessary.
    constants = constants_of(previous.state)
    for entry in applied:
        ratings = update(ratings, entry.game, hfa=entry.hfa, constants=constants)

    return Advance(
        state=EloState(
            schema_version=SCHEMA_VERSION,
            season=season,
            week=week,
            generated_at=now,
            model=constants,
            # Carried forward rather than re-derived. Every state in a season names
            # the one page the season was seeded from, and a chain whose seed
            # changed halfway is a chain that cannot be replayed.
            seeded_from=previous.state.seeded_from,
            games_applied=previous.state.games_applied + len(applied),
            # **Inherited, then set once.** The bound is a property of the season
            # rather than of a week: it is where the accumulation began, and every
            # later advance is building on that same beginning. The first advance
            # to meet unpriceable games sets it; the rest carry it forward. Later
            # advances see none, because `since` has already moved past them.
            folded_from=previous.state.folded_from or batch_bound,
            # Carried forward when nothing was applied: a week that was entirely
            # postponed leaves the ratings and the cutoff exactly where they were.
            through_kickoff=applied[-1].kickoff if applied else since,
            ratings=ratings,
        ),
        previous=previous,
        applied=tuple(applied),
        games_keys=tuple(games_keys),
    )


def _applied_games(
    store: SnapshotStore,
    *,
    season: int,
    resolver: Crosswalk,
    manifests: list[Manifest],
    keep: Callable[[RawGame], bool],
) -> tuple[list[_Applied], list[str], datetime | None]:
    """Every completed game ``keep`` accepts, resolved and in kickoff order.

    The one place ``replay`` and ``advance`` share. The selection rules themselves
    live in ``cfb.sources`` because ``predict`` needs them too; what this adds is
    the resolution to canonical ids and the kickoff sort, which only the two
    accumulating paths need. They differ only in ``keep`` -- a season-to-date cut
    for one, a single week for the other.

    **Games that no snapshot can price are left out, and the third return value
    says where that started.** ``hfa_for`` reads the newest Sagarin manifest
    captured *strictly before* a game's kickoff (§3.3), so a game that kicked off
    before the earliest such manifest exists has no HFA and never will -- no
    later capture can be retroactively moved in front of it.

    **The skip is provably exactly that set, which is what stops it being a
    catch-all.** ``hfa_at`` fails on one condition and one only: no manifest
    precedes the kickoff. Any game after the earliest manifest therefore has at
    least that one available and cannot fail. So ``kickoff <= earliest`` is not a
    heuristic for "probably unpriceable" -- it is the complete failure set, and
    every other missing-HFA case still raises the way §3.3 requires.
    """
    games, games_keys = completed_games(store, season, keep)

    # Oldest first (`hfa_manifests`), so the first is the boundary. An empty list
    # is left to `hfa_for` below, which raises naming the season -- refusing here
    # would replace a specific message with a vaguer one.
    earliest = manifests[0].fetched_at if manifests else None
    priceable = [
        (raw_game, games_key)
        for raw_game, games_key in games
        if earliest is None or raw_game.start_date > earliest
    ]
    skipped = len(games) - len(priceable)
    if skipped and not priceable:
        # **The bound excludes a season's opening games, never all of them.**
        # Skipping the first few is a pipeline that came online after the first
        # kickoffs (§3.5). Skipping every one is a store whose Sagarin coverage
        # does not overlap its games at all -- and returning a seed-only state for
        # that would report "the season has not started" about a season that has,
        # which is the quiet wrong answer this whole module exists to prevent.
        raise ReplayError(
            f"season {season} has {skipped} completed game"
            f"{'' if skipped == 1 else 's'} and no snapshot carrying "
            f"hfa[{HFA_COLUMN!r}] was captured before any of them -- the earliest is "
            f"{manifests[0].fetched_at.isoformat()}, after the last kickoff. Excluding "
            f"the opening games of a season is expected when the pipeline started "
            f"late; excluding all of them means the captures and the games do not "
            f"overlap, so there is nothing to rebuild from"
        )
    games = priceable

    applied = [
        _Applied(
            game=Game(
                cfbd_game_id=raw_game.id,
                # Canonical ids, never vendor names, and an unmapped one raises
                # here exactly as it does in the collector (SPEC-phase0 6.4).
                home=resolver.from_cfbd(raw_game.home_team),
                away=resolver.from_cfbd(raw_game.away_team),
                home_points=raw_game.home_points,
                away_points=raw_game.away_points,
                neutral_site=raw_game.neutral_site,
                kickoff=raw_game.start_date,
            ),
            kickoff=raw_game.start_date,
            partition=raw_game.partition,
            order=raw_game.order,
            hfa=(hfa := hfa_for(manifests, raw_game, season)).hfa[HFA_COLUMN],
            games_key=games_keys[0] if games_keys else "",
            hfa_key=hfa.snapshot_key,
        )
        for raw_game, games_key in games
    ]

    # The sort, and the reason this module exists as more than a loop. Elo is
    # path-dependent, `/games` does not return kickoff order, and an out-of-order
    # fold is wrong in a way that looks exactly like a correct one.
    #
    # The tie-break is cosmetic rather than load-bearing: two games kicking off at
    # the same instant cannot share a team, and `update` reads and writes only the
    # two teams named in its game, so simultaneous games commute exactly -- in
    # floating point too, not merely in principle. It is here so that the sequence
    # a run applied is reproducible when someone comes to read it.
    applied.sort(key=lambda entry: (entry.kickoff, entry.game.cfbd_game_id))

    # The first game actually folded, and only when something was left out. A run
    # that covered everything reports `None`, so an ordinary season's state is
    # unchanged by any of this.
    folded_from = applied[0].kickoff if skipped and applied else None
    return applied, games_keys, folded_from


def _scale(constants: ModelConstants) -> str:
    """The constants a mismatch message needs, in the order they matter."""
    return (
        f"ELO_PER_POINT={constants.elo_per_point} K={constants.k} "
        f"MOV_DENOMINATOR_FLOOR={constants.mov_denominator_floor}"
    )


def verify(rebuilt: Replay, stored: EloState, *, key: str) -> None:
    """Raise ``StateMismatchError`` unless the rebuild reproduces the stored state.

    **Exact equality, not a tolerance.** The replay is the same arithmetic over the
    same inputs, so agreement is bit-for-bit or the inputs differ -- and a
    tolerance would hide precisely the drift this check exists to find. The
    comparison is what SPEC-phase1 11 step 5 means by "byte-identical ratings";
    Python's ``float`` repr round-trips exactly through JSON, so a stored value
    that was ever equal still is.

    A legitimate cause of failure is a corrected re-pull: CFBD backfills scores,
    and a week re-fetched after the state was written is new evidence rather than
    a bug. The state is then stale and should be regenerated -- which is the check
    doing its job, not a false alarm, and the message says so.
    """
    if stored.season != rebuilt.season:
        raise StateMismatchError(
            f"{key} is season {stored.season} and the replay rebuilt {rebuilt.season}"
        )
    if stored.week != rebuilt.week:
        raise StateMismatchError(
            f"{key} is the state through week {stored.week!r} and the replay ran through "
            f"{rebuilt.week!r}. Comparing two different points of the season would report a "
            f"drift that is only a difference of scope"
        )

    # SPEC-phase2 4.1: a state is checked against the constants it was written
    # under, never against whatever the module currently holds. Caught here rather
    # than left to the rating comparison because a rescale disagrees on *every*
    # rating, and 266 drift lines reporting a refit is a diagnosis nobody makes
    # from the output. The caller rebuilds under `constants_of(stored)`.
    written_under = constants_of(stored)
    if written_under != rebuilt.constants:
        raise StateMismatchError(
            f"{key} was written under {_scale(written_under)} and the replay rebuilt under "
            f"{_scale(rebuilt.constants)}. These are not the same model and their ratings are "
            f"not comparable -- an ELO_PER_POINT of {written_under.elo_per_point} means a "
            f"rating on that scale and nothing else. Rebuild with "
            f"`constants=constants_of(stored)` to check this document, or regenerate the "
            f"state if the season has been refitted (SPEC-phase2 4.1)"
        )

    problems = list(_rating_differences(rebuilt.ratings, stored.ratings))
    if stored.through_kickoff != rebuilt.through_kickoff:
        problems.insert(
            0,
            f"through_kickoff: stored {stored.through_kickoff}, replayed "
            f"{rebuilt.through_kickoff}",
        )
    if stored.games_applied != rebuilt.games_applied:
        problems.insert(
            0,
            f"games_applied: stored {stored.games_applied}, replayed "
            f"{rebuilt.games_applied}",
        )
    # **Compared, and deliberately not tolerantly.** Two accumulations that folded
    # different sets of games should disagree -- that is this check working. A
    # comparison that let `None` mean "unbounded, match anything" would put a
    # permanent hole in the one guarantee §3.5 rests on, to paper over a
    # migration.
    if stored.folded_from != rebuilt.folded_from:
        problems.insert(
            0,
            f"folded_from: stored {stored.folded_from}, replayed "
            f"{rebuilt.folded_from} -- the two folded different games, not merely "
            f"different numbers",
        )
    if not problems:
        return

    shown = problems[:_MISMATCH_SAMPLE]
    more = len(problems) - len(shown)
    raise StateMismatchError(
        f"the replay of season {rebuilt.season} through week {rebuilt.week} does not "
        f"reproduce {key}: {len(problems)} disagreement"
        f"{'' if len(problems) == 1 else 's'}.\n"
        + "\n".join(f"  {line}" for line in shown)
        + (f"\n  ... and {more} more" if more else "")
        + f"\n\nThe replay read {len(rebuilt.games_keys)} /games snapshot"
        f"{'' if len(rebuilt.games_keys) == 1 else 's'} and seeded from "
        f"{rebuilt.seeded_from}. A corrected re-pull of a week after this state was "
        f"written is the benign cause and still makes the state stale: regenerate it. "
        f"Anything else means the stored object and raw/ disagree about what happened."
    )


def _rating_differences(rebuilt: Ratings, stored: Ratings) -> Iterator[str]:
    """Every way two rating sets can disagree, worst first.

    Missing and extra teams come before value drift because they are a different
    failure: a team the replay rates and the state does not means the two ran
    against different crosswalks, and reporting it as "a rating differs" would
    send whoever reads it to the arithmetic instead of to the mapping.
    """
    for canonical in sorted(set(stored) - set(rebuilt)):
        yield f"{canonical}: stored at {stored[canonical]!r}, not replayed at all"
    for canonical in sorted(set(rebuilt) - set(stored)):
        yield f"{canonical}: replayed at {rebuilt[canonical]!r}, absent from the stored state"

    drifted = [
        (abs(rebuilt[canonical] - stored[canonical]), canonical)
        for canonical in sorted(set(rebuilt) & set(stored))
        if rebuilt[canonical] != stored[canonical]
    ]
    for delta, canonical in sorted(drifted, reverse=True):
        yield (
            f"{canonical}: stored {stored[canonical]!r}, replayed {rebuilt[canonical]!r} "
            f"({delta:+.6f})"
        )
