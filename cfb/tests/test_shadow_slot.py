"""The shadow slot and the v2 read path (SPEC-phase3 3.1, 3.1a, 3.3).

Two things are being proved here and only one of them is the new feature.

**The v2 read path is the more important half.** `predictions/` is append-only
and tamper-evident -- Phase 1 section 1.1 gave up git to keep the property that
the public record is of forecasts made before kickoff -- and eight documents were
already written for weeks 1 and 2 of a live season before this bump existed. They
are re-read every Monday by `cfb score` and `cfb elo replay`. A schema change
that could not read them would not be a migration, it would be the season's
record becoming unreadable, and no amount of care afterwards recovers that.

So: a v2 document parses, scores, and produces the same numbers it always did.

**The shadow half is a slot with nothing in it yet, built early on purpose.** If
the log cannot hold a second model until after a challenger passes the gate,
section 6.4's four-week clock starts at the worst possible moment. The tests that
matter are the refusals -- a shadow model on a page can never be un-published,
because four weeks of live pre-kickoff evidence cannot be assembled after the
fact.
"""

import json
from datetime import UTC, datetime

import pytest

from cfb.elo import FITTED, SCHEMA_VERSION, ModelConstants, win_probability
from cfb.errors import ShadowRoleError
from cfb.predict import (
    PUBLISHED_MODEL,
    Forecast,
    ModelBlock,
    PredictedGame,
    PredictionLog,
    parse_predictions,
    upgrade_to_v3,
)


@pytest.fixture(scope="module")
def crosswalk():
    from cfb.crosswalk import load as load_crosswalk

    return load_crosswalk(2026)


SEASON = 2026
WEEK = "01"
GENERATED_AT = "2026-09-03T12:00:00Z"
KICKOFF = "2026-09-05T19:00:00Z"


def v2_document(**overrides) -> dict:
    """A schema 2 log in exactly the shape `predictions/` already holds.

    Field for field what `write_predictions` produced before this bump: one
    ``model`` block, and the forecast flat on the game.
    """
    document = {
        "schema_version": 2,
        "season": SEASON,
        "week": WEEK,
        "generated_at": GENERATED_AT,
        "forecast_from": None,
        "model": {
            "name": "elo",
            "elo_per_point": 16.0,
            "k": 30.0,
            "hfa": 2.41,
            "hfa_source": "raw/sagarin/season=2026/week=01/x.meta.json",
            "seeded_from": "raw/sagarin/season=2026/week=preseason/y.txt",
            "elo_state": "elo/season=2026/week=preseason/z.json",
            "sagarin_predictions_from": "raw/sagarin/season=2026/week=01/x.txt",
            "market_lines_from": None,
        },
        "games": [
            {
                "cfbd_game_id": 401856682,
                "kickoff": KICKOFF,
                "home": "texas",
                "away": "ohio-state",
                "neutral_site": False,
                "predicted_margin": 7.0,
                "win_probability": 0.6,
                "elo_home": 2358.0,
                "elo_away": 2486.0,
                "market_line": -7.5,
                "market_line_source": "DraftKings",
                "sagarin_predictor_margin": 6.5,
            }
        ],
    }
    document.update(overrides)
    return document


# --- the v2 read path ---------------------------------------------------------


class TestAVersion2LogStillReads:
    """The eight documents already in the bucket, and every one written before
    2026-09-15."""

    def test_it_parses(self):
        log = parse_predictions(json.dumps(v2_document()))
        assert log.season == SEASON
        assert log.week == WEEK

    def test_its_stamps_survive_the_upgrade(self):
        """**The failure mode that is easy to miss.**

        The upgrade only moves keys the model block and the games own. A reader
        that broke `generated_at` or `kickoff` on the way would be rejecting the
        whole archive over fields it never touched -- which is exactly what a
        pydantic `mode="before"` validator does on a strict model, and why the
        upgrade is a plain function at the boundary instead.
        """
        log = parse_predictions(json.dumps(v2_document()))
        assert log.generated_at == datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        assert log.games[0].kickoff == datetime(2026, 9, 5, 19, 0, tzinfo=UTC)

    def test_the_single_model_reads_as_the_published_one(self):
        """A v2 log had exactly one model and it was the one on the site, so
        `published` is the truth about the document rather than a default."""
        log = parse_predictions(json.dumps(v2_document()))
        assert [block.name for block in log.models] == ["elo"]
        assert log.models[0].role == "published"
        assert log.model.name == "elo"
        assert log.shadows == []

    def test_the_flat_forecast_reads_as_an_elo_forecast(self):
        log = parse_predictions(json.dumps(v2_document()))
        game = log.games[0]
        assert set(game.forecasts) == {PUBLISHED_MODEL}
        assert game.forecasts[PUBLISHED_MODEL].predicted_margin == 7.0

    def test_every_existing_reader_goes_on_working_unchanged(self):
        """The accessors are why a schema bump did not become a rewrite.

        Scoring, the board, the publisher and the CLI all read these four
        attributes and none of them needed touching.
        """
        game = parse_predictions(json.dumps(v2_document())).games[0]
        assert game.predicted_margin == 7.0
        assert game.win_probability == 0.6
        assert game.elo_home == 2358.0
        assert game.elo_away == 2486.0

    def test_the_stored_version_is_reported_as_it_was_written(self):
        """The document says 2 because it *is* 2. Nothing rewrites it, so nothing
        may claim it was written under a schema that did not exist yet."""
        assert parse_predictions(json.dumps(v2_document())).schema_version == 2

    def test_nothing_is_written_back(self):
        """`upgrade_to_v3` takes a dict and returns one. There is no store, no
        key and no write anywhere on this path -- the archive is read, never
        amended."""
        original = v2_document()
        before = json.dumps(original, sort_keys=True)
        upgrade_to_v3(original)
        assert json.dumps(original, sort_keys=True) == before

    def test_a_v3_document_passes_through_untouched(self):
        payload = {"models": [{"name": "elo"}], "games": []}
        assert upgrade_to_v3(payload) is payload

    def test_a_partial_log_keeps_its_forecast_from(self):
        """`forecast_from` is what tells scoring a game nobody could have
        forecast from a join that failed, so it has to survive."""
        log = parse_predictions(json.dumps(v2_document(forecast_from=KICKOFF)))
        assert log.forecast_from == datetime(2026, 9, 5, 19, 0, tzinfo=UTC)


class TestAVersion2LogStillScores:
    """Reading it is not enough -- next Monday's run has to grade it."""

    def test_it_scores_to_the_same_numbers(self):
        from cfb.elo.scoring import score_week
        from cfb.sources import RawGame

        log = parse_predictions(json.dumps(v2_document()))
        result = RawGame.model_validate(
            {
                "id": 401856682,
                "season": SEASON,
                "week": 1,
                "seasonType": "regular",
                "startDate": "2026-09-05T19:00:00.000Z",
                "neutralSite": False,
                "homeTeam": "Texas",
                "awayTeam": "Ohio State",
                "homePoints": 24,
                "awayPoints": 17,
            }
        )
        scored = score_week(
            log,
            [result],
            results_fetched_at=datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
            now=datetime(2026, 9, 6, 12, 30, tzinfo=UTC),
        )
        assert len(scored.games) == 1
        assert scored.games[0].predicted_margin == 7.0
        assert scored.games[0].actual_margin == 7
        assert scored.games[0].error == 0.0


# --- the slot ----------------------------------------------------------------


def block(name: str, role: str) -> ModelBlock:
    return ModelBlock(name=name, role=role, elo_per_point=16.0, k=30.0, hfa=2.41)


def game_with(**forecasts) -> PredictedGame:
    return PredictedGame(
        cfbd_game_id=1,
        kickoff=datetime(2026, 9, 5, 19, 0, tzinfo=UTC),
        home="texas",
        away="ohio-state",
        neutral_site=False,
        forecasts={
            name: Forecast(**values) if isinstance(values, dict) else values
            for name, values in forecasts.items()
        },
        market_line=None,
        market_line_source=None,
        sagarin_predictor_margin=None,
    )


class TestTheShadowSlot:
    def test_a_shadow_model_sits_beside_the_published_one(self):
        log = PredictionLog(
            schema_version=SCHEMA_VERSION,
            season=SEASON,
            week=WEEK,
            generated_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            models=[block("elo", "published"), block("ngb-t", "shadow")],
            games=[
                game_with(
                    elo={"predicted_margin": 7.1, "win_probability": 0.68},
                    **{"ngb-t": {"predicted_margin": 6.4, "win_probability": 0.64}},
                )
            ],
        )
        assert [b.name for b in log.shadows] == ["ngb-t"]
        assert log.model.name == "elo"

    def test_the_published_accessors_read_the_published_model(self):
        """A shadow's numbers must never be what `predicted_margin` answers --
        every mean in this project is computed through that attribute."""
        log = PredictionLog(
            schema_version=SCHEMA_VERSION,
            season=SEASON,
            week=WEEK,
            generated_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            models=[block("elo", "published"), block("ngb-t", "shadow")],
            games=[
                game_with(
                    elo={"predicted_margin": 7.1, "win_probability": 0.68},
                    **{"ngb-t": {"predicted_margin": 99.0, "win_probability": 0.99}},
                )
            ],
        )
        assert log.games[0].predicted_margin == 7.1
        assert log.games[0].win_probability == 0.68

    def test_a_challenger_may_carry_numbers_elo_has_no_name_for(self):
        """§3.3's own example puts `sigma` on the NGBoost block. A log that
        refused it could not hold the model the slot was built for."""
        forecast = Forecast(predicted_margin=6.4, win_probability=0.64, sigma=16.8)
        assert forecast.model_dump()["sigma"] == 16.8

    def test_a_log_with_no_published_model_is_refused(self):
        with pytest.raises(ShadowRoleError, match="none is published"):
            PredictionLog(
                schema_version=SCHEMA_VERSION,
                season=SEASON,
                week=WEEK,
                generated_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
                models=[block("ngb-t", "shadow")],
                games=[],
            )

    def test_two_published_models_are_refused(self):
        """"Which forecast is the site showing" would have no answer, and a
        reader would silently take whichever came first."""
        with pytest.raises(ShadowRoleError, match="2 published models"):
            PredictionLog(
                schema_version=SCHEMA_VERSION,
                season=SEASON,
                week=WEEK,
                generated_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
                models=[block("elo", "published"), block("ngb-t", "published")],
                games=[],
            )

    def test_a_row_with_only_shadow_forecasts_refuses_to_be_read(self):
        game = game_with(**{"ngb-t": {"predicted_margin": 6.4, "win_probability": 0.64}})
        with pytest.raises(ShadowRoleError, match="none from 'elo'"):
            _ = game.predicted_margin

    def test_an_unrecognised_role_is_refused_at_the_model(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            block("ngb-t", "candidate")


# --- the probability scale ----------------------------------------------------


class TestTheProbabilityScale:
    """SPEC-phase3 3.1. One constant was doing two jobs."""

    def test_none_means_the_elo_scale_which_is_what_every_stored_log_used(self):
        """**Backwards compatibility, stated as an identity rather than hoped for.**

        A set of constants written before this field existed must produce exactly
        the probability it published, or every Brier score in `scored/` silently
        describes a model that never ran.
        """
        assert FITTED.probability_scale is None
        assert FITTED.effective_probability_scale == FITTED.elo_per_point

    @pytest.mark.parametrize("margin", [-21.0, -7.0, 0.0, 3.5, 14.0, 38.0])
    def test_a_null_scale_reproduces_the_published_probability(self, margin):
        legacy = 1 / (1 + 10 ** (-(margin * FITTED.elo_per_point) / 400))
        assert win_probability(margin, constants=FITTED) == pytest.approx(legacy, abs=1e-12)

    def test_a_fitted_scale_is_used_when_present(self):
        recalibrated = FITTED.model_copy(update={"probability_scale": 14.0})
        assert recalibrated.effective_probability_scale == 14.0
        assert win_probability(7.0, constants=recalibrated) != win_probability(
            7.0, constants=FITTED
        )

    def test_the_margin_still_determines_the_probability(self):
        """The identity the PRD requires, and the reason isotonic regression was
        rejected: probability stays a deterministic function of margin, through
        its own scale."""
        recalibrated = FITTED.model_copy(update={"probability_scale": 14.0})
        assert win_probability(7.0, constants=recalibrated) == win_probability(
            7.0, constants=recalibrated
        )
        assert win_probability(0.0, constants=recalibrated) == pytest.approx(0.5)

    def test_a_larger_scale_is_more_confident(self):
        flat = ModelConstants(
            elo_per_point=16.0, k=30.0, mov_damping=0.05, mov_denominator_floor=1.0,
            hfa_source="sagarin", probability_scale=8.0,
        )
        steep = flat.model_copy(update={"probability_scale": 32.0})
        assert win_probability(7.0, constants=steep) > win_probability(7.0, constants=flat)

    def test_the_envelope_moved_for_the_renamed_field(self):
        assert SCHEMA_VERSION == 3


# --- the guard, end to end ----------------------------------------------------


class TestAShadowModelCannotReachAPage:
    """SPEC-phase3 3.3's normative half, checked rather than assumed.

    Shadow forecasts are already excluded structurally: every builder reads the
    published model by name. This covers what structure cannot -- a future field,
    or a future builder, carrying one out by a route nobody thought about.
    """

    def published_with_a_shadow(self, crosswalk):
        """A real week's log, rewritten to carry a shadow model beside Elo.

        Written through `write_predictions` at a second timestamp rather than by
        editing the first: `predictions/` is write-once and a test that reached
        around that would be testing a store this project does not have.
        """
        from cfb.predict import predict_week, write_predictions
        from test_publish_history import GENERATED_AT, seeded, texas_game
        from test_publish_history import SEASON as S

        store = seeded(crosswalk, [texas_game()])
        honest = predict_week(
            store=store, season=S, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        with_shadow = honest.model_copy(
            update={
                "generated_at": GENERATED_AT.replace(hour=13),
                "models": [*honest.models, block("ngb-t", "shadow")],
                "games": [
                    g.model_copy(
                        update={
                            "forecasts": {
                                **g.forecasts,
                                "ngb-t": Forecast(
                                    predicted_margin=99.0, win_probability=0.99
                                ),
                            }
                        }
                    )
                    for g in honest.games
                ],
            }
        )
        write_predictions(store, with_shadow)
        return store, S

    def test_the_shadow_is_stored_in_the_log(self, crosswalk):
        """It has to reach the append-only record -- that is the whole point of
        shadow mode, and the only way 6.4's four weeks accrue."""
        from cfb.predict import prediction_generations, read_predictions

        store, season = self.published_with_a_shadow(crosswalk)
        newest = prediction_generations(store, season=season, week="01")[-1][1]
        assert [b.name for b in read_predictions(store, newest).shadows] == ["ngb-t"]

    def test_it_reaches_no_published_document(self, crosswalk):
        from cfb.publish import publish

        store, season = self.published_with_a_shadow(crosswalk)
        publish(store=store, season=season, week="01",
                now=datetime(2026, 9, 3, 14, 0, tzinfo=UTC), crosswalk=crosswalk)

        for key in ("cfb/data/slate.json", "cfb/data/models.json",
                    "cfb/data/next-game.json", "cfb/data/accuracy.json"):
            body = store.get_bytes(key).decode()
            assert "ngb-t" not in body, f"{key} names the shadow model"
            assert "99.0" not in body, f"{key} carries the shadow model's margin"

    def test_the_published_numbers_are_elos(self, crosswalk):
        """The shadow forecast is deliberately absurd, so a leak would be visible
        in the number rather than only in the name."""
        import json as _json

        from cfb.publish import publish

        store, season = self.published_with_a_shadow(crosswalk)
        publish(store=store, season=season, week="01",
                now=datetime(2026, 9, 3, 14, 0, tzinfo=UTC), crosswalk=crosswalk)
        slate = _json.loads(store.get_bytes("cfb/data/slate.json"))
        assert all(g["predicted_margin"] != 99.0 for g in slate["games"])

    def test_a_leak_raises_rather_than_being_filtered(self, crosswalk):
        """The guard itself. A document that named the shadow would stop the
        publish, because a model on a page before it has served its four weeks
        can never be un-published.
        """
        from cfb.publish import _refuse_shadow_leak

        store, season = self.published_with_a_shadow(crosswalk)

        class Leaky:
            def model_dump_json(self) -> str:
                return '{"systems": [{"id": "ngb-t"}]}'

        with pytest.raises(ShadowRoleError, match="names the shadow model"):
            _refuse_shadow_leak(
                store, season=season, week="01", documents={"models": Leaky()}
            )

    def test_the_guard_is_silent_when_there_are_no_shadows(self, crosswalk):
        """Every week until a challenger is fitted, which is all of them today."""
        from cfb.predict import predict_week, write_predictions
        from cfb.publish import _refuse_shadow_leak
        from test_publish_history import GENERATED_AT, seeded, texas_game

        store = seeded(crosswalk, [texas_game()])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )

        class Anything:
            def model_dump_json(self) -> str:
                return '{"anything": "ngb-t"}'

        _refuse_shadow_leak(
            store, season=SEASON, week="01", documents={"models": Anything()}
        )
