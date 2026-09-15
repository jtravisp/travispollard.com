"""Vendor game-id supersessions (SPEC-phase1 section 5.2).

The team crosswalk beside this module exists because two vendors spell the same
team differently. This one exists because **one vendor spells the same game
differently over time.**

CFBD does not always amend a game in place. 2026 week 1 carried Western Carolina
at Campbell as id ``401866625``, kicking off Saturday 2026-09-05 19:30Z. The game
was pushed to Sunday, and the Sunday capture holds it as id ``401917058`` with the
Saturday row gone entirely -- not rescheduled, replaced. The prediction log,
written Friday and correct when written, is filed under an id the results no
longer contain, so one physical game trips two of section 5.2's three failure
modes at once: a result with no prediction, and a played prediction with no
result.

**The relaxation is a fact, not a heuristic.** `cfb/CLAUDE.md` forbids fallback
and fuzzy matching, and matching an orphaned result on ``(week, home, away)``
would be exactly that -- it would also mask a genuine slate change, which is the
thing section 5.2 was written to catch. So the join stays exact and gains a
second exact key: a committed, reviewed, append-only statement that these two
vendor ids name one game. An id nobody has written down still raises.

**Three load-time refusals, and each is a game that would otherwise go missing.**

    a -> a            a game superseded by itself; a typo that reads as a no-op
    a -> b -> c       a chain, where `current(a)` answers `b` and `b` is gone too
    a -> c, b -> c    two retired ids claiming one replacement, merging two games

A chain is legal for the vendor and refused here on purpose: resolving it
silently would make the file's meaning depend on traversal order, and collapsing
it by hand is one edited line with the whole history still visible in git.

**The mapping never scores anything on its own.** It redirects a lookup, and
``score_week`` then compares the prediction's teams against the result's exactly
as it does for every other game. A wrong entry therefore raises
``UnscoredGameError`` on the team comparison rather than quietly grading the
wrong fixture -- which is the property that makes an asserted equality safe
enough to accept at all.

**A missing file is ordinary and means an empty mapping**, unlike the team
crosswalk, where absence is fatal. Most seasons need no entries, and an empty
mapping removes nothing: every join it does not cover is the strict join that was
already there, still raising. One file per season for the same reason the team
crosswalk has one -- a played season's joins are frozen, and a 2027 entry cannot
reach back into a 2026 document.
"""

from datetime import date
from pathlib import Path

import yaml

from cfb.errors import SupersessionError

__all__ = ["Supersessions", "load_supersessions", "supersessions_path"]

_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "crosswalk"

#: Every field a record must carry. The first is the mapping; the rest are the
#: evidence a reviewer needs to agree with it without re-deriving it from S3 --
#: two ids and no fixture would be an assertion nobody could check.
_REQUIRED = frozenset({"superseded_by", "season", "week", "home", "away", "noticed"})


def supersessions_path(season: int, *, data_dir: Path | None = None) -> Path:
    return (data_dir or _DEFAULT_DATA_DIR) / f"games-superseded-{season}.yaml"


class Supersessions:
    """A season's retired-id mapping. Exact lookup, identity when absent."""

    def __init__(self, season: int, entries: dict[int, dict], *, path: Path) -> None:
        self.season = season
        self.entries = entries
        self._path = path
        self._forward = {retired: entry["superseded_by"] for retired, entry in entries.items()}
        self._backward = {current: retired for retired, current in self._forward.items()}

    def __len__(self) -> int:
        return len(self._forward)

    def current(self, cfbd_game_id: int) -> int:
        """The id this game is filed under now.

        Returns the argument unchanged when nothing supersedes it, which is the
        overwhelming majority of calls and is why this is safe to put in front of
        every lookup rather than only in the failure path.
        """
        return self._forward.get(cfbd_game_id, cfbd_game_id)

    def is_superseded(self, cfbd_game_id: int) -> bool:
        return cfbd_game_id in self._forward

    def retired_for(self, cfbd_game_id: int) -> int | None:
        """The old id a current one replaced, or ``None``.

        The reverse direction exists so a scored row can name the id its forecast
        was actually filed under. A document that silently renumbered a game
        would be the tamper-evident log quietly rewriting its own history.
        """
        return self._backward.get(cfbd_game_id)

    def entry(self, cfbd_game_id: int) -> dict:
        try:
            return self.entries[cfbd_game_id]
        except KeyError:
            raise SupersessionError(
                f"no supersession recorded for game {cfbd_game_id} in {self._path.name}"
            ) from None


def load_supersessions(season: int, *, data_dir: Path | None = None) -> Supersessions:
    """The committed supersessions for ``season``; empty when the file is absent."""
    path = supersessions_path(season, data_dir=data_dir)
    if not path.is_file():
        return Supersessions(season, {}, path=path)

    raw = yaml.safe_load(path.read_bytes())
    if raw is None:
        # A file holding only its header comment. Distinct from a malformed one:
        # the season had no supersessions and someone wrote that down.
        return Supersessions(season, {}, path=path)
    if not isinstance(raw, dict):
        raise SupersessionError(
            f"supersessions at {path} are not a mapping of retired_id -> entry"
        )

    entries: dict[int, dict] = {}
    for retired, entry in raw.items():
        if not isinstance(retired, int) or isinstance(retired, bool):
            raise SupersessionError(
                f"supersession key {retired!r} in {path} is not a CFBD game id. "
                f"Keys are the retired integer id, unquoted"
            )
        if not isinstance(entry, dict):
            raise SupersessionError(
                f"supersession {retired} in {path} is not a mapping of fields"
            )
        missing = _REQUIRED - set(entry)
        if missing:
            raise SupersessionError(
                f"supersession {retired} in {path} is missing {sorted(missing)}. "
                f"Every field is evidence a reviewer needs to agree the two ids are "
                f"one game without re-deriving it from raw/"
            )
        current = entry["superseded_by"]
        if not isinstance(current, int) or isinstance(current, bool):
            raise SupersessionError(
                f"supersession {retired} in {path} has superseded_by {current!r}, "
                f"which is not a CFBD game id"
            )
        if current == retired:
            raise SupersessionError(
                f"supersession {retired} in {path} supersedes itself. That reads as a "
                f"no-op and is almost certainly a mistyped replacement id"
            )
        if entry["season"] != season:
            raise SupersessionError(
                f"supersession {retired} in {path} names season {entry['season']}, but "
                f"the file is season {season}'s. A season's joins are frozen and cannot "
                f"be edited from another season's file"
            )
        entries[retired] = entry

    _refuse_chains(entries, path)
    _refuse_merges(entries, path)
    return Supersessions(season, entries, path=path)


def _refuse_chains(entries: dict[int, dict], path: Path) -> None:
    """A replacement that is itself retired.

    Resolving this transitively would make ``current()`` depend on how far it
    chose to walk, and a mapping whose answer depends on its own traversal is not
    the deterministic artifact this file is supposed to be. Collapsing the chain
    to its final id is one edited line, and git keeps the intermediate step.
    """
    for retired, entry in sorted(entries.items()):
        current = entry["superseded_by"]
        if current in entries:
            raise SupersessionError(
                f"supersession {retired} -> {current} in {path} points at an id that is "
                f"itself superseded by {entries[current]['superseded_by']}. Chains are "
                f"refused rather than followed: collapse it to the final id, which is "
                f"the one the results actually carry"
            )


def _refuse_merges(entries: dict[int, dict], path: Path) -> None:
    """Two retired ids claiming one replacement.

    Whichever way the join resolved it, two predicted games would collapse onto
    one result and one of them would leave the scored set without anything going
    red -- section 5.2's dropped row, arrived at through the very file that exists
    to prevent one.
    """
    seen: dict[int, int] = {}
    for retired, entry in sorted(entries.items()):
        current = entry["superseded_by"]
        if current in seen:
            raise SupersessionError(
                f"supersessions {seen[current]} and {retired} in {path} both claim to be "
                f"superseded by {current}. Two games cannot become one: one of the two "
                f"entries names the wrong replacement"
            )
        seen[current] = retired


def describe(entry: dict) -> str:
    """One line for a log or an error, as the record itself states it."""
    noticed = entry["noticed"]
    when = noticed.isoformat() if isinstance(noticed, date) else str(noticed)
    return (
        f"{entry['away']} at {entry['home']}, season {entry['season']} week "
        f"{entry['week']}, recorded {when}"
    )
