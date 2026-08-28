"""The freshness check (SPEC-phase0 4.6).

The check exists because Sagarin going quiet is invisible. The fetch still
succeeds, the bytes still land, the manifest still says ``parse_ok``, and the
only evidence that the season stopped moving is the page's own internal date
stamp failing to advance. Everything else about that run looks healthy.

Which is why the skip paths get the most attention here. **A skip that should
have been a raise is indistinguishable from a healthy run** -- both exit 0, both
write nothing further, both leave a green workflow. The four of them are also the
paths that need no in-season capture to exercise, so they are testable today and
tested in full below: no prior-date manifest, a null stamp on either side,
same-day manifests, and the off-season guard.

**The signature is SPEC 4.6's, plus one keyword.** The spec's
``check_freshness(store, source, now)`` cannot reach a fixture calendar, so it
grew the same ``data_dir`` keyword ``fetch_sagarin`` already has, and the
arguments are keyword-only to match::

    check_freshness(*, store, source, now, data_dir=None) -> None

It lives in ``collectors/sagarin.py``, where SPEC 1 puts freshness.

**The log vocabulary is load-bearing, and it lives in ``cfb.logging``.**
``-> None`` leaves no return value to assert on, so the log line is the only
observable that separates "skipped, and said so" from "silently did nothing" --
the distinction this whole file is about. The strings are imported from
``src/cfb/logging.py`` and recorded in SPEC 4.6, so a test and an implementation
cannot drift into two private vocabularies that both look right in isolation.

**What is provisional.** ``TestTheComparisonItself`` needs an in-season page and
none exists: the golden capture is the 2026 STARTING page (§4.7). Those tests run
against a synthetic page built by rewriting the capture's title line, so an
in-season *title* sits over preseason *data* -- all four rating columns equal,
every record 0-0. That is enough to drive the stamp end to end through
``parse_page_date_stamp``, ``fetch_sagarin`` and the manifest, which is the part
the freshness check reads. It is not evidence about real in-season row shapes,
in-season HFA, or the real stamp format, and the assertions marked PROVISIONAL
below should be re-run against a real capture the first Tuesday one exists.
"""

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from cfb.collectors.sagarin import SOURCE_URL, check_freshness, fetch_sagarin
from cfb.errors import StaleSourceError
from cfb.logging import (
    EVENT_FRESHNESS,
    REASON_NO_PAGE_DATE_STAMP,
    REASON_NO_PRIOR_MANIFEST,
    REASON_NOT_IN_SEASON,
    RESULT_OK,
    RESULT_SKIP,
)
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest
from cfb.storage import MemorySnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"
SYNTHETIC_CALENDAR = FIXTURES / "calendar_2026_synthetic.json"

#: The 2026 STARTING title line, reprinted every 10 rows through the capture.
PRESEASON_TITLE = b"2026 College Football STARTING ratings"

# --- the log vocabulary, now owned by src/cfb/logging.py ----------------------
# Imported rather than restated: a test that spells the strings out itself passes
# against an implementation that logs something else entirely, which is the one
# thing these assertions exist to rule out. The three names below are local
# spellings of the imported constants, kept so the assertions read the same.
EVENT = f"event={EVENT_FRESHNESS}"
REASON_NO_PRIOR = REASON_NO_PRIOR_MANIFEST
REASON_NO_STAMP = REASON_NO_PAGE_DATE_STAMP
REASON_OFF_SEASON = REASON_NOT_IN_SEASON


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


#: Tuesday of week 04 in the synthetic calendar, and in season. SPEC 11 runs the
#: real collection on a Tuesday, which is nobody's game day.
TUESDAY_W4 = at(2026, 9, 22, 12)
TUESDAY_W3 = at(2026, 9, 15, 12)


def in_season_page(stamp: str = "September 15, 2026") -> bytes:
    """The golden capture with an in-season title line. See the module docstring.

    Byte-level replacement on purpose: the capture is CRLF with the HTML wrapper
    intact (§4.7) and decoding it here to build the variant would quietly
    normalize both.
    """
    raw = GOLDEN.read_bytes()
    assert PRESEASON_TITLE in raw, "the golden capture's title line changed; this helper is stale"
    title = b"2026 College Football ratings  through games of " + stamp.encode()
    return raw.replace(PRESEASON_TITLE, title)


@pytest.fixture
def calendar_dir(tmp_path) -> Path:
    root = tmp_path / "calendar"
    root.mkdir()
    (root / "2026.json").write_bytes(SYNTHETIC_CALENDAR.read_bytes())
    return root


@pytest.fixture
def store() -> MemorySnapshotStore:
    return MemorySnapshotStore()


def seed(store, *, fetched_at: datetime, stamp: date | None, week: str) -> Manifest:
    """Write one post-parse manifest, with no snapshot bytes behind it.

    The freshness check reads manifests and nothing else (SPEC 4.6: previous state
    is derived from the manifests in S3, with no state file to drift), so a
    manifest alone is a complete fixture for it. ``week`` is passed rather than
    resolved because these dates deliberately include ones the calendar and the
    partition scheme disagree about.
    """
    key = snapshot_key(source="sagarin", season=2026, week=week, fetched_at=fetched_at)
    manifest = Manifest(
        schema_version=1,
        source="sagarin",
        resource="ratings",
        source_url=SOURCE_URL,
        http_status=200,
        sha256="0" * 64,
        bytes=148793,
        encoding="cp1252",
        fetched_at=fetched_at,
        season=2026,
        week=week,
        week_resolution="calendar",
        snapshot_key=key,
        parse_ok=True,
        page_date_stamp=stamp,
        page_state="preseason" if stamp is None else "in-season",
    )
    store.put_json(manifest_key(key), manifest.model_dump(mode="json"))
    return manifest


def logged(capsys) -> dict[str, str]:
    """The key=value pairs of the last freshness line on stdout.

    Asserts something was logged at all. A check that skips in silence is the
    failure this file exists to catch: it is byte-identical to a healthy run from
    outside the process.
    """
    lines = [line for line in capsys.readouterr().out.splitlines() if EVENT in line]
    assert lines, (
        "check_freshness logged nothing; a silent skip cannot be told apart from a "
        "comparison that ran and passed (SPEC 4.6)"
    )
    return dict(pair.split("=", 1) for pair in lines[-1].split() if "=" in pair)


class TestSkipsThatMustAnnounceThemselves:
    """The paths where passing is correct and silence is not."""

    def test_no_prior_dated_manifest_passes_and_says_so(self, store, calendar_dir, capsys):
        """The first ever run. Today's snapshot exists; nothing precedes it."""
        seed(store, fetched_at=TUESDAY_W4, stamp=date(2026, 9, 21), week="04")

        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

        log = logged(capsys)
        assert log["result"] == RESULT_SKIP
        assert log["reason"] == REASON_NO_PRIOR

    def test_an_empty_store_passes_and_says_so(self, store, calendar_dir, capsys):
        """No snapshot at all -- ``check-freshness`` run before any ``fetch``.

        SPEC 4.6 does not name this case; SPEC 8 makes it reachable, because the
        two are separate CLI commands and nothing orders them. Passing is the only
        answer that does not turn an empty bucket into a red workflow forever, so
        the reason string is left unasserted -- only the skip is contractual here.
        """
        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

        assert logged(capsys)["result"] == RESULT_SKIP

    def test_a_null_stamp_on_todays_page_passes_and_says_so(self, store, calendar_dir, capsys):
        """The preseason page carries no stamp at all (§4.7), so there is nothing to compare.

        Driven through ``fetch_sagarin`` with the real golden capture rather than a
        hand-built manifest: ``page_date_stamp=None`` has to arrive here the way it
        arrives in production, out of ``parse_page_date_stamp`` on a page that
        genuinely has no date on it.
        """
        seed(store, fetched_at=TUESDAY_W3, stamp=date(2026, 9, 14), week="03")
        fetch_sagarin(
            store=store,
            now=TUESDAY_W4,
            fetch=GOLDEN.read_bytes,
            data_dir=calendar_dir,
        )
        capsys.readouterr()

        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

        log = logged(capsys)
        assert log["result"] == RESULT_SKIP
        assert log["reason"] == REASON_NO_STAMP

    def test_a_null_stamp_on_the_prior_page_passes_and_says_so(self, store, calendar_dir, capsys):
        """SPEC 4.6 says *either* stamp missing, and this is the other one.

        It is the ordinary shape of the first in-season week: last Tuesday's
        snapshot was the preseason page and carries no stamp, this Tuesday's is the
        first page that does. Comparing a date against nothing is not a comparison,
        and raising on it would make the season's first real page the alert.
        """
        seed(store, fetched_at=TUESDAY_W3, stamp=None, week="03")
        seed(store, fetched_at=TUESDAY_W4, stamp=date(2026, 9, 21), week="04")

        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

        log = logged(capsys)
        assert log["result"] == RESULT_SKIP
        assert log["reason"] == REASON_NO_STAMP


class TestWhichManifestIsCompared:
    """SPEC 4.6: the newest manifest whose ``fetched_at`` date is strictly earlier than today.

    Both tests below are built so that the right answer and the wrong one give
    opposite outcomes. Asserting only "it passed" would be satisfied by an
    implementation that compared against the wrong manifest and happened to agree.
    """

    def test_a_same_day_manifest_is_not_the_comparison(self, store, calendar_dir):
        """A manual re-run compares against last Tuesday, exactly as the scheduled run did.

        Today already holds an earlier snapshot with the same stamp as the current
        one -- which is what a re-run an hour later looks like. Comparing against it
        finds an unchanged stamp and raises, turning every re-run red. Comparing
        against last Tuesday finds the stamp advanced.
        """
        seed(store, fetched_at=TUESDAY_W3, stamp=date(2026, 9, 14), week="03")
        seed(store, fetched_at=at(2026, 9, 22, 8), stamp=date(2026, 9, 21), week="04")
        seed(store, fetched_at=TUESDAY_W4, stamp=date(2026, 9, 21), week="04")

        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

    def test_a_same_day_manifest_cannot_mask_a_stale_source(self, store, calendar_dir):
        """The mirror, and the one that matters: same-day noise must not suppress the alert.

        Last Tuesday's stamp is unchanged from today's, which is the stale case. An
        earlier snapshot from today carries an older stamp, so an implementation
        that compares against it sees the stamp "advance" and stays green while the
        source is dead.
        """
        seed(store, fetched_at=TUESDAY_W3, stamp=date(2026, 9, 21), week="03")
        seed(store, fetched_at=at(2026, 9, 22, 8), stamp=date(2026, 9, 14), week="04")
        seed(store, fetched_at=TUESDAY_W4, stamp=date(2026, 9, 21), week="04")

        with pytest.raises(StaleSourceError):
            check_freshness(store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir)

    def test_the_newest_of_several_prior_dates_wins(self, store, calendar_dir):
        """Not merely "some earlier manifest" -- the newest one.

        Two weeks ago the stamp was different, so comparing against *that* would
        report an advance and pass. Comparing against last Tuesday reports the truth.
        The day count in the message is the second half of the assertion: it is only
        7 if the right manifest was chosen.
        """
        seed(store, fetched_at=at(2026, 9, 8, 12), stamp=date(2026, 9, 7), week="02")
        seed(store, fetched_at=TUESDAY_W3, stamp=date(2026, 9, 21), week="03")
        seed(store, fetched_at=TUESDAY_W4, stamp=date(2026, 9, 21), week="04")

        with pytest.raises(StaleSourceError) as exc:
            check_freshness(store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir)

        assert re.search(r"\b7\b", str(exc.value)), (
            f"expected 7 days elapsed against the 09-15 manifest, got: {exc.value}"
        )


class TestTheOffSeasonGuard:
    def test_the_check_does_not_run_at_all_off_season(self, calendar_dir, capsys):
        """SPEC 4.6: it runs only while ``in_season``. Not "runs and passes".

        Sagarin does not update from roughly February through August, and a check
        that ran anyway would raise every week of it -- alerting through the
        off-season is how alerting dies. The store refuses every call, so this
        fails if the guard is anywhere later than first.
        """

        class ExplodingStore:
            def _boom(self, *args, **kwargs):
                raise AssertionError(
                    "check_freshness touched the store off-season; SPEC 4.6 gates on "
                    "in_season before any comparison happens"
                )

            put_bytes = put_json = get_bytes = list_manifests = _boom

        check_freshness(
            store=ExplodingStore(),
            source="sagarin",
            now=at(2027, 5, 15, 12),
            data_dir=calendar_dir,
        )  # must not raise

        log = logged(capsys)
        assert log["result"] == RESULT_SKIP
        assert log["reason"] == REASON_OFF_SEASON


class TestTheComparisonItself:
    """PROVISIONAL -- see the module docstring.

    These two run against a synthetic in-season page: the golden capture with its
    title line rewritten. The stamp is real in the sense that it is parsed off a
    page by the real parser and carried into a real manifest by ``fetch_sagarin``,
    which is the whole of what SPEC 4.6 reads. Everything below the title line is
    still preseason data. Re-run both against a real capture once one lands.
    """

    def _run(self, store, calendar_dir, *, stamp: str, now: datetime) -> None:
        fetch_sagarin(
            store=store,
            now=now,
            fetch=lambda: in_season_page(stamp),
            data_dir=calendar_dir,
        )

    def test_an_advanced_stamp_passes(self, store, calendar_dir, capsys):
        self._run(store, calendar_dir, stamp="September 14, 2026", now=TUESDAY_W3)
        self._run(store, calendar_dir, stamp="September 21, 2026", now=TUESDAY_W4)
        capsys.readouterr()

        check_freshness(
            store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir
        )  # must not raise

        assert logged(capsys)["result"] == RESULT_OK

    def test_an_unchanged_stamp_raises_naming_both_stamps_and_the_days_elapsed(
        self, store, calendar_dir
    ):
        """The alert, and what has to be in it.

        A ``StaleSourceError`` that says only "stale" sends whoever reads the red
        run back to S3 to work out what stalled and for how long. The stamp and the
        elapsed days are the two facts that make the run self-explanatory, and
        SPEC 4.6 names both.
        """
        self._run(store, calendar_dir, stamp="September 14, 2026", now=TUESDAY_W3)
        self._run(store, calendar_dir, stamp="September 14, 2026", now=TUESDAY_W4)

        with pytest.raises(StaleSourceError) as exc:
            check_freshness(store=store, source="sagarin", now=TUESDAY_W4, data_dir=calendar_dir)

        message = str(exc.value)
        assert message.count("2026-09-14") >= 2, (
            f"expected both stamps named as ISO dates, got: {message}"
        )
        assert re.search(r"\b7\b", message), f"expected the days elapsed, got: {message}"


class TestTheFixtureItself:
    """Guards the synthetic page, so a failure above is never this helper's fault."""

    def test_the_synthetic_page_reads_as_in_season_with_the_stamp_asked_for(self):
        from cfb.collectors.sagarin import decode_page
        from cfb.parsers.sagarin_ratings import parse_page_date_stamp, parse_page_state

        text, _ = decode_page(in_season_page("September 21, 2026"))
        assert parse_page_state(text) == "in-season"
        assert parse_page_date_stamp(text) == date(2026, 9, 21)

    def test_the_golden_capture_still_has_no_stamp(self):
        """The other half: the null-stamp tests are only meaningful while this holds."""
        from cfb.collectors.sagarin import decode_page
        from cfb.parsers.sagarin_ratings import parse_page_date_stamp, parse_page_state

        text, _ = decode_page(GOLDEN.read_bytes())
        assert parse_page_state(text) == "preseason"
        assert parse_page_date_stamp(text) is None

    def test_the_synthetic_calendar_puts_both_tuesdays_in_season(self, calendar_dir):
        from cfb.calendar import in_season, load_calendar

        calendar = load_calendar(2026, data_dir=calendar_dir)
        assert in_season(TUESDAY_W3, calendar=calendar) is True
        assert in_season(TUESDAY_W4, calendar=calendar) is True
        assert (TUESDAY_W4 - TUESDAY_W3) == timedelta(days=7)

    def test_the_seed_helper_writes_a_manifest_the_store_can_read_back(self, store):
        written = seed(store, fetched_at=TUESDAY_W3, stamp=date(2026, 9, 14), week="03")
        [read_back] = store.list_manifests("raw/sagarin/")
        assert read_back == written
        assert json.loads(store.get_bytes(manifest_key(written.snapshot_key)))["parse_ok"] is True
