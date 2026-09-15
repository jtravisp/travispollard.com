"""Thursday-knowable roster capture (SPEC-phase3 section 3.2).

**The thing under test is a definition, not a parser.** Section 3.2's argument is
that the expectation has to be the *same function of the same information* in 2017
as on a Thursday in 2026, because anything else is retrospective leakage wearing a
feature's clothes. So the tests that matter here are the ones that pin what the
collector refuses to do: it never guesses a starter for a team with no passing
data, it never invents a basis it did not derive, and it never files the document
under the week it read instead of the week it describes.

No network, ever (`cfb/CLAUDE.md`). `fixtures/cfbd_players_2026_week02.json` is a
`/games/players` response in the vendor's shape, using names the committed
crosswalk already resolves.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb.collectors.roster import (
    BACKFILLABLE_BASES,
    ROSTER_SCHEMA_VERSION,
    ExpectedQb,
    TeamRoster,
    check_basis,
    fetch_roster,
    qb_expectations,
)
from cfb.crosswalk import load as load_crosswalk
from cfb.errors import RosterBasisError
from cfb.manifest import manifest_key
from cfb.models import Manifest
from cfb.storage import MemorySnapshotStore

SEASON = 2026
#: The Thursday inside week 3, which is when the real job runs.
THURSDAY = datetime(2026, 9, 17, 11, 45, 2, tzinfo=UTC)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture(scope="module")
def players() -> list[dict]:
    return json.loads((FIXTURES / "cfbd_players_2026_week02.json").read_bytes())


@pytest.fixture
def client(players):
    """A `CfbdClient` stand-in that serves the fixture and counts calls.

    Injected rather than patched, the same seam `fetch_cfbd`'s tests use: the
    budget and the bearer header are the client's business and are tested there.
    """

    class Stub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def get(self, path: str, **params) -> bytes:
            self.calls.append((path, params))
            return json.dumps(players).encode()

    return Stub()


# --- the expectation itself ---------------------------------------------------


class TestWhoIsExpectedToStart:
    def test_the_busiest_passer_is_the_expected_starter(self, players, crosswalk):
        rosters = {r.team: r for r in qb_expectations(players, crosswalk)}
        assert rosters["texas"].expected_qb.name == "Arch Manning"
        assert rosters["ohio-state"].expected_qb.name == "Julian Sayin"

    def test_every_expectation_from_a_box_score_says_so(self, players, crosswalk):
        """`basis` is the load-bearing field and this collector forms exactly one.

        A consumer training across eras filters on it, so a value that did not
        describe the derivation would make a mixed-era set quietly mean two
        different things -- the failure the schema exists to prevent.
        """
        for roster in qb_expectations(players, crosswalk):
            if roster.expected_qb is not None:
                assert roster.expected_qb.basis == "previous-game-starter"
                assert roster.expected_qb.basis in BACKFILLABLE_BASES

    def test_a_timeshare_is_reported_as_one_rather_than_resolved(self, players, crosswalk):
        """17 attempts to 15 is not a starter, and the document should not pretend.

        `usage_share` is published so a consumer can weigh this itself. Collapsing
        it to a bare name here would throw away the only evidence that the
        expectation is weak.
        """
        alabama = {r.team: r for r in qb_expectations(players, crosswalk)}["alabama"]
        assert alabama.expected_qb.name == "Ty Simpson"
        assert alabama.expected_qb.usage_share == pytest.approx(17 / 32, abs=1e-4)
        assert alabama.expected_qb.usage_share < 0.6

    def test_a_clear_starter_reads_as_one(self, players, crosswalk):
        texas = {r.team: r for r in qb_expectations(players, crosswalk)}["texas"]
        assert texas.expected_qb.usage_share == pytest.approx(28 / 31, abs=1e-4)

    def test_a_team_with_no_pass_attempts_gets_no_expectation(self, players, crosswalk):
        """**Never a guess.** The lowest-ranked available player is not a starter.

        Section 3.2 turns on the expectation being the same function everywhere,
        and a fallback would be a different function on exactly the rows where the
        data is thinnest.
        """
        georgia = {r.team: r for r in qb_expectations(players, crosswalk)}["georgia"]
        assert georgia.expected_qb is None

    def test_the_source_game_is_named(self, players, crosswalk):
        """So a human can check the expectation against the box score it came
        from, without re-deriving it."""
        texas = {r.team: r for r in qb_expectations(players, crosswalk)}["texas"]
        assert texas.expected_qb.last_game_id == 401917001

    def test_teams_are_canonical_ids_not_vendor_spellings(self, players, crosswalk):
        teams = {r.team for r in qb_expectations(players, crosswalk)}
        assert teams == {"texas", "ohio-state", "alabama", "georgia"}

    def test_an_unmapped_team_raises(self, crosswalk):
        """The hard rule in `cfb/CLAUDE.md`, reached through this path too."""
        from cfb.errors import UnmappedTeamError

        rows = [{"id": 1, "teams": [{"team": "Not A Real School", "categories": []}]}]
        with pytest.raises(UnmappedTeamError):
            qb_expectations(rows, crosswalk)

    def test_rushing_attempts_are_not_mistaken_for_passing(self, players, crosswalk):
        """Both categories publish a stat called ATT, and the running back has 12.

        Reading the wrong one would name a running back as the quarterback on
        every low-volume passing team, and the document would look entirely
        ordinary.
        """
        texas = {r.team: r for r in qb_expectations(players, crosswalk)}["texas"]
        assert texas.expected_qb.player_id == 4361


# --- the basis check ----------------------------------------------------------


class TestTheBasisIsChecked:
    def test_a_basis_this_collector_cannot_form_raises(self):
        """A box score cannot produce a depth chart.

        The model's `Literal` refuses an unknown string; this refuses a *known*
        one the evidence does not support -- which is the dangerous case, because
        the value a consumer trusts most is the one it would be most wrong about.
        """
        rosters = [
            TeamRoster(
                team="texas",
                expected_qb=ExpectedQb(
                    player_id=1, name="A", basis="depth-chart",
                    games_started=1, usage_share=1.0, last_game_id=9,
                ),
            )
        ]
        with pytest.raises(RosterBasisError, match="cannot form"):
            check_basis(rosters)

    def test_an_unrecognised_basis_is_refused_at_the_model(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExpectedQb(
                player_id=1, name="A", basis="vibes",
                games_started=1, usage_share=1.0, last_game_id=9,
            )

    def test_a_team_with_no_expectation_passes_the_check(self):
        check_basis([TeamRoster(team="georgia", expected_qb=None)])


# --- what lands in the bucket -------------------------------------------------


class TestTheCapture:
    def captured(self, client, crosswalk):
        store = MemorySnapshotStore()
        snapshot = fetch_roster(
            store=store, client=client, resolver=crosswalk,
            season=SEASON, week="03", source_week="02", now=THURSDAY,
        )
        return store, snapshot

    def test_it_queries_the_previous_week(self, client, crosswalk):
        """**The asymmetry is the feature.** A Thursday in week 3 forms week 3's
        expectation out of week 2's completed box scores."""
        self.captured(client, crosswalk)
        assert client.calls == [("/games/players", {"year": 2026, "week": 2})]

    def test_one_call_per_run(self, client, crosswalk):
        """~15 a season against the budget (SPEC-phase3 3.2)."""
        self.captured(client, crosswalk)
        assert len(client.calls) == 1

    def test_the_document_is_filed_under_the_week_it_describes(self, client, crosswalk):
        store, snapshot = self.captured(client, crosswalk)
        assert snapshot.week == "03"
        assert snapshot.source_week == "02"
        assert "raw/roster/season=2026/week=03/2026-09-17T114502Z.json" in store._objects

    def test_the_vendor_bytes_land_under_cfbd_unmodified(self, client, crosswalk, players):
        """The immutability rule is satisfied by what arrived, not by what this
        derived from it. `raw/roster/` is a computed document and says so.
        """
        store, snapshot = self.captured(client, crosswalk)
        evidence = snapshot.derived_from
        assert evidence.startswith("raw/cfbd/season=2026/week=02/players/")
        assert json.loads(store.get_bytes(evidence)) == players

    def test_the_derivation_can_be_replayed_without_a_network_call(
        self, client, crosswalk, players
    ):
        """`derived_from` points at the stored bytes, so the document can be
        rebuilt from `raw/` -- the same property `cfb elo replay` rests on."""
        store, snapshot = self.captured(client, crosswalk)
        again = qb_expectations(json.loads(store.get_bytes(snapshot.derived_from)), crosswalk)
        assert [r.model_dump() for r in again] == [r.model_dump() for r in snapshot.teams]

    def test_a_manifest_sits_beside_the_document(self, client, crosswalk):
        store, snapshot = self.captured(client, crosswalk)
        key = "raw/roster/season=2026/week=03/2026-09-17T114502Z.json"
        manifest = Manifest.model_validate_json(store.get_bytes(manifest_key(key)))
        assert manifest.source == "roster"
        assert manifest.resource == "roster-status"
        assert manifest.week == "03"
        assert manifest.week_resolution == "calendar"
        assert manifest.parse_ok is True
        assert manifest.team_count == 4
        assert manifest.snapshot_key == key

    def test_the_manifest_hash_matches_the_bytes(self, client, crosswalk):
        import hashlib

        store, _ = self.captured(client, crosswalk)
        key = "raw/roster/season=2026/week=03/2026-09-17T114502Z.json"
        manifest = Manifest.model_validate_json(store.get_bytes(manifest_key(key)))
        assert manifest.sha256 == hashlib.sha256(store.get_bytes(key)).hexdigest()

    def test_the_document_carries_its_schema_version(self, client, crosswalk):
        _, snapshot = self.captured(client, crosswalk)
        assert snapshot.schema_version == ROSTER_SCHEMA_VERSION
        assert snapshot.resource == "roster-status"

    def test_an_error_body_stored_with_a_200_is_refused(self, crosswalk):
        """The shape `_rows` guards against elsewhere, reached through this path."""

        class Stub:
            def get(self, path, **params):
                return b'{"message": "Unauthorized"}'

        with pytest.raises(RosterBasisError, match="expected the list"):
            fetch_roster(
                store=MemorySnapshotStore(), client=Stub(), resolver=crosswalk,
                season=SEASON, week="03", source_week="02", now=THURSDAY,
            )
