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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cfb.calendar import (
    PRESEASON_LEAD,
    in_season,
    last_completed_week,
    load_calendar,
    resolve,
)
from cfb.errors import WeekResolutionError
from cfb.manifest import snapshot_key

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "calendar_2026_synthetic.json"

#: Fixed so the expected key is a literal rather than a second computation of the
#: thing under test. Nothing here depends on it matching the resolved moment.
KEYED_AT = datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC)


#: The committed calendar, one real `/calendar?year=2026` call (SPEC 3.1).
REAL = Path(__file__).parent.parent / "data" / "calendar" / "2026.json"


@pytest.fixture(scope="module", params=["synthetic", "real"])
def entries(request) -> list[dict]:
    """Both calendars, because the fixture was a guess and the guess was wrong.

    Every test in this file ran against the synthetic file alone until the real
    one existed. They agree on entry count, ``seasonType`` values and week
    numbering, and they disagree on what ``firstGameStart`` and ``lastGameStart``
    *mean*: CFBD sets both equal to the week's window boundaries at midnight
    Pacific, so real weeks are wall to wall, where the fixture invented multi-day
    gaps between one week's last kickoff and the next week's first.

    Nothing below may hardcode a date-to-week mapping as a result. Anything that
    needs a moment inside week N derives it from the calendar, which is a better
    test than the literals it replaces -- those asserted the fixture, not the
    resolver.
    """
    source = SYNTHETIC if request.param == "synthetic" else REAL
    return json.loads(source.read_bytes())


@pytest.fixture
def data_dir(tmp_path, entries) -> Path:
    """A `data/calendar/` directory holding whichever 2026 calendar is in play."""
    root = tmp_path / "calendar"
    root.mkdir()
    (root / "2026.json").write_bytes(json.dumps(entries).encode("utf-8"))
    return root


def _partition_of(entry) -> str:
    """The ``week=`` value one calendar entry should resolve to (SPEC 3.2)."""
    return "postseason" if entry.is_postseason else f"{entry.week:02d}"


def midweek(calendar, week: int) -> datetime:
    """A moment safely inside regular week ``week``, whichever calendar this is."""
    entry = next(
        e for e in calendar.entries if not e.is_postseason and e.week == week
    )
    return entry.first_game_start + (entry.last_game_start - entry.first_game_start) / 2


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

    @pytest.mark.parametrize("week", [1, 2, 4, 9, 12, 15])
    def test_regular_season_weeks_are_zero_padded(self, calendar, week):
        """SPEC 3.2 says ``01``-``15``, not ``1``-``15``.

        The value is a literal S3 path segment. A stray ``"4"`` opens a second
        partition for a week that already has one, and neither half is wrong
        enough to notice.

        So the assertion follows it to the segment. A ``WeekRef`` carrying ``04``
        is necessary and not sufficient: it says nothing about what the key
        builder does with it downstream, and the docstring above is a claim about
        the path, which is the only end of that trip anyone ever reads back.
        """
        expected = f"{week:02d}"
        ref = resolve(midweek(calendar, week), calendar=calendar)
        assert ref.week == expected
        assert ref.how == "calendar"

        key = snapshot_key(source="sagarin", season=2026, week=ref.week, fetched_at=KEYED_AT)
        assert key == f"raw/sagarin/season=2026/week={expected}/2026-09-16T110302Z.txt"

    def test_a_week_owns_everything_up_to_the_moment_the_next_one_opens(self, calendar):
        """Stated as the boundary, because on the real calendar there is no gap.

        The fixture invented multi-day gaps between weeks and this test used to
        assert a date inside one. CFBD's windows are wall to wall -- adjacent
        entries are exactly 60 seconds apart -- so the only version of this claim
        that holds for both calendars is about the instant before the handover.
        """
        for entry, following in zip(calendar.entries, calendar.entries[1:], strict=False):
            just_before = following.first_game_start - timedelta(seconds=1)
            assert resolve(just_before, calendar=calendar).week == _partition_of(entry)
            assert resolve(following.first_game_start, calendar=calendar).week == _partition_of(
                following
            )

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


class TestLastCompletedWeek:
    """Which regular week has finished as of ``now`` (SPEC 5.2's "N").

    The CFBD workflow pulls the week that just completed, and SPEC 11 forbids
    that arithmetic living in YAML where nothing tests it. So the calendar owns
    it, and these run over both calendars because the two disagree about what a
    week's end *is*: the synthetic fixture's ``last_game_start`` is a kickoff,
    the real one's is the window boundary a week later.

    **The empty answer is the interesting one.** On the real calendar week 1 runs
    2026-08-29 to 2026-09-08, so no week has completed on any Sunday before
    September 13. A collector that treated that as an error would turn the first
    two Sundays of the season red and teach whoever reads the alerts to ignore
    them -- which is the same failure mode SPEC 4.6 avoids by skipping rather
    than raising.
    """

    def test_nothing_has_completed_before_the_season_opens(self, calendar):
        assert last_completed_week(calendar.opens - timedelta(days=1), calendar=calendar) is None

    def test_nothing_has_completed_during_week_one(self, calendar):
        """Week 1 is in progress, so there is no completed week to pull."""
        first = calendar.entries[0]
        assert last_completed_week(first.first_game_start, calendar=calendar) is None
        assert last_completed_week(first.last_game_start, calendar=calendar) is None

    def test_week_one_completes_the_instant_after_its_window_ends(self, calendar):
        """The boundary, and it is inclusive on the wrong side deliberately.

        A week is complete once ``now`` is past its end, not at it. At exactly
        ``last_game_start`` the last game has started and has not finished.
        """
        first = calendar.entries[0]
        assert last_completed_week(first.last_game_start, calendar=calendar) is None
        assert (
            last_completed_week(
                first.last_game_start + timedelta(seconds=1), calendar=calendar
            )
            == "01"
        )

    @pytest.mark.parametrize("week", [1, 2, 4, 9, 14])
    def test_the_week_before_the_current_one_is_what_completed(self, calendar, week):
        """Mid-season: standing inside week N+1, week N is the answer."""
        following = next(
            e for e in calendar.entries if not e.is_postseason and e.week == week + 1
        )
        assert last_completed_week(
            following.first_game_start + timedelta(hours=1), calendar=calendar
        ) == f"{week:02d}"

    def test_it_is_zero_padded(self, calendar):
        """SPEC 3.2. It becomes a literal S3 path segment two calls later."""
        second = next(e for e in calendar.entries if not e.is_postseason and e.week == 2)
        assert last_completed_week(
            second.first_game_start + timedelta(hours=1), calendar=calendar
        ) == "01"

    def test_after_the_last_regular_week_it_stays_at_fifteen(self, calendar):
        """Postseason and beyond report week 15, which is the honest answer.

        Nothing here knows how to express "the bowl slate" as a CFBD week number,
        and inventing one would file real games under a wrong partition. Fifteen
        is the last regular week that actually completed; re-pulling it on a
        January Sunday is redundant rather than wrong, and SPEC 5.4 already says
        every invocation fetches for real.
        """
        assert last_completed_week(calendar.closes, calendar=calendar) == "15"

    def test_the_first_sunday_that_has_anything_to_pull(self, entries, calendar):
        """The case that motivated all of this, asserted on the real calendar only.

        The synthetic fixture's weeks are short, so it completes week 1 much
        earlier and would hide the gap this test exists to pin.
        """
        if len(entries[0].get("endDate", "")) == 0:
            pytest.skip("synthetic fixture: week windows are kickoffs, not boundaries")

        sundays = [at(2026, 8, 30, 12), at(2026, 9, 6, 12), at(2026, 9, 13, 12)]
        assert [last_completed_week(s, calendar=calendar) for s in sundays] == [
            None,
            None,
            "01",
        ]


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

    def test_false_the_day_before_the_preseason_lead_opens(self, calendar):
        """The lead is three weeks (SPEC 4.6) and it has to start somewhere.

        Every other case in this class sits days or months from an edge, which
        leaves the whole left boundary decided by no assertion at all -- a lead
        of zero, of a year, or of nothing would satisfy all of them.
        """
        opens = calendar.opens - PRESEASON_LEAD
        assert in_season(opens - timedelta(days=1), calendar=calendar) is False

    def test_true_at_the_instant_the_preseason_lead_opens(self, calendar):
        """The bound is inclusive, and this is the only test that says so.

        Fails the moment ``<=`` becomes ``<``. Sagarin publishes a starting page
        before week 1 and opening the window late loses that snapshot
        permanently, so the off-by-one here is not symmetric: a run too early is
        a skipped check, a run too late is a hole in the record.
        """
        assert in_season(calendar.opens - PRESEASON_LEAD, calendar=calendar) is True

    def test_true_the_first_full_day_inside_the_preseason_lead(self, calendar):
        assert in_season(
            calendar.opens - PRESEASON_LEAD + timedelta(days=1), calendar=calendar
        ) is True


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

    def test_the_run_exits_non_zero_after_the_write_and_not_instead_of_it(
        self, page, truncated_dir
    ):
        """The raise, and the ordering that makes it the right raise.

        ``WeekResolutionError`` alone does not distinguish the two designs this
        class exists to tell apart: a collector that resolves first and bails
        raises exactly this, at exactly this call, having stored nothing. Both
        are "the run exits non-zero", and only one of them still has the week's
        bytes afterwards. So the error is necessary and the object is the proof.
        """
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(store, page, truncated_dir, at(2026, 12, 28, 12))

        assert store.list_manifests("raw/sagarin/"), (
            "raised before writing anything: the exit code is right and the week is gone"
        )

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

    def test_a_missing_calendar_file_reaches_the_same_outcome_by_a_different_route(
        self, page, truncated_dir, tmp_path
    ):
        """SPEC 3.3 lists three causes and gives them one behaviour.

        Not one code path, though, and the difference matters to what this test
        can see. A truncated calendar loads and ``resolve`` returns
        ``how="unknown"``; a missing file never gets that far, because
        ``load_calendar`` raises and the collector turns that into the same
        ``WeekRef`` itself. Nothing here touches ``resolve``, so a ``resolve``
        that raised instead of returning would leave this test green.

        What is assertable is that the two routes are indistinguishable
        downstream, which is the behaviour SPEC 3.3 actually specifies. Both runs
        use one moment, so agreement extends to the key: same partition, same
        recorded resolution, same bytes, same object.
        """
        from cfb.storage import MemorySnapshotStore

        moment = at(2026, 12, 28, 12)
        empty = tmp_path / "empty-calendar"
        empty.mkdir()

        missing_store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(missing_store, page, empty, moment)

        truncated_store = MemorySnapshotStore()
        with pytest.raises(WeekResolutionError):
            self.run(truncated_store, page, truncated_dir, moment)

        [missing] = missing_store.list_manifests("raw/sagarin/")
        [truncated] = truncated_store.list_manifests("raw/sagarin/")

        assert missing.week == truncated.week == "unknown"
        assert missing.week_resolution == truncated.week_resolution == "unknown"
        assert missing.snapshot_key == truncated.snapshot_key
        assert missing_store.get_bytes(missing.snapshot_key) == page

    def test_a_resolvable_run_is_unaffected(self, page, data_dir, calendar):
        """The control. Without it every assertion above is satisfied by a
        collector that files everything under ``unknown`` and always raises.

        The moment comes from the calendar rather than a literal. ``2026-09-20``
        was hardcoded here and is week 04 on the synthetic fixture and week 03 on
        the real one -- the assertion was about the fixture, not about the
        collector, and only running both calendars showed it.
        """
        from cfb.storage import MemorySnapshotStore

        store = MemorySnapshotStore()
        self.run(store, page, data_dir, midweek(calendar, 4))  # must not raise

        [manifest] = store.list_manifests("raw/sagarin/")
        assert manifest.week == "04"
        assert manifest.week_resolution == "calendar"
        assert "/week=04/" in manifest.snapshot_key
        assert store.get_bytes(manifest.snapshot_key) == page
