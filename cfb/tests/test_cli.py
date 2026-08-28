"""The `cfb` console script (SPEC-phase0 section 8), and the error contract of section 9.

Four commands. The two `crosswalk` subcommands SPEC 8 lists wait on section 6,
which does not exist; registering them now would give a workflow a command that
exits non-zero for a reason unrelated to the data.

**The error contract gets the most assertions here, because the CLI is the only
place it is observable.** SPEC 9 says any `CfbError` is exit 1 with a message on
stderr, that nothing is caught and demoted to a warning, and that there is no
exit code meaning partially ok. Every one of those is a claim about this layer:
the collectors raise, and until something catches, "exit 1 with a message" is
unenforced. So the tests below drive every `CfbError` subclass through the
command that can raise it and assert the same three things each time -- code 1, a
message a human can act on, and no traceback.

The corollary gets a test too. A *non*-`CfbError` must **not** be converted. A
`KeyError` reaching this layer is a bug in the package, and a bug wearing a clean
exit code is a bug nobody finds. SPEC 9 promises an exit code for `CfbError`, not
a blanket catch, and the difference is deliberate.

**Signature is a proposal.** SPEC 8 gives the command surface and the principle --
"a thin shell over functions that take their dependencies as arguments, because a
command that constructs its own client and reads its own credential cannot be
tested without both" -- but no signature::

    main(argv: list[str] | None = None, *, now=None, fetch=None) -> int

`main` returns the exit code rather than calling `sys.exit`, so a test can assert
on it without catching `SystemExit`; the console-script wrapper does the exiting.
`now` and `fetch` are the two seams the principle above requires: without them
every test in this file would need a clock and the network.

**`--store` is resolved, not injected**, because the URL scheme is the thing worth
testing. `file://` builds a `FileSnapshotStore` and needs no AWS, so the CLI's own
store resolution runs for real in every test below.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb.cli import main
from cfb.errors import (
    CallBudgetExceeded,
    CfbError,
    DuplicateRankError,
    EncodingError,
    FetchError,
    ParseError,
    SnapshotExistsError,
    SnapshotNotFoundError,
    StaleSourceError,
    UnmappedTeamError,
    ValidationError,
    WeekResolutionError,
)

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"
SYNTHETIC_CALENDAR = FIXTURES / "calendar_2026_synthetic.json"

#: Tuesday of week 04, in season on the synthetic calendar. SPEC 11's real
#: Sagarin run is a Tuesday.
TUESDAY_W4 = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
#: Deep in the off-season, where the `in_season` guard closes.
IN_MAY = datetime(2027, 5, 15, 12, 0, 0, tzinfo=UTC)

#: Every error SPEC 9 declares, with an instance to raise. `CfbError` itself is
#: in the list on purpose: the clause is written against the base class, and a
#: CLI that enumerated subclasses instead would miss one added later.
CFB_ERRORS = {
    "CfbError": CfbError("something went wrong"),
    "FetchError": FetchError("sagarin.com redirected 302 to https"),
    "EncodingError": EncodingError("no candidate decoded the page"),
    "SnapshotExistsError": SnapshotExistsError("raw/... already exists"),
    "SnapshotNotFoundError": SnapshotNotFoundError("no object at raw/..."),
    "ParseError": ParseError("line 412: unrecognised row"),
    "DuplicateRankError": DuplicateRankError("rank 43 appears twice"),
    "ValidationError": ValidationError("line 42: 1 validation error for TeamRating"),
    "UnmappedTeamError": UnmappedTeamError("no crosswalk entry for 'Southern California'"),
    "WeekResolutionError": WeekResolutionError("season/week could not be resolved"),
    "StaleSourceError": StaleSourceError("page_date_stamp has not advanced, 7 days elapsed"),
    "CallBudgetExceeded": CallBudgetExceeded("per-run call budget of 25 is spent"),
}
ERROR_IDS = list(CFB_ERRORS)


@pytest.fixture
def store_root(tmp_path) -> Path:
    return tmp_path / "local-snapshots"


@pytest.fixture
def store_url(store_root) -> str:
    return f"file://{store_root.as_posix()}"


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    """A `data/calendar/` the CLI finds without being told where it is.

    `fetch_sagarin` and `check_freshness` both take `data_dir`, but SPEC 8's
    command surface has no flag for it -- the committed calendar is meant to be
    found. So the CLI resolves it, and this points that resolution at a fixture.
    """
    root = tmp_path / "data" / "calendar"
    root.mkdir(parents=True)
    (root / "2026.json").write_bytes(SYNTHETIC_CALENDAR.read_bytes())
    monkeypatch.setenv("CFB_DATA_DIR", str(tmp_path / "data"))
    return root


@pytest.fixture
def page() -> bytes:
    return GOLDEN.read_bytes()


def run(argv, **kwargs) -> int:
    return main(argv, **kwargs)


def written(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def snapshots(root: Path) -> list[Path]:
    return [p for p in written(root) if not p.name.endswith(".meta.json")]


def manifests(root: Path) -> list[dict]:
    return [json.loads(p.read_bytes()) for p in written(root) if p.name.endswith(".meta.json")]


class TestTheErrorContract:
    """SPEC 9, and the reason this file exists.

    Three claims, asserted for every declared error rather than for a
    representative one. "Representative" is how the one subclass that takes a
    different path gets missed, and the whole hierarchy exists because each of
    these means something different upstream.
    """

    @pytest.mark.parametrize("name", ERROR_IDS, ids=ERROR_IDS)
    def test_every_cfb_error_exits_one(self, name, monkeypatch, store_url, data_dir, capsys):
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(CFB_ERRORS[name]))

        assert run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4) == 1

    @pytest.mark.parametrize("name", ERROR_IDS, ids=ERROR_IDS)
    def test_every_cfb_error_puts_its_message_on_stderr(
        self, name, monkeypatch, store_url, data_dir, capsys
    ):
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(CFB_ERRORS[name]))

        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

        captured = capsys.readouterr()
        assert str(CFB_ERRORS[name]) in captured.err
        assert str(CFB_ERRORS[name]) not in captured.out, (
            "the failure belongs on stderr; stdout is the structured log"
        )

    @pytest.mark.parametrize("name", ERROR_IDS, ids=ERROR_IDS)
    def test_no_cfb_error_prints_a_traceback(
        self, name, monkeypatch, store_url, data_dir, capsys
    ):
        """A traceback is what an unhandled crash looks like.

        SPEC 9 makes every one of these an expected outcome with an exit code, so
        a traceback here would say "this tool broke" about a case the tool
        handles -- and bury the message that says what to do next.
        """
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(CFB_ERRORS[name]))

        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert "Traceback" not in captured.out

    @pytest.mark.parametrize("name", ERROR_IDS, ids=ERROR_IDS)
    def test_the_error_class_is_named_so_the_failure_is_greppable(
        self, name, monkeypatch, store_url, data_dir, capsys
    ):
        """SPEC 11 makes the Actions log the alert. The class is what says which
        of a dozen documented failures this run hit.
        """
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(CFB_ERRORS[name]))

        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

        assert name in capsys.readouterr().err

    def test_a_non_cfb_error_is_not_converted(self, monkeypatch, store_url, data_dir):
        """The corollary, and the one that keeps the contract honest.

        SPEC 9 promises an exit code for `CfbError`, not a blanket catch. A
        `KeyError` at this layer is a bug in the package; giving it a clean exit 1
        with a one-line message would hide the traceback that identifies it, and
        would make "exit 1" mean both "the source is stale" and "we have a bug".
        """
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(KeyError("predictor")))

        with pytest.raises(KeyError):
            run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

    def test_nothing_is_demoted_to_a_warning(self, monkeypatch, store_url, data_dir, capsys):
        """SPEC 9: nothing is caught to log-and-continue.

        The failure this project is built to prevent is a validation error
        surviving as a warning while the run goes green.
        """
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(ParseError("line 412")))

        code = run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

        assert code == 1
        assert "warn" not in capsys.readouterr().err.lower()

    def test_a_failed_run_writes_nothing(self, monkeypatch, store_url, store_root, data_dir):
        """There is no exit code meaning partially ok, and no partial artifact either."""
        monkeypatch.setattr("cfb.cli.fetch_sagarin", _raiser(FetchError("no route to host")))

        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4)

        assert not store_root.exists() or written(store_root) == []


class TestFetchSagarin:
    def test_it_writes_a_snapshot_and_a_manifest(self, store_url, store_root, data_dir, page):
        code = run(
            ["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page
        )

        assert code == 0
        assert len(snapshots(store_root)) == 1
        assert len(manifests(store_root)) == 1

    def test_the_snapshot_is_the_bytes_verbatim(self, store_url, store_root, data_dir, page):
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)

        [snapshot] = snapshots(store_root)
        assert snapshot.read_bytes() == page

    def test_the_manifest_records_the_week_the_calendar_resolved(
        self, store_url, store_root, data_dir, page
    ):
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)

        [manifest] = manifests(store_root)
        assert manifest["week"] == "04"
        assert manifest["week_resolution"] == "calendar"
        assert manifest["parse_ok"] is True

    def test_off_season_exits_zero_without_fetching(
        self, store_url, store_root, data_dir, capsys
    ):
        """SPEC 11: the collect workflows exit 0 immediately when out of season.

        That is the entire off-season story -- no runs to mute, no suppression
        state, no false alarms from February to August. The fetch callable raises
        if it is reached, so this fails if the guard runs after the fetch.
        """
        code = run(
            ["fetch", "sagarin", "--store", store_url],
            now=IN_MAY,
            fetch=_raiser(AssertionError("fetched off-season")),
        )

        assert code == 0
        assert not store_root.exists() or written(store_root) == []

    def test_force_bypasses_the_off_season_guard(
        self, store_url, store_root, data_dir, page
    ):
        """SPEC 8: `--force` exists for manual testing, which is what makes the
        guard safe to have -- a gate with no override becomes a reason to edit code.
        """
        code = run(
            ["fetch", "sagarin", "--store", store_url, "--force"],
            now=IN_MAY,
            fetch=lambda: page,
        )

        assert code == 0
        assert len(snapshots(store_root)) == 1

    def test_an_unloadable_calendar_does_not_stop_the_fetch(
        self, tmp_path, monkeypatch, store_url, store_root, page, capsys
    ):
        """SPEC 3.3, at the layer that can most easily break it.

        A Sagarin week not captured is gone permanently, so a calendar problem is
        never a reason to skip the fetch. `fetch_sagarin` is careful about this --
        it files under `week=unknown` and raises *after* the write -- and a guard
        in front of it that raises first quietly undoes all of that.

        Found by running the CLI for real: with no committed calendar the guard
        exited 1 having fetched nothing, which is the clean failure SPEC 3.3
        explicitly prefers a messy artifact to.
        """
        monkeypatch.setenv("CFB_DATA_DIR", str(tmp_path / "no-data"))

        code = run(
            ["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page
        )

        assert code == 1, "the run still owes a non-zero exit (SPEC 3.3)"
        [snapshot] = snapshots(store_root)
        assert snapshot.read_bytes() == page, "the bytes are the irreplaceable part"
        assert "/week=unknown/" in snapshot.as_posix()
        assert manifests(store_root)[0]["week_resolution"] == "unknown"

    def test_the_off_season_guard_still_closes_when_the_calendar_loads(
        self, store_url, store_root, data_dir
    ):
        """The control for the test above.

        "Proceed when the calendar is unreadable" must not become "proceed
        always" -- that would delete the off-season story SPEC 11 relies on.
        """
        code = run(
            ["fetch", "sagarin", "--store", store_url],
            now=IN_MAY,
            fetch=_raiser(AssertionError("fetched off-season")),
        )

        assert code == 0
        assert not store_root.exists() or written(store_root) == []

    def test_the_run_is_logged(self, store_url, data_dir, page, capsys):
        """SPEC 9: structured key=value to stdout, so an Actions log is greppable."""
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)

        assert re.search(r"^event=\S+", capsys.readouterr().out, re.M)


class TestFetchCfbd:
    """The seam here is the client, not a zero-argument callable: SPEC 5.1 puts the
    budget inside it, so a command that built its own would be unbudgeted.
    """

    def test_a_resource_is_required(self, store_url, data_dir):
        with pytest.raises(SystemExit) as excinfo:
            run(["fetch", "cfbd", "--store", store_url], now=TUESDAY_W4)

        assert excinfo.value.code == 2, "argparse reports a usage error, not a CfbError"

    @pytest.mark.parametrize("resource", ["games", "lines", "teams", "calendar"])
    def test_every_spec_5_2_resource_is_accepted(self, store_url, data_dir, resource):
        """The four calls of SPEC 5.2 and nothing else. An unknown resource is a
        usage error, not a request that finds out from the vendor.
        """
        with pytest.raises(SystemExit) as excinfo:
            run(["fetch", "cfbd", "--resource", "rosters", "--store", store_url])
        assert excinfo.value.code == 2

    def test_a_week_scoped_resource_lands_under_that_week(
        self, store_url, store_root, data_dir
    ):
        code = run(
            ["fetch", "cfbd", "--resource", "games", "--week", "4", "--season", "2026",
             "--store", store_url],
            now=TUESDAY_W4,
            fetch=_json_response(b'[{"id": 1}]'),
        )

        assert code == 0
        [snapshot] = snapshots(store_root)
        assert "/week=04/games/" in snapshot.as_posix()

    def test_a_season_level_resource_lands_under_week_season(
        self, store_url, store_root, data_dir
    ):
        """SPEC 3.2's `season` partition, which no date resolves to."""
        code = run(
            ["fetch", "cfbd", "--resource", "teams", "--season", "2026", "--store", store_url],
            now=TUESDAY_W4,
            fetch=_json_response(b'[{"school": "Ohio State"}]'),
        )

        assert code == 0
        [snapshot] = snapshots(store_root)
        assert "/week=season/teams/" in snapshot.as_posix()


class TestCheckFreshness:
    def test_it_exits_zero_when_there_is_nothing_to_compare(
        self, store_url, data_dir, page, capsys
    ):
        """The first run: a snapshot exists and nothing precedes it."""
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)
        capsys.readouterr()

        assert run(["check-freshness", "sagarin", "--store", store_url], now=TUESDAY_W4) == 0
        assert "result=skip" in capsys.readouterr().out

    def test_as_of_overrides_the_clock(self, store_url, data_dir, page, capsys):
        """SPEC 8's `--as-of`, and SPEC 11's verification step, which runs the
        check against last week's date on purpose to prove it can go red.
        """
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)
        capsys.readouterr()

        # 2027-05-15 belongs to season 2026: a date before July belongs to the
        # season that started the previous August, and that is the calendar the
        # fixture provides. 2026-05-15 would ask for a 2025 calendar and raise.
        code = run(
            ["check-freshness", "sagarin", "--store", store_url, "--as-of", "2027-05-15"]
        )

        assert code == 0
        assert "reason=not_in_season" in capsys.readouterr().out

    def test_a_bad_as_of_is_a_usage_error(self, store_url, data_dir):
        with pytest.raises(SystemExit) as excinfo:
            run(["check-freshness", "sagarin", "--store", store_url, "--as-of", "last-tuesday"])
        assert excinfo.value.code == 2


class TestReplay:
    """SPEC 8: parse and validate an existing snapshot. No network, no write."""

    def test_it_reparses_a_stored_snapshot(self, store_url, store_root, data_dir, page, capsys):
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)
        [snapshot] = snapshots(store_root)
        key = snapshot.relative_to(store_root).as_posix()
        capsys.readouterr()

        assert run(["replay", key, "--store", store_url]) == 0
        assert "266" in capsys.readouterr().out, "the team count is the point of replaying"

    def test_it_writes_nothing(self, store_url, store_root, data_dir, page):
        """A re-parse is not a capture. SPEC 5.4 is explicit that re-running after
        a parser fix is not the fetch command's job, and the reason is that a
        replay writing a new snapshot would forge a capture that never happened.
        """
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)
        [snapshot] = snapshots(store_root)
        key = snapshot.relative_to(store_root).as_posix()
        before = {p: p.read_bytes() for p in written(store_root)}

        run(["replay", key, "--store", store_url])

        assert {p: p.read_bytes() for p in written(store_root)} == before

    def test_a_missing_key_exits_one(self, store_url, store_root, data_dir, capsys):
        code = run(["replay", "raw/sagarin/season=2026/week=04/nope.txt", "--store", store_url])

        assert code == 1
        assert "SnapshotNotFoundError" in capsys.readouterr().err

    def test_it_never_reaches_the_network(self, store_url, store_root, data_dir, page):
        """`fetch` is rejected outright rather than ignored: a replay that
        accepted a fetcher would be one refactor away from using it.
        """
        run(["fetch", "sagarin", "--store", store_url], now=TUESDAY_W4, fetch=lambda: page)
        [snapshot] = snapshots(store_root)
        key = snapshot.relative_to(store_root).as_posix()

        assert run(["replay", key, "--store", store_url], fetch=_raiser(AssertionError())) == 0


class TestTheStoreFlag:
    def test_file_urls_write_to_that_directory(self, tmp_path, data_dir, page):
        root = tmp_path / "somewhere-else"
        run(
            ["fetch", "sagarin", "--store", f"file://{root.as_posix()}"],
            now=TUESDAY_W4,
            fetch=lambda: page,
        )

        assert len(snapshots(root)) == 1

    def test_an_unknown_scheme_is_a_usage_error(self, data_dir):
        with pytest.raises(SystemExit) as excinfo:
            run(["fetch", "sagarin", "--store", "ftp://example.com"], now=TUESDAY_W4)
        assert excinfo.value.code == 2

    def test_the_default_store_is_the_spec_8_bucket(self):
        """Not exercised against AWS here -- asserted so the default cannot drift
        to something a scheduled run would silently write to instead.
        """
        from cfb.cli import DEFAULT_STORE

        assert DEFAULT_STORE == "s3://travispollard-cfb-data"


class TestTheCommandSurface:
    @pytest.mark.parametrize(
        "argv",
        [
            ["fetch", "sagarin"],
            ["fetch", "cfbd", "--resource", "games"],
            ["check-freshness", "sagarin"],
            ["replay", "some/key.txt"],
        ],
        ids=["fetch-sagarin", "fetch-cfbd", "check-freshness", "replay"],
    )
    def test_spec_8_commands_all_parse(self, argv, monkeypatch):
        """Parsing only. Each is driven properly elsewhere; this is the guard
        against a command being renamed out from under SPEC 11's workflows.
        """
        from cfb.cli import build_parser

        build_parser().parse_args(argv)

    @pytest.mark.parametrize("argv", [["crosswalk", "bootstrap"], ["crosswalk", "verify"]])
    def test_the_crosswalk_commands_are_not_registered_yet(self, argv):
        """SPEC 8 lists them and section 6 does not exist.

        Registering a command whose module is missing gives a workflow something
        that exits non-zero for a reason unrelated to the data.
        """
        from cfb.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(argv)

    def test_no_argv_is_a_usage_error_not_a_crash(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            run([])
        assert excinfo.value.code == 2


def _raiser(exc):
    def raise_it(*args, **kwargs):
        raise exc

    return raise_it


def _json_response(body: bytes):
    """A CFBD seam callable returning one canned 200."""
    import httpx

    def fetch(path: str, params: dict) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return fetch
