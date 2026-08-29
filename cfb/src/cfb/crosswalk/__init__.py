"""The season crosswalk (SPEC-phase0 section 6).

One name from each vendor maps to a project-owned canonical slug. The slug is
the join key everywhere downstream, so a vendor renaming a team or the project
swapping a source rewrites one YAML line rather than every historical row.

**Exact lookup, or it raises.** No fuzzy matching, no normalization pass, no
default, no ``None`` return (SPEC 6.2). Every one of those would turn a name this
project has not decided about into a name it silently guessed at, and an
unmapped team is how a game vanishes from the training set without anything going
red. Similarity scoring exists only in ``bootstrap``, only to order a human's
decisions, and this module cannot reach it.

**One file per season.** A played season's mapping is frozen: backfill reads that
season's file, so a 2027 realignment cannot retroactively break a 2026 join. The
duplicated rows are cheap.

Both divisions. Sagarin rates 266 teams and 128 of them are FCS, and ``/games``
returns those opponents by CFBD name -- an FBS-only crosswalk drops the first
FBS-vs-FCS game of September (SPEC 6.5).
"""

from pathlib import Path
from typing import Literal

import yaml

from cfb.errors import UnmappedTeamError

__all__ = ["Crosswalk", "crosswalk_path", "load"]

_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "crosswalk"


def crosswalk_path(season: int, *, data_dir: Path | None = None) -> Path:
    return (data_dir or _DEFAULT_DATA_DIR) / f"teams-{season}.yaml"


class Crosswalk:
    """A season's mapping, indexed both ways.

    Built once and read many times: the collectors resolve every name on every
    row, so the indexes are dicts rather than a scan.
    """

    def __init__(self, season: int, entries: dict[str, dict], *, path: Path) -> None:
        self.season = season
        self.entries = entries
        self._path = path
        self._by_sagarin = _index(entries, "sagarin", "sagarin_aliases", path)
        self._by_cfbd = _index(entries, "cfbd", "cfbd_aliases", path)

    def from_sagarin(self, name: str) -> str:
        """The canonical id for a Sagarin name, or ``UnmappedTeamError``."""
        return self._lookup(self._by_sagarin, "sagarin", name)

    def from_cfbd(self, name: str) -> str:
        """The canonical id for a CFBD name, or ``UnmappedTeamError``."""
        return self._lookup(self._by_cfbd, "cfbd", name)

    def division(self, canonical_id: str) -> Literal["FBS", "FCS"]:
        entry = self.entries.get(canonical_id)
        if entry is None:
            raise UnmappedTeamError(
                f"no crosswalk entry with canonical id {canonical_id!r} for season "
                f"{self.season} in {self._path.name}"
            )
        return entry["division"]

    def _lookup(self, index: dict[str, str], source: str, name: str) -> str:
        try:
            return index[name]
        except KeyError:
            # SPEC 6.4: the error message is the fix. It names the source,
            # because the same string can be a legal name on one side and
            # unknown on the other, and the file to edit.
            raise UnmappedTeamError(
                f"unmapped {source} team name {name!r} for season {self.season}.\n"
                f"Add it to {self._path}, then: uv run pytest cfb/tests/test_crosswalk.py"
            ) from None


def load(season: int, *, data_dir: Path | None = None) -> Crosswalk:
    """The committed crosswalk for ``season``.

    Raises rather than returning an empty mapping when the file is missing: an
    empty crosswalk resolves nothing, and the failure would surface 266 rows
    later as "every name is unmapped" rather than as "the file is not there".
    """
    path = crosswalk_path(season, data_dir=data_dir)
    if not path.is_file():
        raise UnmappedTeamError(
            f"no crosswalk for season {season} at {path}. Generate the starting point with "
            f"`uv run cfb crosswalk bootstrap --season {season}`, then decide the remainder by hand"
        )

    raw = yaml.safe_load(path.read_bytes())
    if not isinstance(raw, dict) or not raw:
        raise UnmappedTeamError(
            f"crosswalk at {path} is empty or not a mapping of canonical_id -> entry"
        )
    for canonical, entry in raw.items():
        missing = {"cfbd", "sagarin", "division"} - set(entry or {})
        if missing:
            raise UnmappedTeamError(
                f"crosswalk entry {canonical!r} in {path} is missing {sorted(missing)}"
            )
        if entry["division"] not in ("FBS", "FCS"):
            raise UnmappedTeamError(
                f"crosswalk entry {canonical!r} has division {entry['division']!r}; "
                f"expected 'FBS' or 'FCS'"
            )
    return Crosswalk(season, raw, path=path)


def _index(entries: dict[str, dict], key: str, alias_key: str, path: Path) -> dict[str, str]:
    """Name -> canonical id, aliases included.

    A collision raises at load rather than at lookup. One name resolving to two
    canonical ids splits a team's history in half without either half looking
    wrong from a single row.
    """
    index: dict[str, str] = {}
    for canonical, entry in entries.items():
        for name in [entry.get(key), *(entry.get(alias_key) or [])]:
            if name is None:
                continue
            if name in index:
                raise UnmappedTeamError(
                    f"{key} name {name!r} in {path} maps to both {index[name]!r} and "
                    f"{canonical!r}; one team's history would split in half"
                )
            index[name] = canonical
    return index
