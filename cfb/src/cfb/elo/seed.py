"""Seeding Elo from the Sagarin preseason page (SPEC-phase1 3.2).

Phase 2 owns historical backfill, so Phase 1 opens with no prior results at all.
A uniform 1500 start predicts Texas-Kennesaw State as a coin flip through
September, which is visibly wrong on ``/cfb`` in exactly the weeks people arrive.
The preseason page carries real information about relative strength -- a 67.2
point spread across FBS and a 25.8 point FBS-FCS median gap -- and this is the
transform that moves it onto the Elo scale::

    elo = 1500 + (sagarin_rating - fbs_mean) * ELO_PER_POINT

**The mean is the part that can silently be wrong.** The formula looks correct
under any ``mean``, and centring on the all-266 mean instead of the FBS mean
shifts every rating by 367 Elo while leaving every relative gap intact -- so every
internal-consistency check still passes and Ohio State reads 2853. Only the
absolute values in ``tests/test_seed.py`` distinguish the two.

**It is this snapshot's mean, not a stored constant.** 67.85 would look identical
on the golden capture and be wrong on every page Sagarin publishes after it.
"""

import statistics

from cfb.crosswalk import Crosswalk, crosswalk_path
from cfb.elo import ELO_PER_POINT, Ratings
from cfb.errors import ParseError, SeedStateError, UnmappedTeamError
from cfb.models import SagarinSnapshot

__all__ = ["BASE_ELO", "seed"]

#: Where the FBS field is centred. The textbook Elo origin, kept because the only
#: thing it has to be is the same number every season.
BASE_ELO = 1500.0


def seed(snapshot: SagarinSnapshot, crosswalk: Crosswalk) -> Ratings:
    """Every team on a preseason page, keyed by canonical id.

    Centring on the FBS mean rather than the all-266 mean puts the FBS field
    either side of 1500 and lets FCS fall where the ratings put it, which is the
    behaviour the division gap is supposed to produce. Nothing is clamped, no
    division carries a bonus, and no team gets a different transform from the
    rest: an Elo gap divided by ``ELO_PER_POINT`` reproduces Sagarin's own rating
    difference for every pair, and ``tests/test_seed.py`` asserts that
    exhaustively over all 35,245 of them.

    **FCS is seeded too.** FCS games count (§3.4) -- an FBS team losing to one is
    the single most informative result of its season -- so those teams need
    ratings, and the crosswalk spans both divisions for this reason.
    """
    _refuse_in_season(snapshot)

    fbs = [team.rating for team in snapshot.teams if team.division == "A"]
    if not fbs:
        # Every path that produces this is a parse that went wrong rather than a
        # page that means it: a real Sagarin page rates ~138 FBS teams, and a
        # mean over an empty list is the one arithmetic here with no answer.
        raise ParseError(
            "no division-'A' teams in the snapshot, so there is no FBS mean to centre on "
            "(SPEC-phase1 3.2). A real page rates roughly 138 of them; zero means the "
            "division column was misread, not that the season has no FBS"
        )
    fbs_mean = statistics.fmean(fbs)

    ratings: Ratings = {}
    unmapped: list[str] = []
    collided: list[str] = []

    for team in snapshot.teams:
        try:
            canonical = crosswalk.from_sagarin(team.name)
        except UnmappedTeamError:
            # Collected rather than raised on, for the same reason the collector
            # collects (Phase 0 §6.4): realignment renames several teams at once,
            # and failing one at a time turns a single fix into a week of red runs.
            unmapped.append(team.name)
            continue
        if canonical in ratings:
            collided.append(f"{canonical} (rank {team.rank}, {team.name})")
            continue
        ratings[canonical] = BASE_ELO + (team.rating - fbs_mean) * ELO_PER_POINT

    if unmapped:
        raise UnmappedTeamError(
            f"{len(unmapped)} Sagarin {'name' if len(unmapped) == 1 else 'names'} on the "
            f"preseason page have no entry in {crosswalk_path(crosswalk.season)}: "
            f"{', '.join(repr(name) for name in unmapped)}.\n"
            f"Seeding 265 of 266 teams would leave the rest unrated for the season with "
            f"nothing saying so. Add them, then: uv run pytest cfb/tests/test_crosswalk.py"
        )
    if collided:
        # `Crosswalk` already rejects two names mapping to one id at load, so this
        # needs a page that lists the same team twice under names that both
        # resolve. Whichever row landed second would silently overwrite the first.
        raise UnmappedTeamError(
            f"two rows on the preseason page resolve to the same canonical id: "
            f"{', '.join(collided)}. One team cannot hold two preseason ratings"
        )

    return ratings


def _refuse_in_season(snapshot: SagarinSnapshot) -> None:
    """Seeding is a preseason-only operation (SPEC-phase1 3.2).

    It runs once, from the first snapshot whose ``page_state`` is ``preseason``,
    and never again within a season. A mid-season re-seed would silently discard
    every result the model had learned from and revert the season to August, and
    this refusal is the only thing standing between that and a rerun of the wrong
    command.
    """
    if snapshot.page_state != "preseason":
        raise SeedStateError(
            f"refusing to seed from a snapshot whose page_state is "
            f"{snapshot.page_state!r} (page stamped {snapshot.page_date_stamp}). Seeding is "
            f"preseason-only (SPEC-phase1 3.2): re-seeding mid-season would discard every "
            f"result the ratings have learned from and revert them to August"
        )
