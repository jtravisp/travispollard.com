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
``predict``, ``score``, ``publish`` and ``note``. All of them are registered as
of Phase 1. SPEC 8's ``crosswalk verify`` is not, and will not be: the SPEC 6.5
assertions it would run are `uv run pytest cfb/tests/test_crosswalk.py`, which
SPEC 6.4's fix loop already tells you to type. ``elo replay`` is here because
SPEC-phase1 11 step 5 is a command a human runs, and it is the check that keeps
the stored Elo state a cache rather than a second source of truth.
"""

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

from cfb.calendar import coming_week, in_season, last_completed_week, load_calendar
from cfb.collectors.cfbd import CfbdClient, fetch_cfbd, http_fetch
from cfb.collectors.sagarin import check_freshness, decode_page, fetch_sagarin
from cfb.errors import CfbError, ReplayError, SeedStateError, WeekResolutionError
from cfb.logging import (
    EVENT_BACKTESTED,
    EVENT_ELO_REPLAY,
    EVENT_ELO_STATE,
    EVENT_ELO_VERIFY,
    EVENT_INVALIDATED,
    EVENT_NOTE_WRITTEN,
    EVENT_PREDICTIONS_WRITTEN,
    EVENT_PUBLISHED,
    EVENT_SNAPSHOT_WRITTEN,
    EVENT_WEEK_SCORED,
    REASON_NO_COMING_WEEK,
    REASON_NO_COMPLETED_WEEK,
    REASON_NO_STORED_STATE,
    REASON_NOT_A_CDN_ORIGIN,
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
    # Optional, unlike `elo seed` and `elo advance`. Those are run by hand for a
    # season someone has in mind; this one runs every Sunday from `cfb-score.yml`
    # as SPEC-phase1 11 step 5, and a `--season $(date -u +%Y)` in that file
    # would be both the week arithmetic these workflows exist to keep out of YAML
    # and wrong every January -- a January date belongs to the season that
    # started the previous August, which `_season_of` already knows.
    elo_replay.add_argument("--season", type=int)
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

    # Not in SPEC-phase1 9's list, and kept anyway. §8 gives the Elo update to the
    # Sunday `cfb score` run, and `score` does call the same `advance()` -- but it
    # also needs a week's predictions and its results, so this is the verb that
    # brings a season's state up to date when there is nothing to score against:
    # a backfill, or the run that gives step 5 of §11 something to check.
    elo_advance = elo_actions.add_parser(
        "advance", help="apply one week's results to the previous state"
    )
    elo_advance.add_argument("--season", type=int, required=True)
    elo_advance.add_argument("--week", metavar="N", required=True)
    _add_store(elo_advance)

    predict = commands.add_parser(
        "predict", help="write a week's predictions (SPEC-phase1 4)"
    )
    predict.add_argument("--season", type=int)
    predict.add_argument(
        "--week",
        metavar="N",
        help="1-15; defaults to the week about to be played",
    )
    predict.add_argument(
        "--force",
        action="store_true",
        help="bypass the in_season guard, for manual testing",
    )
    _add_store(predict)

    score = commands.add_parser(
        "score", help="score a completed week against its predictions (SPEC-phase1 5)"
    )
    score.add_argument("--season", type=int)
    score.add_argument(
        "--week",
        metavar="N",
        help="1-15; defaults to the week that just completed",
    )
    score.add_argument(
        "--force",
        action="store_true",
        help="bypass the in_season guard, for manual testing",
    )
    _add_store(score)

    publish = commands.add_parser(
        "publish", help="build and upload /cfb/data/* (SPEC-phase1 6)"
    )
    publish.add_argument("--season", type=int)
    publish.add_argument(
        "--week",
        metavar="N",
        help="1-15; defaults to the week about to be played",
    )
    publish.add_argument(
        "--force",
        action="store_true",
        help="bypass the in_season guard, for manual testing",
    )
    _add_store(publish)

    note = commands.add_parser(
        "note", help="write a week's note scaffold (SPEC-phase1 7)"
    )
    note.add_argument("--season", type=int)
    note.add_argument(
        "--week",
        metavar="N",
        help="1-15; defaults to the week that just completed",
    )
    _add_store(note)

    backtest = commands.add_parser(
        "backtest",
        help="score a week the model was not live for, retrospectively (not a prediction)",
    )
    backtest.add_argument("--season", type=int, required=True)
    backtest.add_argument("--week", metavar="N", required=True)
    _add_store(backtest)

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
    if args.command == "backtest":
        return _backtest(args, moment=moment)
    if args.command == "note":
        return _note(args, moment=moment)
    if args.command == "publish":
        return _publish(args, moment=moment)
    if args.command == "score":
        return _score(args, moment=moment)
    if args.command == "predict":
        return _predict(args, moment=moment)
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


def _predict(args, *, moment: datetime) -> int:
    """SPEC-phase1 4: write the coming week's predictions, once, before kickoff.

    **The index is rebuilt in the same command.** §4.1 keeps
    ``predictions/index.json`` so the publish step and the site never list a
    prefix, and an index that lags the objects it describes is worse than no index
    -- the site would serve a key that is not the newest generation. It is a pure
    projection of the listing, so rebuilding costs one LIST and cannot disagree
    with what it describes.

    The week default is the calendar's, not this module's: `coming_week` is the
    mirror of `last_completed_week` that `fetch cfbd` already uses, and SPEC 11
    wants the workflow running the command a human runs rather than a week
    expression in YAML.
    """
    from cfb.predict import predict_week, rebuild_index, write_predictions

    season = args.season or _season_of(moment)
    calendar = load_calendar(season, data_dir=_data_dir())

    if not args.force and not in_season(moment, calendar=calendar):
        log(
            EVENT_PREDICTIONS_WRITTEN,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NOT_IN_SEASON,
        )
        return 0

    week = (
        _week_partition(args.week, flag="--week")
        if args.week is not None
        else coming_week(moment, calendar=calendar)
    )
    if week is None:
        # Past the last regular week's first kickoff. Nothing is ahead to predict,
        # and raising would redden every December Thursday.
        log(
            EVENT_PREDICTIONS_WRITTEN,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NO_COMING_WEEK,
        )
        return 0

    store = _store(args.store)
    log_document = predict_week(store=store, season=season, week=week, now=moment)
    key = write_predictions(store, log_document)
    index = rebuild_index(store, now=moment)

    log(
        EVENT_PREDICTIONS_WRITTEN,
        season=season,
        week=week,
        result=RESULT_OK,
        key=key,
        games=len(log_document.games),
        hfa=log_document.model.hfa,
        elo_state=log_document.model.elo_state,
        benchmarked=sum(
            1 for game in log_document.games if game.sagarin_predictor_margin is not None
        ),
        # How many of the slate a book actually priced. A Thursday run where this
        # collapses is a /lines pull that did not happen, and §5.3's ATS record
        # would quietly shrink rather than fail.
        priced=sum(1 for game in log_document.games if game.market_line is not None),
        indexed=len(index.weeks),
    )
    return 0


def _score(args, *, moment: datetime) -> int:
    """SPEC-phase1 8's Sunday run: update Elo, score last week, write ``scored/``.

    **Two things happen and they are independent**, which is the only reason it is
    safe for one command to do both. The advance folds the week's completed games
    onto the previous state and reads nothing from ``predictions/``; the scoring
    grades a document written days earlier against results and reads no rating.
    Neither can quietly consume the other's output. §8 lists the Elo update first,
    so it goes first among the *writes* -- and if the scoring then raises on a
    join failure, the state already written is still correct, because a prediction
    that went missing says nothing about whether the game was played.

    **The advance is `replay.advance`, the same function `cfb elo advance` calls.**
    Not a copy of it -- a second implementation of "which games, which names,
    which HFA" is precisely what step 5 of §11 would stop being able to detect,
    since it would be comparing a rebuild against a cache that drifted for reasons
    the model never saw.

    A rerun writes new keys beside the old ones rather than replacing them, for
    both documents. That is the same behaviour `cfb predict` has and it is the
    point of write-once: a rescore that disliked Sunday's numbers cannot quietly
    become the only surviving record.
    """
    from cfb.elo.scoring import score_week, write_scored
    from cfb.elo.state import write_state
    from cfb.predict import predictions_to_score
    from cfb.replay import advance
    from cfb.sources import results_capture, week_position, week_slate

    season = args.season or _season_of(moment)
    calendar = load_calendar(season, data_dir=_data_dir())

    if not args.force and not in_season(moment, calendar=calendar):
        log(
            EVENT_WEEK_SCORED,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NOT_IN_SEASON,
        )
        return 0

    week = (
        _week_partition(args.week, flag="--week")
        if args.week is not None
        else last_completed_week(moment, calendar=calendar)
    )
    if week is None:
        # No regular week has finished. Normal on the season's first Sundays, and
        # a skip rather than an error for the same reason `fetch cfbd` skips.
        log(
            EVENT_WEEK_SCORED,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NO_COMPLETED_WEEK,
        )
        return 0

    store = _store(args.store)

    # **Everything is read before anything is written.** Not tidiness: `advance`
    # writes a state whatever it finds, and a week whose results never landed is
    # a week it legitimately folds zero games into. Left after the write, a Sunday
    # where the CFBD pull failed would go red on the missing capture *and* leave
    # an empty week state behind it -- harmless, since a replay of the same empty
    # `raw/` reproduces it and the next run absorbs the week, but it is a state
    # object asserting a week happened that nobody has evidence for yet. Reading
    # first makes a run that cannot do its job write nothing at all.
    #
    # The capture is read for its `fetched_at`, and that is a model input rather
    # than a log field: §5.2 decides "unplayed, or a join that failed" against
    # when the results were looked at rather than against a clock, so a scoring
    # run that took the moment from `now` could not be replayed.
    capture = results_capture(store, season, week)
    target = week_position(week, label="--week")
    slate, _ = week_slate(store, season, lambda raw: raw.order == target)
    predictions = predictions_to_score(store, season=season, week=week)

    advanced = advance(store=store, season=season, week=week, now=moment)
    state = write_state(store, advanced.state)
    log(
        EVENT_ELO_STATE,
        season=advanced.state.season,
        week=advanced.state.week,
        result=RESULT_OK,
        key=state,
        games=advanced.games_applied,
        season_games=advanced.state.games_applied,
        previous=advanced.previous.key,
    )

    scored = score_week(
        predictions,
        [raw for raw, _ in slate],
        results_fetched_at=capture.fetched_at,
        now=moment,
    )
    key = write_scored(store, scored)

    log(
        EVENT_WEEK_SCORED,
        season=scored.season,
        week=scored.week,
        result=RESULT_OK,
        key=key,
        games=len(scored.games),
        # Every prediction is accounted for: scored, or left out and counted.
        # §5.2 makes anything else an error, so a run where these do not add up to
        # the slate is a bug in the scorer rather than a quiet week.
        unplayed=scored.unplayed,
        results_from=capture.snapshot_key,
        predictions_generated_at=scored.predictions_generated_at.isoformat(),
        ats=scored.full_slate.ats.record,
        # The two figures the accuracy page opens with, and the two whose
        # denominators §5.3 insists travel with them.
        mae=scored.full_slate.mae,
        brier=scored.full_slate.brier,
        texas_games=scored.texas.games,
        elo_state=state,
    )
    return 0


def _publish(args, *, moment: datetime) -> int:
    """SPEC-phase1 8's Friday run: build `/cfb/data/*` and upload it.

    **This is the SLO**, and its deadline is first kickoff Saturday. §8 is
    explicit that it can genuinely be missed and that there is no
    retry-until-it-works loop, because a prediction published after kickoff is not
    a prediction -- so everything here either succeeds loudly or fails loudly, and
    the `published` line is what an alert reads.

    The week default is `coming_week`, the same one `cfb predict` uses, because
    the two commands are two halves of one week: Thursday writes the forecast and
    Friday puts it on the page. A publish that resolved the week differently from
    the predict that fed it would be publishing a slate nobody generated.

    **The invalidation is a separate step and a separate log line**, after both
    documents are written. §6.5 pairs it with the upload, but the upload is what
    makes the new numbers exist and the invalidation only makes them visible
    sooner -- a failure here is a slow page, not a wrong one. A Friday run has to
    be readable on that distinction at a glance.

    It is skipped, loudly, when the store is not the bucket the CDN reads. A
    `file://` publish has no edge cache in front of it, and a run reporting an
    invalidation it never made would be the one line on a Friday nobody could
    trust.
    """
    from cfb.publish import ACCURACY_KEY, NEXT_GAME_KEY, SLATE_KEY, publish

    season = args.season or _season_of(moment)
    calendar = load_calendar(season, data_dir=_data_dir())

    if not args.force and not in_season(moment, calendar=calendar):
        log(
            EVENT_PUBLISHED,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NOT_IN_SEASON,
        )
        return 0

    week = (
        _week_partition(args.week, flag="--week")
        if args.week is not None
        else coming_week(moment, calendar=calendar)
    )
    if week is None:
        log(
            EVENT_PUBLISHED,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NO_COMING_WEEK,
        )
        return 0

    store = _store(args.store)
    written = publish(store=store, season=season, week=week, now=moment)

    # Re-read rather than re-derive: the numbers on this line are the ones a
    # person would check the live page against, so they should come from the
    # document that was actually written.
    from cfb.publish import AccuracyDocument, NextGameDocument, SlateDocument

    next_game = NextGameDocument.model_validate_json(store.get_bytes(NEXT_GAME_KEY))
    accuracy = AccuracyDocument.model_validate_json(store.get_bytes(ACCURACY_KEY))
    slate = SlateDocument.model_validate_json(store.get_bytes(SLATE_KEY))

    log(
        EVENT_PUBLISHED,
        season=season,
        week=week,
        result=RESULT_OK,
        keys=" ".join(sorted(written)),
        team=next_game.team,
        # `bye` rather than a missing field: a Friday where `/cfb` shows no game
        # should be visible in the run that put it there.
        opponent=next_game.game.opponent if next_game.game else "bye",
        win_probability=next_game.game.win_probability if next_game.game else None,
        national_rank=next_game.as_of.national_rank,
        elo_state_week=next_game.as_of.week,
        slate_games=len(slate.games),
        # A week where this collapses is a /lines pull that did not happen, and
        # §5.3's ATS record would quietly shrink rather than fail.
        slate_priced=slate.priced,
        scored_through=accuracy.through_week,
        scored_games=accuracy.full_slate.games,
        seed_disclosure=accuracy.seed_disclosure.active,
        sagarin_r=accuracy.seed_disclosure.current_r,
    )

    _invalidate(args, season=season, week=week, moment=moment)
    return 0


def _invalidate(args, *, season: int, week: str, moment: datetime) -> None:
    """§6.5's `/cfb/data/*` invalidation, or a logged skip saying why not."""
    if urlparse(args.store).scheme != "s3":
        log(
            EVENT_INVALIDATED,
            season=season,
            week=week,
            result=RESULT_SKIP,
            reason=REASON_NOT_A_CDN_ORIGIN,
            store=args.store,
        )
        return

    from cfb.cdn import DATA_PATHS, distribution_id, invalidate

    distribution = distribution_id()
    # The run's own moment as the caller reference, so a retried publish asks
    # CloudFront for the same invalidation rather than a second one -- see
    # `cdn.invalidate` for why this is the caller's to supply.
    reference = f"cfb-publish-{season}-{week}-{moment.strftime('%Y-%m-%dT%H%M%SZ')}"
    log(
        EVENT_INVALIDATED,
        season=season,
        week=week,
        result=RESULT_OK,
        distribution=distribution,
        paths=" ".join(DATA_PATHS),
        invalidation=invalidate(distribution=distribution, caller_reference=reference),
    )


def _note(args, *, moment: datetime) -> int:
    """SPEC-phase1 7: the scaffold a person turns into the week's note.

    **No in-season guard, unlike every other command here.** The others are
    scheduled and gate on the calendar so an out-of-season cron is a skip rather
    than a failure; this one is only ever run by hand, by someone who has decided
    to write about a specific week. Skipping silently because of the date would
    be answering a question they did not ask.

    Reads the newest scored generation for the week. There is no pre-kickoff
    subtlety here of the kind `cfb score` has: a scaffold describes games that
    have been played, so the newest scoring of them is simply the best one.
    """
    from cfb.elo.scoring import scored_weeks
    from cfb.publish.notes import write_scaffold

    season = args.season or _season_of(moment)
    week = (
        _week_partition(args.week, flag="--week")
        if args.week is not None
        else last_completed_week(moment, calendar=load_calendar(season, data_dir=_data_dir()))
    )
    if week is None:
        log(
            EVENT_NOTE_WRITTEN,
            season=season,
            result=RESULT_SKIP,
            reason=REASON_NO_COMPLETED_WEEK,
        )
        return 0

    store = _store(args.store)
    scored = [found for found in scored_weeks(store, season=season) if found.week == week]
    if not scored:
        raise ReplayError(
            f"week {week} of season {season} has not been scored, so there are no figures "
            f"to build a note from. Score it first:\n"
            f"  uv run cfb score --season {season} --week "
            f"{int(week) if week.isdigit() else week}"
        )

    week_scored = scored[0]
    key = write_scaffold(store, week_scored, generated_at=moment)
    log(
        EVENT_NOTE_WRITTEN,
        season=season,
        week=week,
        result=RESULT_OK,
        key=key,
        games=len(week_scored.games),
        # The three things the scaffold is built around, so the run says what it
        # actually had to work with.
        texas=any(game.home == "texas" or game.away == "texas" for game in week_scored.games),
        ats=week_scored.full_slate.ats.record,
        mae=week_scored.full_slate.mae,
    )
    return 0


def _backtest(args, *, moment: datetime) -> int:
    """Score a week the model was not live for. **This is not a prediction.**

    Week 1 of 2026 opened at 2026-08-27T22:00Z and the earliest Sagarin capture
    this project holds is 2026-08-28T16:50Z, so §3.3 refuses to read an HFA for it
    and `cfb predict --week 1` exits 1. That refusal is correct and stays.

    What this does instead is state plainly what it is. The seed contains no
    week 1 information -- it is the preseason page, which predates every game --
    so the numbers are honestly derivable. What is missing is not the arithmetic
    but the *evidence of having been written first*, which is the entire property
    SPEC-phase1 1.1 gives up git in order to keep.

    So three things keep it separate, and all three are structural rather than a
    convention someone has to remember:

    - it never writes to ``predictions/``, so nothing can grade it as a forecast;
    - it writes to ``backtest/``, a prefix ``scored_weeks`` does not read by
      default, so it cannot reach the published season-to-date record;
    - §6.4 renders it in its own block, labelled.

    **And it is worth knowing what a week 1 backtest actually measures.** The seed
    is ``1500 + (rating - mean) * 28``, so an Elo gap over 28 is exactly a Sagarin
    rating gap, and the preseason page's four rating columns are identical
    (SPEC-phase1 1.2). A week 1 forecast is therefore Sagarin's PREDICTOR to the
    floating-point bit -- §3.6's correlation opens at exactly 1.0. The figures
    this produces are a measurement of Sagarin's preseason page, not of Elo, and
    the page says so.
    """
    from cfb.elo.scoring import score_week, write_scored
    from cfb.predict import predict_week
    from cfb.sources import (
        hfa_manifests,
        results_capture,
        sagarin_manifests,
        week_position,
        week_slate,
    )

    week = _week_partition(args.week, flag="--week")
    store = _store(args.store)

    # The oldest snapshot carrying an HFA, not the newest before kickoff. It is
    # the preseason page, it predates the whole season, and it is a fixed choice
    # rather than a clock -- so this is as replayable as every other path here.
    manifests = hfa_manifests(sagarin_manifests(store, args.season))
    if not manifests:
        raise ReplayError(
            f"no Sagarin snapshot for season {args.season} carries an HFA, so there is "
            f"nothing to backtest week {week} from"
        )
    earliest = manifests[0]

    # Not named `log`: that is the logging function this module uses everywhere,
    # and shadowing it here crashed the run *after* the document was written.
    retrodiction = predict_week(
        store=store,
        season=args.season,
        week=week,
        now=moment,
        hfa_manifest=earliest,
    )

    capture = results_capture(store, args.season, week)
    target = week_position(week, label="--week")
    slate, _ = week_slate(store, args.season, lambda raw: raw.order == target)

    scored = score_week(
        retrodiction,
        [raw for raw, _ in slate],
        results_fetched_at=capture.fetched_at,
        now=moment,
    )
    key = write_scored(store, scored, prefix="backtest")

    log(
        EVENT_BACKTESTED,
        season=args.season,
        week=week,
        result=RESULT_OK,
        key=key,
        games=len(scored.games),
        unplayed=scored.unplayed,
        hfa_source=earliest.snapshot_key,
        mae=scored.full_slate.mae,
        ats=scored.full_slate.ats.record,
        # Expected to be 1.0 for week 1 -- see this function's docstring.
        sagarin_r=scored.sagarin_r,
    )
    return 0


def _elo(args, *, moment: datetime) -> int:
    if args.action == "seed":
        return _elo_seed(args, moment=moment)
    if args.action == "advance":
        return _elo_advance(args, moment=moment)
    return _elo_replay(args, moment=moment)


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


def _elo_replay(args, *, moment: datetime) -> int:
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
    season = args.season or _season_of(moment)
    rebuilt = replay(store=store, season=season, through_week=_through_week(args))

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
