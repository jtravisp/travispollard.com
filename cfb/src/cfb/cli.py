"""The ``cfb`` console script (SPEC-phase0 section 8).

A thin shell, deliberately. Every command below resolves a store, works out a
moment, and calls one function that takes its dependencies as arguments -- because
a command that constructs its own client and reads its own credential cannot be
tested without both, and SPEC 11 needs the workflows to call exactly the commands
a human calls locally. That is what makes a red run reproducible.

**The error contract is this module's real job.** SPEC 9 says any ``CfbError`` is
exit 1 with a message on stderr, that nothing is caught and demoted to a warning,
and that no exit code means partially ok. Nothing enforced any of that until
something caught: the collectors raise and, before this module, the raise went
straight to the interpreter as a traceback.

The corollary is deliberate and narrow: a **non**-``CfbError`` is not converted.
A ``KeyError`` reaching this layer is a bug in the package, and a bug wearing a
clean exit code is a bug nobody finds. SPEC 9 promises an exit code for
``CfbError``, not a blanket catch. So exit 1 means "a documented failure
happened", and a traceback means "this tool is broken" -- two different things
that a wider catch would merge.

SPEC 8 also lists ``crosswalk verify``; SPEC-phase1 9 lists ``elo seed``,
``predict``, ``score``, ``publish`` and ``note``. None of those are registered:
a command whose module is missing gives a workflow something that exits non-zero
for a reason unrelated to the data. ``elo replay`` is here because SPEC-phase1 11
step 5 is a command a human runs, and it is the check that keeps the stored Elo
state a cache rather than a second source of truth.
"""

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

from cfb.calendar import in_season, last_completed_week, load_calendar
from cfb.collectors.cfbd import CfbdClient, fetch_cfbd, http_fetch
from cfb.collectors.sagarin import check_freshness, decode_page, fetch_sagarin
from cfb.errors import CfbError, SeedStateError, WeekResolutionError
from cfb.logging import (
    EVENT_ELO_REPLAY,
    EVENT_ELO_STATE,
    EVENT_ELO_VERIFY,
    EVENT_SNAPSHOT_WRITTEN,
    REASON_NO_COMPLETED_WEEK,
    REASON_NO_STORED_STATE,
    REASON_NOT_IN_SEASON,
    RESULT_OK,
    RESULT_SKIP,
    log,
)
from cfb.models import SagarinSnapshot, validating
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)
from cfb.storage import FileSnapshotStore, S3SnapshotStore

__all__ = ["DEFAULT_STORE", "build_parser", "main"]

#: SPEC 8. The bucket a scheduled run writes to when nothing says otherwise.
DEFAULT_STORE = "s3://travispollard-cfb-data"

#: SPEC 2: us-east-1, passed explicitly and never inherited from ambient env.
REGION = "us-east-1"

#: SPEC 5.2's four calls, and nothing else. An unknown resource is a usage error
#: rather than a request that finds out from the vendor at the cost of quota.
RESOURCES = ("games", "lines", "teams", "calendar")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cfb", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="capture a raw snapshot")
    sources = fetch.add_subparsers(dest="source", required=True)

    sagarin = sources.add_parser("sagarin", help="the Sagarin ratings page")
    _add_store(sagarin)
    sagarin.add_argument(
        "--force",
        action="store_true",
        help="bypass the in_season guard, for manual testing",
    )

    cfbd = sources.add_parser("cfbd", help="one CFBD resource")
    _add_store(cfbd)
    cfbd.add_argument("--resource", choices=RESOURCES, required=True)
    cfbd.add_argument(
        "--week",
        type=int,
        help="games and lines only; defaults to the week that just completed",
    )
    cfbd.add_argument("--season", type=int)
    cfbd.add_argument(
        "--force",
        action="store_true",
        help="bypass the in_season guard, for manual testing",
    )

    freshness = commands.add_parser(
        "check-freshness", help="has the source's own date stamp advanced"
    )
    freshness.add_argument("source", choices=["sagarin"])
    _add_store(freshness)
    freshness.add_argument(
        "--as-of",
        type=_a_date,
        metavar="YYYY-MM-DD",
        help="run the check as though it were this date",
    )

    replay = commands.add_parser(
        "replay", help="re-parse a stored snapshot; no network, no write"
    )
    replay.add_argument("key", help="a key within the store")
    _add_store(replay)

    # `elo replay` rather than a flag on `replay` above: that one re-parses one
    # Sagarin page and this one rebuilds a season. Sharing a verb would make
    # `--key` and `--season` mutually exclusive arguments on one command, which
    # is two commands wearing one name.
    elo = commands.add_parser("elo", help="the Elo model (SPEC-phase1 3)")
    elo_actions = elo.add_subparsers(dest="action", required=True)
    elo_replay = elo_actions.add_parser(
        "replay",
        help="rebuild a season's ratings from raw/ and check the stored state",
    )
    elo_replay.add_argument("--season", type=int, required=True)
    elo_replay.add_argument(
        "--through-week",
        metavar="N",
        help="stop after this week: 1-15, zero-padded or not, or 'postseason'. "
        "Default: the whole season",
    )
    _add_store(elo_replay)

    elo_seed = elo_actions.add_parser(
        "seed", help="write the season's opening state from the preseason page"
    )
    elo_seed.add_argument("--season", type=int, required=True)
    elo_seed.add_argument(
        "--force",
        action="store_true",
        help="re-seed a season that already has later states, e.g. after a parser fix",
    )
    _add_store(elo_seed)

    # Not in SPEC-phase1 9's list. §8 gives the Elo update to the Sunday
    # `cfb score` run, which is §5 and does not exist yet -- and until something
    # writes a week state, `elo replay` has nothing to check and step 5 of §11
    # verifies nothing. `cfb score` will call the same `advance()` when it lands.
    elo_advance = elo_actions.add_parser(
        "advance", help="apply one week's results to the previous state"
    )
    elo_advance.add_argument("--season", type=int, required=True)
    elo_advance.add_argument("--week", metavar="N", required=True)
    _add_store(elo_advance)

    # SPEC 8 also lists `crosswalk verify`; the SPEC 6.5 assertions it would run
    # are `uv run pytest cfb/tests/test_crosswalk.py`, which is what SPEC 6.4's
    # fix loop already tells you to type. A second way to run the same checks is
    # a second thing to keep in step with them.
    crosswalk = commands.add_parser("crosswalk", help="crosswalk tooling")
    crosswalk_actions = crosswalk.add_subparsers(dest="action", required=True)
    boot = crosswalk_actions.add_parser(
        "bootstrap", help="write the exact matches and rank the rest for review"
    )
    boot.add_argument("--season", type=int, required=True)

    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None, fetch=None) -> int:
    """Run one command. Returns the exit code; it does not call ``sys.exit``.

    ``now`` and ``fetch`` are the seams SPEC 8's "thin shell" principle requires.
    Without them every test of this module would need a clock and the network,
    and ``cfb/CLAUDE.md`` forbids the second one outright.
    """
    args = build_parser().parse_args(argv)
    moment = now or datetime.now(UTC)

    try:
        return _dispatch(args, moment=moment, fetch=fetch)
    except CfbError as exc:
        # SPEC 9. The class name is on the line because SPEC 11 makes the Actions
        # log the alert, and it is what says which of a dozen documented failures
        # this run hit.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _dispatch(args, *, moment: datetime, fetch) -> int:
    if args.command == "fetch" and args.source == "sagarin":
        return _fetch_sagarin(args, moment=moment, fetch=fetch)
    if args.command == "fetch" and args.source == "cfbd":
        return _fetch_cfbd(args, moment=moment, fetch=fetch)
    if args.command == "check-freshness":
        return _check_freshness(args, moment=moment)
    if args.command == "crosswalk":
        return _crosswalk_bootstrap(args)
    if args.command == "elo":
        return _elo(args, moment=moment)
    return _replay(args)


def _fetch_sagarin(args, *, moment: datetime, fetch) -> int:
    if not args.force and not _in_season(moment):
        # SPEC 11: the collect workflows exit 0 immediately when out of season.
        # That is the entire off-season story -- no runs to mute, no suppression
        # state, no false alarms from February to August.
        log(
            EVENT_SNAPSHOT_WRITTEN,
            source="sagarin",
            result=RESULT_SKIP,
            reason=REASON_NOT_IN_SEASON,
        )
        return 0

    store = _store(args.store)
    snapshot = (
        fetch_sagarin(store=store, now=moment, data_dir=_data_dir())
        if fetch is None
        else fetch_sagarin(store=store, now=moment, fetch=fetch, data_dir=_data_dir())
    )

    log(
        EVENT_SNAPSHOT_WRITTEN,
        source="sagarin",
        result=RESULT_OK,
        page_state=snapshot.page_state,
        teams=len(snapshot.teams),
        predictions=len(snapshot.predictions),
    )
    return 0


def _fetch_cfbd(args, *, moment: datetime, fetch) -> int:
    # Loaded once and used for both gates below. Unlike `fetch sagarin`, a
    # calendar that will not load is fatal here rather than something to proceed
    # past: SPEC 3.3's "never lose the capture" is about a page that exists only
    # today, and CFBD history is backfillable. There is nothing to save by
    # guessing, and a guessed week misfiles real games permanently.
    calendar = load_calendar(_season_of(moment), data_dir=_data_dir())

    if not args.force and not in_season(moment, calendar=calendar):
        # SPEC 11, and it runs before the week default on purpose. Off-season
        # both conditions are true and only one of them is the reason; reporting
        # "no completed week" in May would send whoever reads it to the calendar
        # looking for a bug that is not there.
        log(
            EVENT_SNAPSHOT_WRITTEN,
            source="cfbd",
            resource=args.resource,
            result=RESULT_SKIP,
            reason=REASON_NOT_IN_SEASON,
        )
        return 0

    season = args.season or _season_of(moment)
    week = _cfbd_week(args, calendar=calendar, moment=moment)
    if week is None:
        # No regular week has finished yet -- normal on the season's first
        # Sundays (SPEC 5.2). Exit 0: raising would turn those Sundays red before
        # anything had gone wrong, and an alert that is wrong twice before it is
        # ever right is one nobody reads by October. Nothing was requested, so
        # the budget of SPEC 5.1 is untouched.
        log(
            EVENT_SNAPSHOT_WRITTEN,
            source="cfbd",
            resource=args.resource,
            result=RESULT_SKIP,
            reason=REASON_NO_COMPLETED_WEEK,
        )
        return 0

    # SPEC 5.5. Building the fetcher touches nothing -- the key is read from SSM on
    # the first request -- so `cfb --help` and a usage error still need no
    # credentials.
    fetch_cfbd(
        store=_store(args.store),
        client=CfbdClient(fetch=fetch or http_fetch()),
        resource=args.resource,
        season=season,
        week=week,
        now=moment,
    )
    log(
        EVENT_SNAPSHOT_WRITTEN,
        source="cfbd",
        resource=args.resource,
        season=season,
        week=week,
        result=RESULT_OK,
    )
    return 0


def _check_freshness(args, *, moment: datetime) -> int:
    as_of = moment
    if args.as_of is not None:
        as_of = datetime(args.as_of.year, args.as_of.month, args.as_of.day, 12, tzinfo=UTC)

    check_freshness(
        store=_store(args.store),
        source=args.source,
        now=as_of,
        data_dir=_data_dir(),
    )
    return 0


def _replay(args) -> int:
    """Parse and validate an existing snapshot. No network, no write.

    SPEC 5.4: re-running after a parser fix is not the fetch command's job. A
    replay that wrote a new snapshot would forge a capture that never happened,
    so nothing here touches ``put_bytes`` -- it reads and reports.
    """
    data = _store(args.store).get_bytes(args.key)
    text, encoding = decode_page(data)

    with validating(f"replay of {args.key}"):
        snapshot = SagarinSnapshot(
            fetched_at=datetime.now(UTC),
            page_date_stamp=parse_page_date_stamp(text),
            page_state=parse_page_state(text),
            hfa=parse_hfa(text),
            teams=parse_ratings(text),
            predictions=parse_predictions(text),
        )

    log(
        "replay",
        key=args.key,
        result=RESULT_OK,
        encoding=encoding,
        page_state=snapshot.page_state,
        page_date_stamp=snapshot.page_date_stamp,
        teams=len(snapshot.teams),
        fbs=sum(1 for team in snapshot.teams if team.division == "A"),
        predictions=len(snapshot.predictions),
    )
    return 0


def _elo(args, *, moment: datetime) -> int:
    if args.action == "seed":
        return _elo_seed(args, moment=moment)
    if args.action == "advance":
        return _elo_advance(args, moment=moment)
    return _elo_replay(args)


def _elo_seed(args, *, moment: datetime) -> int:
    """SPEC-phase1 9's `cfb elo seed`: the season's opening state, written once.

    **Refuses a season that already has later states**, which is what §9's
    "refuses in-season" means at this level. §3.2's refusal is about the *page* and
    is enforced in `seed()`; it cannot fire here, because the seed snapshot is
    selected by `page_state == "preseason"` and an in-season page is never a
    candidate. The failure this guard catches is the other one: re-seeding a season
    that is under way. Re-seeding is not destructive on its own -- week states are
    separate objects and `advance` builds on the nearest earlier one, not on the
    seed -- but a second preseason state that nothing rebuilt the chain from is a
    season whose states no longer share an origin, and `--force` is there for the
    case where that is deliberate.
    """
    from cfb.elo.state import season_states, write_state
    from cfb.replay import seed_state

    store = _store(args.store)

    existing = [
        stored for stored in season_states(store, season=args.season)
        if stored.state.week != "preseason"
    ]
    if existing and not args.force:
        raise SeedStateError(
            f"season {args.season} already has {len(existing)} Elo state"
            f"{'' if len(existing) == 1 else 's'} past the preseason, the latest at "
            f"{existing[-1].key}. Re-seeding leaves those built on the old seed, so the "
            f"season would no longer share one origin. Pass --force if that is intended, "
            f"then rebuild the chain with `cfb elo advance` from week 01 forward"
        )

    state = seed_state(store=store, season=args.season, now=moment)
    key = write_state(store, state)

    log(
        EVENT_ELO_STATE,
        season=state.season,
        week=state.week,
        result=RESULT_OK,
        key=key,
        teams=len(state.ratings),
        seeded_from=state.seeded_from,
    )
    return 0


def _elo_advance(args, *, moment: datetime) -> int:
    """One week's results folded onto the previous state, and written.

    The Elo half of SPEC-phase1 8's Sunday run, ahead of the `cfb score` command
    that will own it. Writing zero games is a legitimate outcome and still writes a
    state -- a week that was entirely postponed, or a run that fires before any
    result has landed, both leave the ratings unchanged and both should leave a
    state at that week so the next advance has something to build on.
    """
    from cfb.elo.state import write_state
    from cfb.replay import advance

    week = _week_partition(args.week, flag="--week")
    advanced = advance(store=(store := _store(args.store)), season=args.season,
                       week=week, now=moment)
    key = write_state(store, advanced.state)

    log(
        EVENT_ELO_STATE,
        season=advanced.state.season,
        week=advanced.state.week,
        result=RESULT_OK,
        key=key,
        games=advanced.games_applied,
        season_games=advanced.state.games_applied,
        previous=advanced.previous.key,
    )
    return 0


def _elo_replay(args) -> int:
    """SPEC-phase1 11 step 5: rebuild the season from ``raw/`` and check the cache.

    Two things happen and the log says which. The rebuild always runs and always
    reports what it read -- the seed snapshot, the games keys, the count applied --
    because that is the artifact SPEC-phase1 3.5 promises can be regenerated
    without a state file. The comparison runs only when there is a stored state to
    compare against, and its absence is a logged skip rather than a failure: the
    Sunday scoring run of SPEC-phase1 8 writes those, and nothing orders a replay
    after it, so a replay in week 1 legitimately finds nothing.

    A mismatch is a ``StateMismatchError``, which `main` turns into exit 1 and a
    red run. That is the point of the check -- a stored state nobody can regenerate
    is a second source of truth wearing a cache's clothes, and it should cost a
    red run the first Sunday it stops being reproducible.
    """
    from cfb.replay import load_state, newest_state_key, replay, verify

    store = _store(args.store)
    rebuilt = replay(store=store, season=args.season, through_week=_through_week(args))

    log(
        EVENT_ELO_REPLAY,
        season=rebuilt.season,
        week=rebuilt.week,
        result=RESULT_OK,
        seeded_from=rebuilt.seeded_from,
        games=rebuilt.games_applied,
        snapshots=len(rebuilt.games_keys),
        teams=len(rebuilt.ratings),
    )

    key = newest_state_key(store, season=rebuilt.season, week=rebuilt.week)
    if key is None:
        log(
            EVENT_ELO_VERIFY,
            season=rebuilt.season,
            week=rebuilt.week,
            result=RESULT_SKIP,
            reason=REASON_NO_STORED_STATE,
        )
        return 0

    verify(rebuilt, load_state(store, key), key=key)
    log(
        EVENT_ELO_VERIFY,
        season=rebuilt.season,
        week=rebuilt.week,
        result=RESULT_OK,
        key=key,
        games=rebuilt.games_applied,
    )
    return 0


def _crosswalk_bootstrap(args) -> int:
    """SPEC 6.3. Imported here, not at module scope, and that is the point.

    ``bootstrap`` is the only module in this package that scores string
    similarity, and SPEC 6.3 quarantines it from the runtime path so a score can
    never become a mapping. A top-level import would put it one refactor away
    from the collectors; a function-local one keeps the CLI the only caller, and
    ``tests/test_crosswalk.py`` asserts the quarantine holds.
    """
    from cfb.crosswalk.bootstrap import bootstrap, candidates_path

    rosters = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "rosters"
    data_dir = Path(__file__).parent.parent.parent / "data" / "crosswalk"

    matched, undecided = bootstrap(
        season=args.season,
        sagarin_roster=rosters / f"sagarin-{args.season}.txt",
        cfbd_roster=rosters / f"cfbd-{args.season}.json",
        data_dir=data_dir,
    )
    print(f"  auto-matched exactly: {matched}")
    print(f"  needs review -> {candidates_path(args.season, data_dir=data_dir)}")
    print(f"    {undecided} names, ranked best-first; scoring orders them and decides none")
    return 0


def _through_week(args) -> str | None:
    """``--through-week`` as a partition value, or ``None`` for the whole season."""
    if args.through_week is None:
        return None
    return _week_partition(args.through_week, flag="--through-week")


def _week_partition(raw: str, *, flag: str) -> str:
    """A typed week as a partition value (SPEC-phase0 3.2).

    Accepts ``4`` and ``04`` and normalises both, because the value the user types
    is a week number and the value it becomes is a literal S3 path segment. SPEC
    11 step 5 writes it zero-padded and a person at a terminal will not.
    """
    if raw == "postseason":
        return raw
    if raw.isdigit() and 1 <= int(raw) <= 15:
        return f"{int(raw):02d}"
    build_parser().error(
        f"{flag} must be 1-15 or 'postseason' (SPEC-phase0 3.2), got {raw!r}"
    )


def _add_store(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE,
        metavar="URL",
        help=f"s3://bucket or file://path (default: {DEFAULT_STORE})",
    )


def _store(url: str):
    """Resolve ``--store`` (SPEC 8). An unknown scheme is a usage error.

    Argparse's exit 2, not a ``CfbError``: a mistyped flag is not a failure of the
    pipeline, and giving it the same exit code as a stale source would make the
    two indistinguishable in a workflow.
    """
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        return S3SnapshotStore(parsed.netloc, REGION)
    if parsed.scheme == "file":
        return FileSnapshotStore(Path(parsed.netloc + parsed.path))
    build_parser().error(f"--store must be s3:// or file://, got {url!r}")


def _cfbd_week(args, *, calendar, moment: datetime) -> str | None:
    """The ``week=`` partition for this pull, or ``None`` if nothing has completed.

    An explicit ``--week`` always wins. CFBD history is backfillable (SPEC 5.3),
    so re-pulling an older week is ordinary and must not require editing the
    committed calendar to do it.
    """
    if args.resource in ("teams", "calendar"):
        # Season-level resources are not week-scoped (SPEC 3.2's `season`).
        return "season"
    if args.week is not None:
        return _week_arg(args)
    return last_completed_week(moment, calendar=calendar)


def _week_arg(args) -> str:
    if not 1 <= args.week <= 15:
        build_parser().error(f"--week must be 1-15 (SPEC 3.2), got {args.week}")
    # The partition value, zero-padded: it reaches S3 as a literal path segment
    # and a stray "4" opens a second partition for a week that already has one.
    return f"{args.week:02d}"


def _a_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {text!r}") from None


def _in_season(moment: datetime) -> bool:
    """The SPEC 11 guard. **A calendar that will not load does not close it.**

    This is the one place in the package where an unreadable calendar is not a
    reason to stop, and the asymmetry is SPEC 3.3's. ``check_freshness`` reads,
    so refusing to run costs nothing and raising is right. This gate stands in
    front of a *capture*: Sagarin publishes current ratings only, so a week not
    fetched is gone permanently, and a guard that raised here would skip the
    fetch entirely over a problem with a different file.

    ``fetch_sagarin`` already handles the case properly -- it files the bytes
    under ``week=unknown``, records ``week_resolution="unknown"`` so a later
    re-partition sweep finds them, and only then raises so the run goes red. All
    of that is unreachable if this function raises first, which is exactly what
    it did until a real run against the live page found it.
    """
    try:
        calendar = load_calendar(_season_of(moment), data_dir=_data_dir())
    except WeekResolutionError:
        return True
    return in_season(moment, calendar=calendar)


def _season_of(moment: datetime) -> int:
    """A January date belongs to the season that started the previous August."""
    return moment.year if moment.month >= 7 else moment.year - 1


def _data_dir() -> Path | None:
    """Where the committed calendar lives.

    SPEC 8's command surface has no flag for it -- ``data/calendar/`` is committed
    and meant to be found -- so the override is an environment variable, which is
    what the tests point at a fixture.
    """
    import os

    override = os.environ.get("CFB_DATA_DIR")
    return Path(override) / "calendar" if override else None


def run() -> None:
    """The console-script entry point. Exits; ``main`` returns."""
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    run()
