"""Season and week resolution (SPEC-phase0 section 3).

Built against ``fixtures/calendar_2026_synthetic.json`` rather than
``data/calendar/2026.json``, which needs a CFBD key nobody has wired up yet. The
fixture is a hand-built calendar in the CFBD ``/calendar`` shape: fifteen regular
weeks a week apart from 2026-08-29, plus one postseason entry running
2026-12-19 to 2027-01-11. Between them the tests below reach every partition
value in SPEC 3.2 -- ``preseason``, ``01``-``15``, ``postseason``, ``offseason``,
``unknown`` here, and ``season`` in ``test_manifest.py`` where it belongs, since
it is a property of a CFBD resource and not of a date.

Following the idiom of ``test_models.py``: one good fixture, and the broken
variants built by mutating it in memory. A truncated calendar and a malformed one
are two lines of setup each, and a second and third fixture file on disk would be
two more things to keep in sync with the first.

**Three signatures here are proposals, not spec.** SPEC 3.1 writes
``load_calendar(season)``, ``resolve(now)`` and ``in_season(now)``, none of which
can be pointed at a fixture, so each grew one keyword argument -- ``data_dir`` on
the loader, ``calendar`` on the other two. Nothing else about them changed, and
if the injection should look different, these tests are where to say so.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb.calendar import in_season, load_calendar, resolve
from cfb.errors import WeekResolutionError

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "calendar_2026_synthetic.json"


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return json.loads(SYNTHETIC.read_bytes())


@pytest.fixture
def data_dir(tmp_path, entries) -> Path:
    """A `data/calendar/` directory holding the synthetic 2026 calendar."""
    root = tmp_path / "calendar"
    root.mkdir()
    (root / "2026.json").write_bytes(json.dumps(entries).encode("utf-8"))
    return root


@pytest.fixture
def calendar(data_dir):
    return load_calendar(2026, data_dir=data_dir)


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


class TestLoadCalendar:
    def test_loads_the_committed_shape(self, calendar):
        assert calendar.season == 2026

    def test_a_missing_file_raises(self, tmp_path):
        """SPEC 3.3's first failure cause. It raises here; SPEC 3.3's "the fetch
        still happens" is the collector's job, tested at the bottom of this file.
        """
        empty = tmp_path / "calendar"
        empty.mkdir()
        with pytest.raises(WeekResolutionError) as excinfo:
            load_calendar(2026, data_dir=empty)
        assert "2026" in str(excinfo.value)

    def test_malformed_json_raises(self, tmp_path):
        root = tmp_path / "calendar"
        root.mkdir()
        (root / "2026.json").write_bytes(b'[{"season": 2026, "week":')
        with pytest.raises(WeekResolutionError):
            load_calendar(2026, data_dir=root)

    def test_valid_json_of_the_wrong_shape_raises(self, tmp_path):
        """Parsing is not the same as understanding.

        A calendar that is valid JSON but carries none of the fields resolution
        needs would otherwise resolve every date to something arbitrary.
        """
        root = tmp_path / "calendar"
        root.mkdir()
        (root / "2026.json").write_bytes(b'{"detail": "Unauthorized"}')
        with pytest.raises(WeekResolutionError):
            load_calendar(2026, data_dir=root)

    def test_an_empty_calendar_raises(self, tmp_path):
        """A zero-week calendar is a failed CFBD call that returned 200."""
        root = tmp_path / "calendar"
        root.mkdir()
        (root / "2026.json").write_bytes(b"[]")
        with pytest.raises(WeekResolutionError):
            load_calendar(2026, data_dir=root)

    def test_the_season_must_match_what_was_asked_for(self, tmp_path, entries):
        """Guards the copy-paste that files 2025's calendar under 2026.json.

        Silently resolving 2026 dates against 2025's weeks would misfile a whole
        season of snapshots under plausible-looking keys.
        """
        root = tmp_path / "calendar"
        root.mkdir()
        wrong = [entry | {"season": 2025} for entry in entries]
        (root / "2026.json").write_bytes(json.dumps(wrong).encode("utf-8"))
        with pytest.raises(WeekResolutionError):
            load_calendar(2026, data_dir=root)


class TestResolvePartitionValues:
    def test_before_week_one_is_preseason(self, calendar):
        ref = resolve(at(2026, 8, 20, 12), calendar=calendar)
        assert ref.week == "preseason"
        assert ref.how == "calendar"
        assert ref.season == 2026

    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            (at(2026, 8, 30, 12), "01"),
            (at(2026, 9, 6, 12), "02"),
            (at(2026, 9, 20, 12), "04"),
            (at(2026, 10, 25, 12), "09"),
            (at(2026, 11, 15, 12), "12"),
            (at(2026, 12, 6, 12), "15"),
        ],
    )
    def test_regular_season_weeks_are_zero_padded(self, calendar, moment, expected):
        """SPEC 3.2 says ``01``-``15``, not ``1``-``15``.

        The value is a literal S3 path segment. A stray ``"4"`` opens a second
        partition for a week that already has one, and neither half is wrong
        enough to notice.
        """
        ref = resolve(moment, calendar=calendar)
        assert ref.week == expected
        assert ref.how == "calendar"

    def test_the_gap_between_weeks_belongs_to_the_week_that_opened_it(self, calendar):
        """Sagarin is fetched on a Tuesday (SPEC 11), which is nobody's game day.

        Every scheduled run lands in one of these gaps, so this is the ordinary
        case and not an edge one.
        """
        assert resolve(at(2026, 9, 22, 12), calendar=calendar).week == "04"

    def test_bowls_are_postseason(self, calendar):
        ref = resolve(at(2026, 12, 28, 12), calendar=calendar)
        assert ref.week == "postseason"
        assert ref.how == "calendar"

    def test_the_postseason_runs_into_the_next_calendar_year(self, calendar):
        """The season is 2026 on 2027-01-05. Resolving by year would say 2027."""
        ref = resolve(at(2027, 1, 5, 12), calendar=calendar)
        assert ref.season == 2026
        assert ref.week == "postseason"

    def test_after_the_postseason_is_offseason(self, calendar):
        ref = resolve(at(2027, 3, 1, 12), calendar=calendar)
        assert ref.week == "offseason"
        assert ref.how == "calendar"

    def test_a_truncated_calendar_resolves_to_unknown_not_offseason(self, tmp_path, entries):
        """The distinction SPEC 3.3 turns on.

        A complete calendar says a March date is ``offseason``. A calendar that
        stops at week 10 says nothing at all about December, and answering
        ``offseason`` there would be a guess dressed as an answer -- the snapshot
        would be filed under a partition that is confidently wrong rather than
        one that is honestly unknown.
        """
        root = tmp_path / "calendar"
        root.mkdir()
        truncated = [e for e in entries if e["seasonType"] == "regular" and e["week"] <= 10]
        (root / "2026.json").write_bytes(json.dumps(truncated).encode("utf-8"))

        ref = resolve(at(2026, 12, 28, 12), calendar=load_calendar(2026, data_dir=root))
        assert ref.week == "unknown"
        assert ref.how == "unknown"

    def test_resolve_never_raises_on_a_date_it_cannot_place(self, tmp_path, entries):
        """The one documented departure from "validation failures raise".

        SPEC 3.3 prefers a messy artifact to a clean failure here, and the
        ``how`` field exists to carry that: SPEC 2.2 types ``week_resolution`` as
        ``"calendar" | "unknown"``, and ``"unknown"`` could never appear if
        resolution raised instead of returning. The non-zero exit is still owed,
        and the collector still owes it -- after the write.
        """
        root = tmp_path / "calendar"
        root.mkdir()
        truncated = [e for e in entries if e["seasonType"] == "regular" and e["week"] <= 10]
        (root / "2026.json").write_bytes(json.dumps(truncated).encode("utf-8"))
        calendar = load_calendar(2026, data_dir=root)

        ref = resolve(at(2026, 12, 28, 12), calendar=calendar)  # must not raise
        assert ref.week == "unknown"


class TestInSeason:
    """SPEC 4.6: the freshness check runs only while ``in_season`` is true.

    Sagarin does not update from roughly February through August, and alerting
    through the off-season is how alerting dies.
    """

    def test_true_during_the_regular_season(self, calendar):
        assert in_season(at(2026, 10, 6, 12), calendar=calendar) is True

    def test_true_during_the_postseason(self, calendar):
        assert in_season(at(2026, 12, 28, 12), calendar=calendar) is True

    def test_true_on_the_last_postseason_game_day(self, calendar):
        assert in_season(at(2027, 1, 11, 0, 30), calendar=calendar) is True

    def test_false_deep_in_the_offseason(self, calendar):
        assert in_season(at(2027, 5, 15, 12), calendar=calendar) is False

    def test_false_the_month_after_the_postseason_ends(self, calendar):
        assert in_season(at(2027, 2, 15, 12), calendar=calendar) is False


class TestResolutionFailureKeepsTheSnapshot:
    """SPEC 3.3, the case the whole section exists for.

    When resolution fails the fetch still happens, the bytes are written under
    ``week=unknown``, ``week_resolution`` records ``"unknown"``, and the run exits
    non-zero **after** the write. The ordering is the entire point: a Sagarin week
    not captured is gone permanently, and a calendar bug is not a reason to lose
    it. An implementation that resolves first, raises on failure, and never
    fetches satisfies "the run exits non-zero" perfectly while destroying the
    thing the run exists to collect -- so every test below that asserts the raise
    also asserts what survived it, and none of them would pass on the exit code
    alone.

    ``fetch_sagarin`` is a proposed seam, not spec. SPEC 8 gives the CLI surface
    (``uv run cfb fetch sagarin``) and SPEC 4.3 the order of operations, but no
    signature that can be driven without a network and a bucket. This takes the
    store and the fetch as arguments so the test needs neither.
    """

    @pytest.fixture
    def page(self) -> bytes:
        return (FIXTURES / "sagarin_2026_preseason.txt").read_bytes()

    @pytest.fixture
    def truncated_dir(self, tmp_path, entries) -> Path:
        root = tmp_path / "calendar"
        root.mkdir()
        keep = [e for e in entries if e["seasonType"] == "regular" and e["week"] <= 10]
        (root / "2026.json").write_bytes(json.dumps(keep).encode("utf-8"))
        return root

    @staticmethod
    def run(store, page, data_dir, moment):
        from cfb.collectors.sagarin import fetch_sagarin

        return fetch_sagarin(
            store=store, now=moment, fetch=lambda: page, data_dir=data_dir
        )

    def test_the_run_exits_non_zero(self, page, truncated_dir):
        """Necessary, and on its own worth almost nothing -- see the class docstring."""
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

    def test_and_the_bytes_survive_it(self, page, truncated_dir):
        """The assertion that separates a messy artifact from a lost one."""
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

        manifests = store.list_manifests("raw/sagarin/")
        assert len(manifests) == 1
        assert store.get_bytes(manifests[0].snapshot_key) == page

    def test_the_bytes_land_under_week_unknown(self, page, truncated_dir):
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

        [manifest] = store.list_manifests("raw/sagarin/")
        assert "/week=unknown/" in manifest.snapshot_key
        assert manifest.week == "unknown"

    def test_the_manifest_records_the_resolution_as_unknown(self, page, truncated_dir):
        """``week_resolution`` is how a later re-partition finds these objects.

        SPEC 3.3 copies them forward once the calendar is fixed. A manifest that
        said ``"calendar"`` would hide the snapshot from that sweep permanently.
        """
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

        [manifest] = store.list_manifests("raw/sagarin/")
        assert manifest.week_resolution == "unknown"

    def test_no_snapshot_is_filed_under_a_guessed_week(self, page, truncated_dir):
        """Failing over to ``offseason`` would be worse than ``unknown``.

        Both are wrong, but one is indistinguishable from a correct answer and
        would never be re-partitioned.
        """
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

        [manifest] = store.list_manifests("raw/sagarin/")
        for guess in ("week=offseason", "week=postseason", "week=15", "week=11"):
            assert guess not in manifest.snapshot_key

    def test_a_missing_calendar_file_takes_the_same_path(self, page, tmp_path):
        """SPEC 3.3 lists three causes and gives them one behaviour.

        A missing file is the one most likely to happen on a fresh checkout, and
        the one where an implementation is most tempted to bail early.
        """
        from cfb.storage import MemorySnapshotStore

        empty = tmp_path / "calendar"
        empty.mkdir()
        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, empty, at(2026, 9, 20, 12))

        [manifest] = store.list_manifests("raw/sagarin/")
        assert manifest.week == "unknown"
        assert store.get_bytes(manifest.snapshot_key) == page

    def test_a_resolvable_run_is_unaffected(self, page, data_dir):
        """The control. Without it every assertion above is satisfied by a
        collector that files everything under ``unknown`` and always raises.
        """
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        self.run(store, page, data_dir, at(2026, 9, 20, 12))  # must not raise

        [manifest] = store.list_manifests("raw/sagarin/")
        assert manifest.week == "04"
        assert manifest.week_resolution == "calendar"
        assert "/week=04/" in manifest.snapshot_key
        assert store.get_bytes(manifest.snapshot_key) == page
