"""Tests for the snapshot-level validators (SPEC-phase0 4.5).

The parsers already raise on everything checked here, and they raise earlier and
name the offending line. ``SagarinSnapshot`` is deliberate defence in depth: a
future parser change that reintroduces a duplicate rank must not be able to reach
the manifest. A defence nobody tests is not a defence, so these build snapshots by
hand from the golden capture and then break them.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from cfb.errors import DuplicateRankError, ParseError
from cfb.models import SagarinSnapshot
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def page() -> str:
    return (FIXTURES / "sagarin_2026_preseason.txt").read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def parts(page):
    return {
        "fetched_at": datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        "page_date_stamp": parse_page_date_stamp(page),
        "page_state": parse_page_state(page),
        "hfa": parse_hfa(page),
        "teams": parse_ratings(page),
        "predictions": parse_predictions(page),
    }


def test_the_golden_capture_assembles_into_a_snapshot(parts):
    snapshot = SagarinSnapshot(**parts)

    assert len(snapshot.teams) == 266
    assert len(snapshot.predictions) == 53
    assert snapshot.page_state == "preseason"
    assert snapshot.page_date_stamp is None
    assert snapshot.hfa["predictor"] == 2.41


def test_an_empty_hfa_raises(parts):
    """There is no default home-field advantage to fall back to."""
    with pytest.raises(ParseError) as excinfo:
        SagarinSnapshot(**{**parts, "hfa": {}})
    assert "no default" in str(excinfo.value)


def test_a_duplicate_team_rank_raises(parts):
    teams = list(parts["teams"])
    teams[42] = teams[42].model_copy(update={"rank": teams[41].rank})

    with pytest.raises(DuplicateRankError) as excinfo:
        SagarinSnapshot(**{**parts, "teams": teams})
    assert "team rank" in str(excinfo.value)


def test_a_duplicate_prediction_rank_raises(parts):
    predictions = list(parts["predictions"])
    predictions[1] = predictions[1].model_copy(update={"rank": predictions[0].rank})

    with pytest.raises(DuplicateRankError) as excinfo:
        SagarinSnapshot(**{**parts, "predictions": predictions})
    assert "prediction rank" in str(excinfo.value)


def test_a_preseason_page_whose_columns_disagree_raises(parts):
    """The title line and the columns must tell the same story.

    A page claiming STARTING while its rating columns diverge is contradicting
    itself, and guessing which half is right is the coercion this project forbids.
    """
    teams = list(parts["teams"])
    teams[0] = teams[0].model_copy(update={"predictor": teams[0].predictor + 1.0})

    with pytest.raises(ParseError) as excinfo:
        SagarinSnapshot(**{**parts, "teams": teams})
    assert "preseason" in str(excinfo.value)


def test_a_preseason_page_with_a_played_record_raises(parts):
    teams = list(parts["teams"])
    teams[0] = teams[0].model_copy(update={"wins": 1})

    with pytest.raises(ParseError) as excinfo:
        SagarinSnapshot(**{**parts, "teams": teams})
    assert "1-0 record" in str(excinfo.value)


def test_the_degeneracy_check_is_scoped_to_preseason(parts):
    """An in-season page is expected to have diverging columns and real records."""
    teams = list(parts["teams"])
    teams[0] = teams[0].model_copy(update={"predictor": teams[0].predictor + 1.0, "wins": 3})

    snapshot = SagarinSnapshot(**{**parts, "page_state": "in-season", "teams": teams})
    assert snapshot.teams[0].wins == 3


def test_the_models_are_frozen(parts):
    """A parsed row is evidence; nothing downstream may edit it."""
    snapshot = SagarinSnapshot(**parts)
    with pytest.raises(PydanticValidationError):
        snapshot.teams[0].rating = 0.0
