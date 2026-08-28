"""The crosswalk (SPEC-phase0 section 6).

**These tests are the worklist.** SPEC §6.3 bootstraps the exact matches and
leaves the rest in `_candidates-2026.yaml` for a human; §6.4 ends its fix loop
with "Then: `uv run pytest cfb/tests/test_crosswalk.py`". So until every name is
decided, `test_every_sagarin_name_resolves` fails and its message names exactly
what is left. That is the intended state of this file mid-review, not a defect --
a green run here means the mapping is complete.

The rosters are the contract, and they span both divisions. Sagarin rates 266
teams and 128 of them are FCS; `/games` returns those opponents by CFBD name, so
an FBS-only crosswalk drops the first cupcake game of September on the floor.
SPEC §6.5 records the decision; the two fixtures are 266 rows each and their two
128s were counted independently by two vendors.

**No fuzzy matching anywhere in here.** SPEC §6.2 is exact lookup against the
mapping and its alias lists, or `UnmappedTeamError`. Similarity scoring lives in
`bootstrap.py`, exists only to order a human's decisions, and never makes one --
there is a test below asserting the runtime cannot even import it.
"""

import json
from pathlib import Path

import pytest
import yaml

from cfb.crosswalk import Crosswalk, load
from cfb.errors import UnmappedTeamError

FIXTURES = Path(__file__).parent / "fixtures"
CFBD_ROSTER = FIXTURES / "rosters" / "cfbd-2026.json"
SAGARIN_ROSTER = FIXTURES / "rosters" / "sagarin-2026.txt"
CROSSWALK_FILE = Path(__file__).parent.parent / "data" / "crosswalk" / "teams-2026.yaml"

SEASON = 2026


@pytest.fixture(scope="module")
def crosswalk() -> Crosswalk:
    return load(SEASON)


@pytest.fixture(scope="module")
def sagarin_roster() -> list[str]:
    text = SAGARIN_ROSTER.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


@pytest.fixture(scope="module")
def cfbd_roster() -> list[dict]:
    return json.loads(CFBD_ROSTER.read_bytes())


@pytest.fixture(scope="module")
def raw_yaml() -> dict:
    return yaml.safe_load(CROSSWALK_FILE.read_bytes()) or {}


def _unmapped(names, lookup) -> list[str]:
    missing = []
    for name in names:
        try:
            lookup(name)
        except UnmappedTeamError:
            missing.append(name)
    return missing


class TestCoverage:
    """SPEC §6.5's first two assertions, and the reason the suite exists.

    A name the crosswalk cannot resolve is a game that vanishes from the
    training set. These fail loudly and list what is missing, because that list
    is the work.
    """

    def test_every_sagarin_name_resolves(self, crosswalk, sagarin_roster):
        missing = _unmapped(sagarin_roster, crosswalk.from_sagarin)
        assert not missing, (
            f"{len(missing)} of {len(sagarin_roster)} Sagarin names are unmapped. "
            f"Decide them in data/crosswalk/teams-2026.yaml -- the ordered candidates are in "
            f"_candidates-2026.yaml:\n  " + "\n  ".join(missing[:40])
        )

    def test_every_cfbd_name_resolves(self, crosswalk, cfbd_roster):
        names = [team["school"] for team in cfbd_roster]
        missing = _unmapped(names, crosswalk.from_cfbd)
        assert not missing, (
            f"{len(missing)} of {len(names)} CFBD names are unmapped:\n  "
            + "\n  ".join(missing[:40])
        )

    def test_both_divisions_are_represented(self, crosswalk, raw_yaml):
        """The FCS half is the point of SPEC §6.5's widening.

        A crosswalk that resolved only FBS would pass every other test here and
        still drop the first FBS-vs-FCS game of the season.
        """
        divisions = {entry["division"] for entry in raw_yaml.values()}
        assert divisions == {"FBS", "FCS"}


class TestNoOrphans:
    """SPEC §6.5: no entry may reference a name absent from both rosters.

    This catches the typo, which the coverage tests above cannot: a misspelled
    `sagarin:` value leaves the real name unmapped *and* adds a mapping for a
    name that does not exist. Only one of those two symptoms is visible from the
    roster side.
    """

    def test_no_entry_references_an_unknown_sagarin_name(self, raw_yaml, sagarin_roster):
        known = set(sagarin_roster)
        orphans = {
            canonical: entry["sagarin"]
            for canonical, entry in raw_yaml.items()
            if entry.get("sagarin") and entry["sagarin"] not in known
        }
        assert not orphans, f"sagarin names in no roster: {orphans}"

    def test_no_entry_references_an_unknown_cfbd_name(self, raw_yaml, cfbd_roster):
        known = {team["school"] for team in cfbd_roster}
        orphans = {
            canonical: entry["cfbd"]
            for canonical, entry in raw_yaml.items()
            if entry.get("cfbd") and entry["cfbd"] not in known
        }
        assert not orphans, f"cfbd names in no roster: {orphans}"

    def test_every_cfbd_id_matches_the_roster(self, raw_yaml, cfbd_roster):
        """`cfbd_id` rides along as a cross-check on the name mapping (SPEC §6.1).

        It is only a cross-check if something checks it. An id that disagrees
        with the name it sits beside means one of the two was pasted from the
        wrong row.
        """
        by_name = {team["school"]: team["id"] for team in cfbd_roster}
        wrong = {
            canonical: (entry["cfbd"], entry.get("cfbd_id"), by_name.get(entry["cfbd"]))
            for canonical, entry in raw_yaml.items()
            if entry.get("cfbd_id") is not None
            and by_name.get(entry["cfbd"]) != entry["cfbd_id"]
        }
        assert not wrong, f"cfbd_id disagrees with the roster: {wrong}"


class TestUniqueness:
    """SPEC §6.5: no duplicate canonical_id, no source name mapped twice.

    A name mapped to two canonical ids splits one team's history in half without
    either half looking wrong.
    """

    def test_canonical_ids_are_unique(self):
        """Asserted on the raw text, because a YAML dict silently keeps the last
        of two identical keys and the duplicate would never reach the parser.
        """
        keys = [
            line.split(":")[0]
            for line in CROSSWALK_FILE.read_text(encoding="utf-8").splitlines()
            if line and not line[0].isspace() and not line.lstrip().startswith("#")
        ]
        duplicates = {key for key in keys if keys.count(key) > 1}
        assert not duplicates, f"duplicate canonical ids: {duplicates}"

    def test_no_sagarin_name_maps_to_two_canonical_ids(self, raw_yaml):
        seen: dict[str, str] = {}
        collisions = {}
        for canonical, entry in raw_yaml.items():
            for name in [entry.get("sagarin"), *entry.get("sagarin_aliases", [])]:
                if name is None:
                    continue
                if name in seen:
                    collisions[name] = (seen[name], canonical)
                seen[name] = canonical
        assert not collisions, f"sagarin names mapped twice: {collisions}"

    def test_no_cfbd_name_maps_to_two_canonical_ids(self, raw_yaml):
        seen: dict[str, str] = {}
        collisions = {}
        for canonical, entry in raw_yaml.items():
            for name in [entry.get("cfbd"), *entry.get("cfbd_aliases", [])]:
                if name is None:
                    continue
                if name in seen:
                    collisions[name] = (seen[name], canonical)
                seen[name] = canonical
        assert not collisions, f"cfbd names mapped twice: {collisions}"


class TestLookup:
    """SPEC §6.2: exact lookup or raise. No fuzzy matching, no default, no None."""

    def test_an_unknown_name_raises(self, crosswalk):
        with pytest.raises(UnmappedTeamError):
            crosswalk.from_sagarin("Springfield Isotopes")
        with pytest.raises(UnmappedTeamError):
            crosswalk.from_cfbd("Springfield Isotopes")

    @pytest.mark.parametrize(
        "near_miss",
        ["ohio state", "Ohio  State", " Ohio State", "Ohio State ", "OhioState"],
        ids=["lowercase", "double-space", "leading", "trailing", "no-space"],
    )
    def test_a_near_miss_raises_rather_than_being_normalized(self, crosswalk, near_miss):
        """The one place a normalization pass would be tempting, and the reason not to.

        Every one of these is a plausible typo *and* a plausible vendor rename.
        Silently accepting them means the day CFBD really does rename a team, the
        crosswalk absorbs it and nobody learns the mapping is now wrong.
        """
        with pytest.raises(UnmappedTeamError):
            crosswalk.from_cfbd(near_miss)

    def test_the_error_names_the_source_and_the_name(self, crosswalk):
        """SPEC §6.4: the error message is the fix. It has to say which side."""
        with pytest.raises(UnmappedTeamError) as excinfo:
            crosswalk.from_sagarin("Springfield Isotopes")
        message = str(excinfo.value)
        assert "Springfield Isotopes" in message
        assert "sagarin" in message.lower()
        assert "teams-2026.yaml" in message

    def test_aliases_resolve_to_the_same_canonical_id(self, raw_yaml, crosswalk):
        """Optional alias lists hold historical spellings (SPEC §6.1)."""
        aliased = [
            (canonical, entry["sagarin_aliases"][0])
            for canonical, entry in raw_yaml.items()
            if entry.get("sagarin_aliases")
        ]
        if not aliased:
            pytest.skip("no sagarin_aliases in the mapping yet")
        canonical, alias = aliased[0]
        assert crosswalk.from_sagarin(alias) == canonical

    def test_division_comes_back_for_a_known_id(self, crosswalk, raw_yaml):
        canonical = next(iter(raw_yaml))
        assert crosswalk.division(canonical) in ("FBS", "FCS")

    def test_division_of_an_unknown_id_raises(self, crosswalk):
        with pytest.raises(UnmappedTeamError):
            crosswalk.division("springfield-isotopes")


class TestBootstrapIsQuarantined:
    """SPEC §6.3: a one-off tool, kept off the runtime path by module boundary
    *and* by this test. Similarity scoring must never decide a mapping, and the
    cheapest way to guarantee that is for the runtime to be unable to reach it.
    """

    @pytest.mark.parametrize(
        "module",
        [
            "cfb.collectors.sagarin",
            "cfb.collectors.cfbd",
            "cfb.parsers.sagarin_ratings",
            "cfb.parsers.sagarin_predictions",
            "cfb.crosswalk",
            "cfb.calendar",
            "cfb.storage",
            "cfb.manifest",
            "cfb.models",
        ],
    )
    def test_no_runtime_module_imports_bootstrap(self, module):
        import importlib
        import sys

        sys.modules.pop("cfb.crosswalk.bootstrap", None)
        importlib.import_module(module)
        assert "cfb.crosswalk.bootstrap" not in sys.modules, (
            f"{module} pulled in the bootstrap tool; similarity scoring must not be "
            f"reachable from the runtime path (SPEC §6.3)"
        )

    def test_the_data_path_never_names_it(self):
        """Belt and braces: a lazily-imported bootstrap passes the test above.

        `cli.py` is the one sanctioned caller -- SPEC 6.3's entry point is
        `uv run cfb crosswalk bootstrap`, so the CLI has to name it, and it does
        so with a function-local import for exactly this reason. What must never
        reach it is the *data path*: the collectors and parsers that turn a page
        into rows, where a similarity score becoming a mapping would be a
        silently wrong join rather than a visible mistake.
        """
        runtime = Path(__file__).parent.parent / "src" / "cfb"
        data_path = [
            *(runtime / "collectors").glob("*.py"),
            *(runtime / "parsers").glob("*.py"),
            runtime / "crosswalk" / "__init__.py",
            runtime / "models.py",
            runtime / "storage.py",
            runtime / "calendar.py",
            runtime / "manifest.py",
        ]
        # Imports, not the word. `crosswalk/__init__.py` names the tool in
        # `load()`'s error message on purpose -- SPEC 6.4 makes the message the
        # fix, and "run bootstrap" is the fix when the file is missing. What is
        # forbidden is reaching the code, not mentioning it.
        offenders = [
            f"{path.name}:{number}"
            for path in data_path
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if "bootstrap" in line and line.lstrip().startswith(("import ", "from "))
        ]
        assert not offenders, f"data-path modules importing bootstrap: {offenders}"

    def test_the_cli_reaches_it_only_from_inside_a_function(self):
        """The import that keeps the quarantine one refactor away from breaking."""
        source = (Path(__file__).parent.parent / "src" / "cfb" / "cli.py").read_text(
            encoding="utf-8"
        )
        for line in source.splitlines():
            if "crosswalk.bootstrap" in line and "import" in line:
                assert line.startswith(" "), (
                    "cli.py imports bootstrap at module scope; keep it function-local "
                    "so the runtime cannot pull it in transitively (SPEC 6.3)"
                )


class TestTheRostersThemselves:
    def test_both_rosters_hold_266(self, sagarin_roster, cfbd_roster):
        """Two vendors, counted independently, agreeing exactly.

        SPEC §4.7 counts 138 FBS and 128 FCS off the Sagarin page; `/teams`
        returns 138 and 128. The totals matching is the best evidence available
        that neither side is dropping rows.
        """
        assert len(sagarin_roster) == 266
        assert len(cfbd_roster) == 266

    def test_the_cfbd_roster_is_both_divisions_and_nothing_lower(self, cfbd_roster):
        counts = {"fbs": 0, "fcs": 0}
        for team in cfbd_roster:
            counts[team["classification"]] = counts.get(team["classification"], 0) + 1
        assert counts == {"fbs": 138, "fcs": 128}
