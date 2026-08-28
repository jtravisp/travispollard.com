"""The crosswalk roster fixtures (SPEC-phase0 6.5).

SPEC 6.5 makes these files the contract: every name in them must resolve through
the crosswalk, and no crosswalk entry may reference a name absent from them. The
crosswalk does not exist yet, so none of those assertions can run. What can run
is everything about the fixtures themselves -- and a fixture that is wrong is a
contract that certifies the wrong thing, so it is worth checking before anything
depends on it.

``cfbd-2026.json`` is derived from one real ``/teams?year=2026`` call,
snapshotted to ``raw/cfbd/season=2026/week=season/teams/`` first, per the
immutability rule. Source sha256
``6a0bd09d1eff5ed66b4ba6111cb706aeb6e7c812bfef3c6b48a31aa474d84ea5``.

Four fields are kept out of the thirteen CFBD returns. The crosswalk maps a name
to a canonical id; logos, colours, mascots and twitter handles churn without ever
affecting whether a name resolves, and a fixture that churns is one nobody trusts
as a contract.

``sagarin-2026.txt`` is the other half and is not written yet. It is generatable
today -- all 266 names parse clean off the golden capture -- and is deliberately
left until the crosswalk needs it, so the roster and the resolver land together.
"""

import json
from pathlib import Path

import pytest

from cfb.parsers.sagarin_ratings import parse_ratings

FIXTURES = Path(__file__).parent / "fixtures"
CFBD_ROSTER = FIXTURES / "rosters" / "cfbd-2026.json"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"

#: SPEC 4.7 states both of these independently, from the Sagarin side.
FBS_COUNT = 138
FCS_COUNT = 128


@pytest.fixture(scope="module")
def roster() -> list[dict]:
    return json.loads(CFBD_ROSTER.read_bytes())


def test_the_roster_is_both_divisions(roster):
    """Widened from FBS-only when SPEC 6.5 settled the FCS question.

    `/games` returns FCS opponents by CFBD name, so an FBS-only roster makes the
    first FBS-vs-FCS game of September unjoinable. D-II and D-III are excluded:
    Sagarin rates none of them, so the crosswalk can never be asked.
    """
    counts = {"fbs": 0, "fcs": 0}
    for team in roster:
        counts[team["classification"]] = counts.get(team["classification"], 0) + 1
    assert counts == {"fbs": FBS_COUNT, "fcs": FCS_COUNT}
    assert len(roster) == FBS_COUNT + FCS_COUNT


def test_the_two_sources_agree_on_how_many_fbs_teams_there_are(roster):
    """Independent corroboration, which is the only kind worth having.

    SPEC 4.7 records 138 division-``A`` teams counted off the Sagarin page, and
    notes it is 138 rather than the 134 someone might expect. CFBD's ``/teams``
    returns 138 as well. Two vendors who do not talk to each other arriving at the
    same number is the strongest evidence available that neither parser is
    dropping rows.
    """
    teams = parse_ratings(GOLDEN.read_bytes().decode("utf-8"))
    sagarin_fbs = sum(1 for team in teams if team.division == "A")
    cfbd_fbs = sum(1 for team in roster if team["classification"] == "fbs")
    assert sagarin_fbs == cfbd_fbs == FBS_COUNT


def test_every_id_is_unique(roster):
    """``cfbd_id`` is what a crosswalk entry pins to (SPEC 6.1).

    A name can be re-branded between seasons; the id is the stable half of the
    mapping, and a duplicate would make it useless as one.
    """
    ids = [team["id"] for team in roster]
    assert len(set(ids)) == len(ids)


def test_every_school_name_is_unique(roster):
    """SPEC 6.5: no source name may map to two canonical ids.

    That assertion is about the crosswalk, but it is only satisfiable if the
    source itself does not print one name twice.
    """
    schools = [team["school"] for team in roster]
    assert len(set(schools)) == len(schools)


def test_no_name_or_conference_is_blank(roster):
    """An empty string resolves to nothing and looks like a name in a diff."""
    assert all(team["school"].strip() for team in roster)
    assert all(team["conference"].strip() for team in roster)


def test_the_names_spec_6_1_maps_by_hand_are_present_and_spelled_as_shown(roster):
    """The three SPEC 6.1 uses as examples, checked against the real vendor strings.

    All three are cases where the CFBD name and the Sagarin name differ enough
    that similarity scoring is no help -- ``"Southern California" ~ USC (0.09)``
    is the one SPEC 6.3 calls out. Pinning the CFBD spelling here means a change
    on the vendor's side shows up as a fixture failure rather than as an
    ``UnmappedTeamError`` in a scheduled run.
    """
    by_id = {team["id"]: team["school"] for team in roster}
    assert by_id[30] == "USC"
    assert by_id[2116] == "UCF"
    assert by_id[245] == "Texas A&M"


def test_the_fixture_is_sorted_by_school(roster):
    """So a re-generation next season is a readable diff rather than a rewrite."""
    assert roster == sorted(roster, key=lambda team: team["school"])


def test_the_two_sources_agree_on_the_fcs_count_too(roster):
    """The gap that forced SPEC 6.5's decision, now closed.

    This test used to assert the opposite -- that the 128 Sagarin FCS names had
    *no* counterpart here, because the fixture came from ``/teams/fbs``. Pulling
    ``/teams`` instead gives 138 + 128, and both numbers match what the Sagarin
    page says independently.
    """
    teams = parse_ratings(GOLDEN.read_bytes().decode("utf-8"))
    sagarin_fcs = sum(1 for team in teams if team.division == "AA")
    cfbd_fcs = sum(1 for team in roster if team["classification"] == "fcs")
    assert sagarin_fcs == cfbd_fcs == FCS_COUNT
    assert len(teams) == len(roster) == 266
