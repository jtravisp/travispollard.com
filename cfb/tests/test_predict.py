"""The prediction log (SPEC-phase1 4).

What §4.2 actually asks for is a document that can be disbelieved: every number in
it re-derivable from `raw/` months later by someone who does not trust it. So most
of this file is about the `model` block and the joins, not about the arithmetic —
`test_elo.py` owns the formulas and asserting them again here would mean two files
failing for one cause.

## The benchmark join is tested against the real page

`sagarin_predictor_margin` comes from the golden capture's predictions block, which
holds 53 real rows. Five of them are at a neutral or classic site, and those are
the ones that matter: §5.1 records that the two sources can disagree about which
team is nominally home, and Sagarin's `@` marker is its own view rather than
CFBD's.

Rank 20 of the real page is `North Carolina` over `TCU` at a neutral site, margin
−6.20 from Sagarin's home team. `TestTheSagarinBenchmark` builds a CFBD capture
that lists **TCU** as home for that game — which is legal, arbitrary, and exactly
what happens — and asserts the stored margin is +6.20. A join keyed on
`(home, away)` rather than on the unordered pair passes every other test in this
file and silently returns `None` for every neutral-site game.

## What is not asserted here

`closing_line`. There is no `/lines` capture in this project and no fixture, so
there is nothing to test a parser against and `cfb/CLAUDE.md` forbids fetching one
from a test. §4.2 makes the field nullable and `predict._closing_line` documents
the single place to implement it once a capture exists.
"""

from datetime import UTC, datetime

import pytest

from cfb.cli import main
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import ELO_PER_POINT, K, win_probability
from cfb.elo.state import write_state
from cfb.errors import ReplayError, SnapshotExistsError
from cfb.predict import (
    INDEX_KEY,
    PredictionIndex,
    PredictionLog,
    index_entries,
    predict_week,
    prediction_key,
    rebuild_index,
    write_predictions,
)
from cfb.replay import advance, seed_state
from cfb.storage import FileSnapshotStore, MemorySnapshotStore
from test_replay import PRESEASON_AT, PRESEASON_HFA, SEASON, cfbd_game, put_games, put_sagarin

# --- the week 1 slate ---------------------------------------------------------
#
# Three games, each testing a different half of the benchmark join. The kickoffs
# straddle a Thursday-to-Saturday week so the HFA boundary has something to bite.

THURSDAY = datetime(2026, 9, 3, 23, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)
SATURDAY_LATE = datetime(2026, 9, 5, 23, 30, tzinfo=UTC)

#: On the page, ordinary site, Sagarin's home is CFBD's home. Margin +10.67.
ON_PAGE = cfbd_game(
    game_id=301, week=1, kickoff=THURSDAY,
    home="Austin Peay", away="Gardner-Webb", home_points=None, away_points=None,
)
#: On the page at rank 20 as `North Carolina` over `TCU`, neutral, −6.20 from
#: Sagarin's home. CFBD lists the other team as home, which is the disagreement.
REVERSED_NEUTRAL = cfbd_game(
    game_id=302, week=1, kickoff=SATURDAY,
    home="TCU", away="North Carolina",
    home_points=None, away_points=None, neutral_site=True,
)
#: Not on the page. The benchmark is partial and `None` is the ordinary answer.
OFF_PAGE = cfbd_game(
    game_id=303, week=1, kickoff=SATURDAY_LATE,
    home="Ohio State", away="Michigan", home_points=None, away_points=None,
)

WEEK_01_PULLED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

#: The real values on the golden page, so the join assertions name their source.
AUSTIN_PEAY_MARGIN = 10.67
NEUTRAL_MARGIN_SAGARIN_HOME = -6.20


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture
def store(crosswalk):
    """A seeded season with week 1's slate captured and nothing played yet."""
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(
        store, week="01", fetched_at=WEEK_01_PULLED_AT,
        games=[OFF_PAGE, REVERSED_NEUTRAL, ON_PAGE],  # not in kickoff order
    )
    write_state(
        store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
    )
    return store


@pytest.fixture
def log(store, crosswalk) -> PredictionLog:
    return predict_week(
        store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
    )


def by_id(log: PredictionLog) -> dict[int, object]:
    return {game.cfbd_game_id: game for game in log.games}


# --- the document -------------------------------------------------------------


class TestTheEnvelope:
    def test_it_carries_the_spec_4_2_envelope(self, log):
        assert log.schema_version == 1
        assert log.season == SEASON
        assert log.week == "01"
        assert log.generated_at == GENERATED_AT

    def test_every_game_on_the_slate_is_present(self, log):
        assert len(log.games) == 3
        assert set(by_id(log)) == {301, 302, 303}

    def test_unplayed_games_are_the_point(self, log):
        """§4.1 is "every game on that week's slate", not the completed ones.

        `replay` and `advance` read `completed_games`; this reads `week_slate`.
        A prediction run happens before anything has been played, so a filter that
        looked for results would write an empty document every Thursday.
        """
        assert all(game.kickoff > GENERATED_AT for game in log.games)

    def test_the_games_are_in_kickoff_order(self, log):
        """Presentational here, unlike the identical sort in `replay`.

        The capture lists them out of order on purpose, so this fails if the sort
        is dropped — but nothing about the numbers depends on it, because nothing
        here folds anything.
        """
        assert [g.cfbd_game_id for g in log.games] == [301, 302, 303]

    def test_the_key_is_the_spec_4_1_layout(self, log):
        assert (
            prediction_key(season=SEASON, week="01", generated_at=GENERATED_AT)
            == "predictions/season=2026/week=01/2026-09-03T120000Z.json"
        )


class TestTheModelBlock:
    """§4.2: a prediction that cannot be re-derived is an assertion, not a record."""

    def test_it_names_the_constants_the_run_used(self, log):
        assert log.model.name == "elo"
        assert log.model.elo_per_point == ELO_PER_POINT
        assert log.model.k == K

    def test_it_names_the_manifest_the_hfa_came_from(self, log):
        """The `.meta.json`, not the `.txt`.

        The HFA was read from the manifest (SPEC-phase0 2.2 captures it there so
        nothing re-parses the page for it), and naming the page would point at
        bytes this run never opened for that number.
        """
        assert log.model.hfa == PRESEASON_HFA
        assert log.model.hfa_source.endswith(".meta.json")
        assert log.model.hfa_source.startswith(f"raw/sagarin/season={SEASON}/")

    def test_it_names_the_page_the_season_was_seeded_from(self, log, store):
        assert log.model.seeded_from.endswith(".txt")
        assert store.get_bytes(log.model.seeded_from)  # the object is really there

    def test_it_names_the_elo_state_the_run_started_from(self, log, store):
        assert log.model.elo_state.startswith(f"elo/season={SEASON}/week=preseason/")
        assert store.get_bytes(log.model.elo_state)

    def test_it_names_the_page_the_benchmark_came_from(self, log, store):
        """Not in §4.2's example, and it belongs.

        `sagarin_predictor_margin` is a number from a source. A number whose source
        the document cannot name is the thing the model block exists to prevent.
        """
        assert store.get_bytes(log.model.sagarin_predictions_from)

    def test_the_state_is_the_one_before_this_week(self, store, crosswalk):
        """§4.2's example: a week 04 prediction names `elo/.../week=03/`.

        Predicting a week must not depend on results from it, so the state is the
        one strictly before — and with a week 1 state written, a week 2 prediction
        must move to it rather than staying on the seed.
        """
        put_games(
            store, week="02", fetched_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            games=[cfbd_game(
                game_id=401, week=2, kickoff=datetime(2026, 9, 12, 23, tzinfo=UTC),
                home="Ohio State", away="Michigan", home_points=None, away_points=None,
            )],
        )
        write_state(store, advance(
            store=store, season=SEASON, week="01",
            now=datetime(2026, 9, 6, 12, 30, tzinfo=UTC), crosswalk=crosswalk,
        ).state)

        log = predict_week(
            store=store, season=SEASON, week="02",
            now=datetime(2026, 9, 10, 12, tzinfo=UTC), crosswalk=crosswalk,
        )
        assert "week=01" in log.model.elo_state


class TestHomePerspective:
    """§4.2: home perspective always, so nothing downstream flips a sign."""

    def test_the_margin_matches_the_elo_gap_over_the_scale_plus_hfa(self, log):
        game = by_id(log)[301]
        expected = (game.elo_home - game.elo_away) / ELO_PER_POINT + PRESEASON_HFA
        assert game.predicted_margin == pytest.approx(expected, abs=1e-9)

    def test_a_neutral_site_gets_no_home_advantage(self, log):
        """§3.4. The designation is arbitrary at a neutral site, so an edge awarded
        on it would be noise in whichever direction CFBD happened to list them.
        """
        game = by_id(log)[302]
        assert game.neutral_site is True
        assert game.predicted_margin == pytest.approx(
            (game.elo_home - game.elo_away) / ELO_PER_POINT, abs=1e-9
        )

    def test_margin_and_probability_cannot_disagree(self, log):
        """The PRD's requirement, at the document level."""
        for game in log.games:
            assert game.win_probability == pytest.approx(
                win_probability(game.predicted_margin), abs=1e-12
            )

    def test_probabilities_are_stored_unclamped(self, log):
        """§3.7's clamp is presentational and applied at publish.

        Austin Peay against Gardner-Webb is not extreme, so this asserts the
        weaker available thing: nothing sits exactly on a clamp endpoint, which is
        what a clamp applied here would produce.
        """
        assert all(game.win_probability not in (0.001, 0.999) for game in log.games)

    def test_the_ratings_are_full_precision(self, log):
        """§4.2's example shows rounded Elo values. Storing those would make the
        row unable to reproduce its own margin.
        """
        assert any(game.elo_home != round(game.elo_home) for game in log.games)


class TestTheSagarinBenchmark:
    """The join, and the neutral-site sign that only real data exposes."""

    def test_a_game_on_the_page_carries_its_margin(self, log):
        assert by_id(log)[301].sagarin_predictor_margin == pytest.approx(
            AUSTIN_PEAY_MARGIN, abs=1e-9
        )

    def test_a_reversed_neutral_site_game_has_its_margin_re_signed(self, log):
        """**The test this file exists for.**

        The page has this game at rank 20 as `North Carolina` over `TCU`, neutral,
        −6.20 from Sagarin's home team. The CFBD capture lists TCU as home — legal,
        arbitrary, and what actually happens (§5.1). So the stored margin has to be
        +6.20, re-signed to CFBD's home team.

        A join keyed on `(home, away)` returns `None` here and passes every other
        test in this file.
        """
        assert by_id(log)[302].sagarin_predictor_margin == pytest.approx(
            -NEUTRAL_MARGIN_SAGARIN_HOME, abs=1e-9
        )

    def test_a_game_not_on_the_page_is_none_not_an_error(self, log):
        """The page carries 53 rows against a full FBS slate. Partial is normal,
        and §4.2 says so — which is why §5.3 reports it beside the closing line
        rather than instead of it.
        """
        assert by_id(log)[303].sagarin_predictor_margin is None

    def test_the_benchmark_is_an_input_to_nothing(self, log):
        """§1.2: PREDICTOR remains a benchmark only.

        The predicted margin is a function of the ratings and the HFA alone, so
        removing the benchmark cannot move it. Asserted by re-deriving the margin
        without reference to it.
        """
        for game in log.games:
            hfa = 0.0 if game.neutral_site else PRESEASON_HFA
            assert game.predicted_margin == pytest.approx(
                (game.elo_home - game.elo_away) / ELO_PER_POINT + hfa, abs=1e-9
            )


class TestHomeFieldAdvantage:
    """One value for the slate, bounded by the slate's *first* kickoff."""

    def test_a_snapshot_landing_mid_week_is_not_used(self, store, crosswalk):
        """A prediction run cannot use a snapshot that did not exist when it ran.

        This capture lands after Thursday's kickoff and before Saturday's. Under a
        per-game rule, Saturday's games would take its HFA — which is right for
        *scoring* them later and wrong for a Thursday forecast, because the run
        never saw it. §4.2 carries one `hfa` per run for exactly this reason.
        """
        put_sagarin(
            store,
            fetched_at=datetime(2026, 9, 4, 12, tzinfo=UTC),  # between the kickoffs
            week="01",
            page_state="in-season",
            page_date_stamp=datetime(2026, 9, 3, tzinfo=UTC).date(),
            hfa={"rating": 9.9, "predictor": 9.9},
        )

        log = predict_week(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert log.model.hfa == PRESEASON_HFA

    def test_a_snapshot_before_the_first_kickoff_is_used(self, store, crosswalk):
        """The control: the rule takes the newest one it is allowed to see."""
        put_sagarin(
            store,
            fetched_at=datetime(2026, 9, 1, 12, tzinfo=UTC),  # before Thursday
            week="01",
            page_state="in-season",
            page_date_stamp=datetime(2026, 8, 31, tzinfo=UTC).date(),
            hfa={"rating": 3.5, "predictor": 3.5},
        )

        log = predict_week(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert log.model.hfa == 3.5

    def test_no_snapshot_before_the_slate_raises_rather_than_defaulting(self, crosswalk):
        """`cfb/CLAUDE.md`: never hardcode home-field advantage."""
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=datetime(2026, 9, 30, 12, tzinfo=UTC))
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[ON_PAGE])
        write_state(store, seed_state(
            store=store, season=SEASON, now=datetime(2026, 10, 1, tzinfo=UTC),
            crosswalk=crosswalk,
        ))

        with pytest.raises(ReplayError, match="hfa"):
            predict_week(
                store=store, season=SEASON, week="01",
                now=GENERATED_AT, crosswalk=crosswalk,
            )


class TestRefusals:
    def test_predicting_without_a_state_says_what_to_run(self, crosswalk):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[ON_PAGE])

        with pytest.raises(ReplayError) as excinfo:
            predict_week(
                store=store, season=SEASON, week="01",
                now=GENERATED_AT, crosswalk=crosswalk,
            )
        assert "cfb elo seed" in str(excinfo.value)

    def test_an_empty_slate_raises_rather_than_writing_an_empty_object(
        self, store, crosswalk
    ):
        """The object is write-once and permanent. An empty one would be too.

        §4.1's whole integrity story is that a prediction cannot be replaced, which
        cuts both ways: a wrong one cannot be withdrawn either.
        """
        with pytest.raises(ReplayError) as excinfo:
            predict_week(
                store=store, season=SEASON, week="05",
                now=GENERATED_AT, crosswalk=crosswalk,
            )
        assert "fetch cfbd" in str(excinfo.value)

    def test_an_illegal_week_raises(self, store, crosswalk):
        with pytest.raises(ReplayError, match="week"):
            predict_week(
                store=store, season=SEASON, week="16",
                now=GENERATED_AT, crosswalk=crosswalk,
            )


class TestWriteOnce:
    """§4.1, and the property SPEC-phase1 1.1 kept when it dropped git."""

    def test_a_prediction_round_trips(self, store, log):
        key = write_predictions(store, log)
        assert PredictionLog.model_validate_json(store.get_bytes(key)) == log

    def test_rewriting_the_same_key_raises(self, store, log):
        """A prediction written Thursday cannot become a different one on Sunday."""
        write_predictions(store, log)
        with pytest.raises(SnapshotExistsError):
            write_predictions(store, log)

    def test_a_regenerate_writes_a_second_object_and_keeps_the_first(
        self, store, crosswalk, log
    ):
        first = write_predictions(store, log)
        later = predict_week(
            store=store, season=SEASON, week="01",
            now=datetime(2026, 9, 3, 18, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        second = write_predictions(store, later)

        assert first != second
        assert store.get_bytes(first)  # still there, forever
        assert len(store.list_keys(f"predictions/season={SEASON}/week=01/")) == 2

    def test_the_stored_json_is_readable_at_a_terminal(self, store, log):
        """§11 step 1 is `aws s3 ls` and a `python -m json.tool` away from this."""
        key = write_predictions(store, log)
        assert store.get_bytes(key).startswith(b"{\n  ")


class TestTheIndex:
    """§4.1's one mutable object, and why it is safe to overwrite."""

    def test_it_names_the_newest_generation_per_week(self, store, crosswalk, log):
        write_predictions(store, log)
        later = predict_week(
            store=store, season=SEASON, week="01",
            now=datetime(2026, 9, 3, 18, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        newest = write_predictions(store, later)

        entries = index_entries(store)
        assert len(entries) == 1
        assert entries[0].key == newest
        assert entries[0].week == "01"
        assert entries[0].season == SEASON

    def test_it_is_a_pure_projection_of_the_listing(self, store, log):
        """Every field comes out of the key, so the index cannot disagree with the
        objects it describes — it never opened them.
        """
        key = write_predictions(store, log)
        [entry] = index_entries(store)
        assert entry.generated_at == log.generated_at
        assert entry.key == key

    def test_it_ignores_itself_and_strays(self, store, log):
        write_predictions(store, log)
        rebuild_index(store, now=GENERATED_AT)
        store.put_bytes("predictions/notes.txt", b"scratch", "text/plain")

        assert len(index_entries(store)) == 1

    def test_rebuilding_overwrites_rather_than_accumulating(self, store, log):
        """`put_json`, deliberately: this is the manifest-shaped exception."""
        write_predictions(store, log)
        rebuild_index(store, now=GENERATED_AT)
        rebuild_index(store, now=datetime(2026, 9, 4, 12, tzinfo=UTC))

        index = PredictionIndex.model_validate_json(store.get_bytes(INDEX_KEY))
        assert index.generated_at == datetime(2026, 9, 4, 12, tzinfo=UTC)
        assert len(index.weeks) == 1

    def test_weeks_come_back_newest_first(self, store, crosswalk, log):
        write_predictions(store, log)
        put_games(
            store, week="02", fetched_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            games=[cfbd_game(
                game_id=402, week=2, kickoff=datetime(2026, 9, 12, 23, tzinfo=UTC),
                home="Ohio State", away="Michigan", home_points=None, away_points=None,
            )],
        )
        write_predictions(store, predict_week(
            store=store, season=SEASON, week="02",
            now=datetime(2026, 9, 10, 12, tzinfo=UTC), crosswalk=crosswalk,
        ))

        assert [entry.week for entry in index_entries(store)] == ["02", "01"]


class TestTheCommand:
    """`cfb predict` — SPEC-phase1 9, as a human and a workflow both type it."""

    @pytest.fixture
    def rooted(self, tmp_path, store):
        disk = FileSnapshotStore(tmp_path)
        for key, data in sorted(store._objects.items()):  # noqa: SLF001 - the test store
            disk.put_bytes(key, data, "application/octet-stream")
        return f"file://{tmp_path}", disk

    @pytest.fixture
    def calendar_dir(self, tmp_path, monkeypatch):
        """The synthetic calendar, so `--week` can be defaulted from it."""
        from pathlib import Path as P

        source = P(__file__).parent / "fixtures" / "calendar_2026_synthetic.json"
        root = tmp_path / "data" / "calendar"
        root.mkdir(parents=True)
        (root / "2026.json").write_bytes(source.read_bytes())
        monkeypatch.setenv("CFB_DATA_DIR", str(tmp_path / "data"))
        return root

    def test_it_writes_a_week_and_indexes_it(self, rooted, calendar_dir, capsys):
        url, disk = rooted
        assert main(
            ["predict", "--season", "2026", "--week", "1", "--store", url],
            now=GENERATED_AT,
        ) == 0

        out = capsys.readouterr().out
        assert "event=predictions_written" in out
        assert "games=3" in out
        assert "benchmarked=2" in out
        assert "indexed=1" in out
        assert disk.get_bytes(INDEX_KEY)

    def test_the_week_defaults_to_the_one_about_to_be_played(
        self, rooted, calendar_dir, capsys
    ):
        """§9: "predict takes the week that is *about to* be played".

        The default comes from the committed calendar, not from this module — SPEC
        11 wants the workflow calling the command a human calls, with no week
        arithmetic in YAML.

        Run before the synthetic calendar's week 1 opens on 2026-08-29, so the
        coming week is 01. The slate's own kickoffs are in September and do not
        have to sit inside that window: the calendar picks the week *number*, and
        the games are selected by the ``week`` field CFBD puts on each row.
        """
        url, _ = rooted
        assert main(
            ["predict", "--season", "2026", "--store", url],
            now=datetime(2026, 8, 27, 12, tzinfo=UTC),
        ) == 0
        assert "week=01" in capsys.readouterr().out

    def test_the_default_moves_on_once_a_week_has_started(
        self, rooted, calendar_dir, capsys
    ):
        """The control. A default that always answered "01" would pass the test
        above and be wrong every week after the first.
        """
        url, _ = rooted
        # Past week 1's first kickoff, so week 2 is the one still ahead.
        assert main(["predict", "--season", "2026", "--store", url], now=GENERATED_AT) == 1
        assert "week 02 slate" in capsys.readouterr().err

    def test_out_of_season_is_a_logged_skip_not_a_failure(
        self, rooted, calendar_dir, capsys
    ):
        url, _ = rooted
        assert main(
            ["predict", "--season", "2026", "--store", url],
            now=datetime(2026, 4, 1, 12, tzinfo=UTC),
        ) == 0
        out = capsys.readouterr().out
        assert "result=skip" in out
        assert "reason=not_in_season" in out

    def test_past_the_last_week_is_a_logged_skip(self, rooted, calendar_dir, capsys):
        """Nothing ahead to predict. Raising would redden every December Thursday."""
        url, _ = rooted
        assert main(
            ["predict", "--season", "2026", "--force", "--store", url],
            now=datetime(2026, 12, 20, 12, tzinfo=UTC),
        ) == 0
        assert "reason=no_coming_week" in capsys.readouterr().out

    def test_a_missing_state_is_exit_1(self, tmp_path, calendar_dir, store, capsys):
        """The Thursday SLO failing loudly rather than writing nothing quietly."""
        disk = FileSnapshotStore(tmp_path)
        for key, data in sorted(store._objects.items()):  # noqa: SLF001
            if not key.startswith("elo/"):
                disk.put_bytes(key, data, "application/octet-stream")

        assert main(
            ["predict", "--season", "2026", "--week", "1", "--store", f"file://{tmp_path}"],
            now=GENERATED_AT,
        ) == 1
        assert "ReplayError" in capsys.readouterr().err

    def test_an_illegal_week_is_a_usage_error(self, rooted, calendar_dir):
        url, _ = rooted
        with pytest.raises(SystemExit) as excinfo:
            main(["predict", "--season", "2026", "--week", "16", "--store", url])
        assert excinfo.value.code == 2


class TestTheWeekOneContamination:
    """§3.6, which turns out to be exactly and demonstrably true.

    §3.6 argues: "In week 1 a prediction is Sagarin's rating gap divided by 28,
    multiplied by 28, plus Sagarin's HFA — which is Sagarin's prediction." It says
    this to justify a disclosure on the accuracy page, and until now it was an
    argument rather than a measurement.

    On seeded week-0 ratings it is an identity, not an approximation. The seed is
    `1500 + (rating - mean) * 28`, so an Elo gap over 28 is exactly a Sagarin
    rating gap; adding the same HFA Sagarin used reproduces its PREDICTOR margin
    to the floating-point bit. These assert that, which does two things: it
    verifies §3.6's premise, and it means §3.6's Pearson correlation opens the
    season at exactly 1.0 rather than merely near it.
    """

    def test_a_week_one_prediction_is_sagarins_prediction(self, log):
        benchmarked = [
            game for game in log.games if game.sagarin_predictor_margin is not None
        ]
        assert len(benchmarked) == 2
        for game in benchmarked:
            assert game.predicted_margin == pytest.approx(
                game.sagarin_predictor_margin, abs=1e-9
            )

    def test_it_holds_at_a_neutral_site_too(self, log):
        """Both sides drop the HFA, so the identity survives the one case where
        the two could have disagreed about what to add.
        """
        neutral = by_id(log)[302]
        assert neutral.neutral_site is True
        assert neutral.predicted_margin == pytest.approx(
            neutral.sagarin_predictor_margin, abs=1e-9
        )

    def test_which_is_why_the_disclosure_exists(self, log):
        """§3.6's threshold is `r >= 0.90` and week 1 opens at 1.0.

        Computed here rather than asserted from the spec, so the number the
        accuracy page will publish in week 1 is one this suite has actually seen.
        """
        pairs = [
            (game.predicted_margin, game.sagarin_predictor_margin)
            for game in log.games
            if game.sagarin_predictor_margin is not None
        ]
        ours = [p for p, _ in pairs]
        theirs = [s for _, s in pairs]
        # Two points, so a correlation is degenerate -- assert the identity that
        # makes it 1.0 rather than a coefficient over n=2.
        assert ours == pytest.approx(theirs, abs=1e-9)


def test_closing_line_is_null_until_a_lines_capture_exists(log):
    """Documented absence, asserted so it cannot be forgotten (§4.2).

    CFBD `/lines` has never been captured by this project — no snapshot, no
    fixture — and `cfb/CLAUDE.md` forbids calling CFBD from a test. A parser
    written against a remembered response shape would either raise on the first
    real Thursday or, worse, return `None` for every game and silently delete the
    headline benchmark of the whole project.

    §4.2 makes the field nullable, so this is a legal document rather than a hole.
    `predict._closing_line` is the one place to change.
    """
    assert all(game.closing_line is None for game in log.games)
