"""Step 5 of SPEC-phase0 4.3: resolve every name through the crosswalk.

The step sits between the parse and the full manifest write, and where it sits is
the whole design:

```
2. put_bytes(snapshot_key)           <- the irreplaceable artifact is now safe
4. parse ratings + predictions
5. resolve every name via crosswalk  <- UnmappedTeamError
6. put_json(manifest_key)            <- full manifest, parse_ok=true
```

**An unmapped name fails the run after the snapshot is written** (SPEC 6.4). A new
cupcake opponent turning a Tuesday red for ten minutes is the intended cost of
never letting a game vanish silently -- but only if the bytes survive the failure,
because Sagarin publishes current ratings only and a week not captured is gone.
So every test below that asserts the raise also asserts what is still in the
store, and none of them would pass on the exception alone.

**`unmapped` can finally mean what it says.** It was omitted from both manifest
writes until now rather than written as `[]`, because an empty list would have
claimed every name resolved when nothing had been checked. Now `[]` is a positive
assertion: every name on the page was looked up and every one was found. It is
always empty in a *written* post-parse manifest, because a non-empty one raises
before step 6 -- the value carries its meaning by being reachable at all.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from cfb.collectors.sagarin import fetch_sagarin
from cfb.crosswalk import load
from cfb.errors import UnmappedTeamError
from cfb.storage import MemorySnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"
SYNTHETIC_CALENDAR = FIXTURES / "calendar_2026_synthetic.json"
REAL_CROSSWALK = Path(__file__).parent.parent / "data" / "crosswalk" / "teams-2026.yaml"

#: Inside week 04 of the synthetic calendar, so the snapshot files under a real
#: week rather than `unknown` and the raise under test is the only one.
IN_WEEK_FOUR = datetime(2026, 9, 22, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def page() -> bytes:
    return GOLDEN.read_bytes()


@pytest.fixture
def calendar_dir(tmp_path) -> Path:
    root = tmp_path / "calendar"
    root.mkdir()
    (root / "2026.json").write_bytes(SYNTHETIC_CALENDAR.read_bytes())
    return root


@pytest.fixture(scope="module")
def full_crosswalk():
    return load(2026)


@pytest.fixture
def crosswalk_without(tmp_path):
    """The committed crosswalk with named Sagarin entries removed.

    Built by deletion from the real file rather than by hand, so the mapping under
    test is the one production uses minus exactly the rows the test is about.
    """

    def build(*sagarin_names: str):
        entries = yaml.safe_load(REAL_CROSSWALK.read_text(encoding="utf-8"))
        dropped = {
            canonical
            for canonical, entry in entries.items()
            if entry["sagarin"] in sagarin_names
        }
        assert len(dropped) == len(sagarin_names), (
            f"expected to drop {sagarin_names}, matched {dropped}"
        )
        for canonical in dropped:
            del entries[canonical]

        root = tmp_path / "crosswalk"
        root.mkdir(exist_ok=True)
        (root / "teams-2026.yaml").write_text(
            yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8"
        )
        return load(2026, data_dir=root)

    return build


def run(store, page, *, calendar_dir, crosswalk, now=IN_WEEK_FOUR):
    return fetch_sagarin(
        store=store,
        now=now,
        fetch=lambda: page,
        data_dir=calendar_dir,
        crosswalk=crosswalk,
    )


def manifests(store) -> list[dict]:
    """The manifests as raw dicts, so an absent key is distinguishable from None."""
    return [
        json.loads(store.get_bytes(key))
        for key in sorted(store._objects)  # noqa: SLF001 - the test store is a dict
        if key.endswith(".meta.json")
    ]


class TestTheResolvedRun:
    def test_the_golden_capture_resolves_completely(self, page, calendar_dir, full_crosswalk):
        store = MemorySnapshotStore()
        run(store, page, calendar_dir=calendar_dir, crosswalk=full_crosswalk)  # must not raise

        [manifest] = manifests(store)
        assert manifest["parse_ok"] is True

    def test_unmapped_is_written_as_a_real_empty_list(
        self, page, calendar_dir, full_crosswalk
    ):
        """`[]` is a positive assertion now, not a placeholder.

        Until step 5 existed this key was omitted from both writes on purpose: an
        empty list would have said every name resolved when nothing had been
        looked up. Present-and-empty and absent are two different claims, and only
        one of them is true after a resolved run.
        """
        store = MemorySnapshotStore()
        run(store, page, calendar_dir=calendar_dir, crosswalk=full_crosswalk)

        [manifest] = manifests(store)
        assert "unmapped" in manifest
        assert manifest["unmapped"] == []
        assert isinstance(manifest["unmapped"], list)


class TestAnUnmappedNameKeepsTheSnapshot:
    """SPEC 6.4, and the assertion that matters more than the exit code.

    An implementation that resolved before writing would satisfy "the run goes
    red" perfectly while destroying the thing the run exists to collect.
    """

    def test_it_raises(self, page, calendar_dir, crosswalk_without):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError):
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

    def test_the_bytes_are_still_there_and_unchanged(
        self, page, calendar_dir, crosswalk_without
    ):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError):
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        [manifest] = manifests(store)
        assert store.get_bytes(manifest["snapshot_key"]) == page

    def test_it_lands_under_the_real_week_not_unknown(
        self, page, calendar_dir, crosswalk_without
    ):
        """A crosswalk gap is not a partitioning problem.

        Filing it under `week=unknown` would put a perfectly well-placed snapshot
        in the re-partition sweep's queue for a reason that has nothing to do with
        the calendar.
        """
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError):
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        [manifest] = manifests(store)
        assert manifest["week"] == "04"
        assert manifest["week_resolution"] == "calendar"

    def test_the_manifest_left_behind_is_the_honest_partial_one(
        self, page, calendar_dir, crosswalk_without
    ):
        """Step 6 never ran, so `parse_ok` is absent and so is `unmapped`.

        SPEC 4.3 calls that state detectable and replayable. Writing `parse_ok:
        true` alongside a failed resolution would be the one thing worse than
        either -- a manifest asserting a run finished when it did not.
        """
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError):
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        [manifest] = manifests(store)
        assert "parse_ok" not in manifest or manifest["parse_ok"] is None
        assert "unmapped" not in manifest or manifest["unmapped"] is None

    def test_a_missing_crosswalk_file_also_keeps_the_snapshot(
        self, page, calendar_dir, tmp_path
    ):
        """The crosswalk is loaded at step 5, not at the top of the function.

        A missing `teams-2026.yaml` is a real problem and must not be one that
        costs the week's capture. Loading it before the fetch would make an
        unreadable file destroy a page that only exists today.
        """
        store = MemorySnapshotStore()
        empty = tmp_path / "no-crosswalk"
        empty.mkdir()

        with pytest.raises(UnmappedTeamError):
            fetch_sagarin(
                store=store,
                now=IN_WEEK_FOUR,
                fetch=lambda: page,
                data_dir=calendar_dir,
                crosswalk=None,
                crosswalk_dir=empty,
            )

        [manifest] = manifests(store)
        assert store.get_bytes(manifest["snapshot_key"]) == page


class TestTheErrorIsTheFix:
    """SPEC 6.4: the message is the fix, not a pointer to where the fix lives."""

    def test_it_names_the_snapshot_it_came_from(self, page, calendar_dir, crosswalk_without):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError) as excinfo:
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        [manifest] = manifests(store)
        assert manifest["snapshot_key"] in str(excinfo.value)

    def test_it_names_the_unmapped_name(self, page, calendar_dir, crosswalk_without):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError) as excinfo:
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        assert "Ohio State" in str(excinfo.value)

    def test_it_shows_the_yaml_to_add_and_what_to_run(
        self, page, calendar_dir, crosswalk_without
    ):
        """A message that says "add it to the crosswalk" makes the reader derive
        the shape. SPEC 6.4's example hands it over ready to paste.
        """
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError) as excinfo:
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without("Ohio State"))

        message = str(excinfo.value)
        assert "teams-2026.yaml" in message
        assert "sagarin:" in message
        assert "division:" in message
        assert "pytest" in message

    def test_every_unmapped_name_is_listed_not_only_the_first(
        self, page, calendar_dir, crosswalk_without
    ):
        """Realignment renames several teams at once.

        Failing on the first one turns one fix into N red runs, and the person
        doing the fixing learns that after the second.
        """
        missing = ("Ohio State", "Alabama", "Gardner-Webb")
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError) as excinfo:
            run(store, page, calendar_dir=calendar_dir, crosswalk=crosswalk_without(*missing))

        message = str(excinfo.value)
        for name in missing:
            assert name in message
        assert "3" in message, "the count belongs in the message"


class TestPredictionNamesAreResolvedToo:
    """SPEC 4.3 says every name, and the predictions block is half the value.

    On the golden capture the 106 prediction names are a strict subset of the 266
    rated ones, so resolving the ratings table alone would look complete. This
    renames a team in one predictions row only, which is what a page where the two
    blocks disagree would look like.
    """

    @pytest.fixture
    def page_with_a_prediction_only_name(self, page) -> bytes:
        text = page.decode("utf-8")
        row = "   Gardner-Webb             309"
        assert text.count(row) >= 1, "the Gardner-Webb prediction row moved"
        # Same length, so every column after it stays where the parser expects.
        return text.replace(row, "   Gardner-Webz             309").encode("utf-8")

    def test_a_name_only_in_the_predictions_block_still_fails_the_run(
        self, page_with_a_prediction_only_name, calendar_dir, full_crosswalk
    ):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError) as excinfo:
            run(
                store,
                page_with_a_prediction_only_name,
                calendar_dir=calendar_dir,
                crosswalk=full_crosswalk,
            )

        assert "Gardner-Webz" in str(excinfo.value)

    def test_and_the_bytes_survive_that_too(
        self, page_with_a_prediction_only_name, calendar_dir, full_crosswalk
    ):
        store = MemorySnapshotStore()
        with pytest.raises(UnmappedTeamError):
            run(
                store,
                page_with_a_prediction_only_name,
                calendar_dir=calendar_dir,
                crosswalk=full_crosswalk,
            )

        [manifest] = manifests(store)
        assert store.get_bytes(manifest["snapshot_key"]) == page_with_a_prediction_only_name
