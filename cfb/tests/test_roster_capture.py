"""Thursday-knowable roster capture (SPEC-phase3 section 3.2).

**The thing under test is a definition, not a parser.** Section 3.2's argument is
that the expectation has to be the *same function of the same information* in 2017
as on a Thursday in 2026, because anything else is retrospective leakage wearing a
feature's clothes. So the tests that matter here are the ones that pin what the
collector refuses to do: it never guesses a starter for a team with no passing
data, it never invents a basis it did not derive, and it never files the document
under the week it read instead of the week it describes.

No network, ever (`cfb/CLAUDE.md`). `fixtures/cfbd_players_2026_week02.json` is
**three real games trimmed out of the stored 2026 week 2 capture**, byte-for-byte
as CFBD sent them.

**That provenance is the point, and it was learned the hard way.** The first
version of this fixture was written from the shape the spec implied -- a passing
category with an `ATT` stat holding an integer. The real response spells it
`C/ATT` and holds `"23/37"`; a bare `ATT` exists only under *rushing*. Against
invented bytes the collector passed twenty-one tests, and against the real
capture it produced 240 teams and **zero** expectations without raising anything.
A fixture that encodes an assumption tests the assumption.
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
from cfb.errors import ReplayError, RosterBasisError
from cfb.manifest import manifest_key
from cfb.models import Manifest
from cfb.sources import week_slate
from cfb.storage import MemorySnapshotStore
from test_replay import cfbd_game, put_games

SEASON = 2026
#: The Thursday inside week 3, which is when the real job runs.
THURSDAY = datetime(2026, 9, 17, 11, 45, 2, tzinfo=UTC)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture(scope="module")
def players() -> list[dict]:
    # Bytes, not text. `sources._rows` records why: the responses carry accented
    # names (San José State) that a text read under a non-UTF-8 default locale
    # mangles into something the crosswalk cannot resolve.
    return json.loads((FIXTURES / "cfbd_players_2026_week02.json").read_bytes())


#: The fixture's own games, standing in for `week_slate`'s selection.
@pytest.fixture(scope="module")
def only_games(players) -> set[int]:
    return {row["id"] for row in players}


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
    def expectations(self, players, crosswalk, only_games):
        return {r.team: r for r in qb_expectations(players, crosswalk, only_games=only_games)}

    def test_the_busiest_passer_is_the_expected_starter(self, players, crosswalk, only_games):
        rosters = self.expectations(players, crosswalk, only_games)
        assert rosters["texas"].expected_qb.name == "Arch Manning"
        assert rosters["ohio-state"].expected_qb.name == "Julian Sayin"
        assert rosters["alabama"].expected_qb.name == "Keelon Russell"

    def test_attempts_are_read_from_the_slash_value(self, players, crosswalk, only_games):
        """**The bug a guessed fixture could not catch.**

        The passing category spells the stat ``C/ATT`` and the value is
        ``"23/37"`` -- completions over attempts. A bare ``ATT`` exists under
        *rushing*, so a reader matching on ``"ATT"`` finds no passing stat, names
        nobody, and raises nothing. Against the real week 2 capture that produced
        240 teams and zero expectations.
        """
        texas = self.expectations(players, crosswalk, only_games)["texas"]
        assert texas.expected_qb.usage_share == 1.0

    def test_attempts_not_completions_decide_it(self, players, crosswalk, only_games):
        """A quarterback who went 2-for-14 still took the snaps."""
        virginia = self.expectations(players, crosswalk, only_games)["virginia"]
        # Pribula 12/14, Geer 2/4, Holstein 4/6 -> 14 of 24 attempts.
        assert virginia.expected_qb.name == "Beau Pribula"
        assert virginia.expected_qb.usage_share == pytest.approx(14 / 24, abs=1e-4)

    def test_every_expectation_from_a_box_score_says_so(self, players, crosswalk, only_games):
        """``basis`` is the load-bearing field and this collector forms exactly one.

        A consumer training across eras filters on it, so a value that did not
        describe the derivation would make a mixed-era set quietly mean two
        different things -- the failure the schema exists to prevent.
        """
        for roster in self.expectations(players, crosswalk, only_games).values():
            if roster.expected_qb is not None:
                assert roster.expected_qb.basis == "previous-game-starter"
                assert roster.expected_qb.basis in BACKFILLABLE_BASES

    def test_a_timeshare_is_reported_as_one_rather_than_resolved(
        self, players, crosswalk, only_games
    ):
        """Virginia played three quarterbacks and the document should say so.

        ``usage_share`` is published so a consumer can weigh this itself.
        Collapsing it to a bare name would throw away the only evidence that the
        expectation is weak -- and 0.58 is a materially different claim from 1.00.
        """
        virginia = self.expectations(players, crosswalk, only_games)["virginia"]
        assert virginia.expected_qb.usage_share < 0.6

    def test_a_clear_starter_reads_as_one(self, players, crosswalk, only_games):
        rosters = self.expectations(players, crosswalk, only_games)
        assert rosters["texas"].expected_qb.usage_share == 1.0
        assert rosters["ohio-state"].expected_qb.usage_share == 1.0

    def test_a_vendor_pseudo_athlete_does_not_win_the_job(self, players, crosswalk, only_games):
        """Kentucky's box score carries a ``" Team"`` row at 0/1 beside the starter.

        It is a real entry in the real response -- a sack or a team-charged
        attempt -- and it costs the starter a point of usage share rather than the
        job. Worth pinning: it is exactly the shape that would take the job on a
        week where the starter attempted one pass.
        """
        kentucky = self.expectations(players, crosswalk, only_games)["kentucky"]
        assert kentucky.expected_qb.name == "Kenny Minchey"
        assert kentucky.expected_qb.usage_share == pytest.approx(31 / 32, abs=1e-4)

    def test_the_source_game_is_named(self, players, crosswalk, only_games):
        """So a human can check the expectation against the box score it came
        from, without re-deriving it."""
        texas = self.expectations(players, crosswalk, only_games)["texas"]
        assert texas.expected_qb.last_game_id == 401856682

    def test_player_ids_are_the_vendors(self, players, crosswalk, only_games):
        texas = self.expectations(players, crosswalk, only_games)["texas"]
        assert texas.expected_qb.player_id == 4870906

    def test_teams_are_canonical_ids_not_vendor_spellings(self, players, crosswalk, only_games):
        assert set(self.expectations(players, crosswalk, only_games)) == {
            "texas",
            "ohio-state",
            "alabama",
            "kentucky",
            "virginia",
            "norfolk-state",
        }

    def test_an_fcs_opponent_is_covered_too(self, players, crosswalk, only_games):
        """FCS teams are in the crosswalk and in the model's universe (SPEC 6.5)."""
        norfolk = self.expectations(players, crosswalk, only_games)["norfolk-state"]
        assert norfolk.expected_qb.name == "Deljay Bailey"

    def test_a_team_with_no_pass_attempts_gets_no_expectation(self, crosswalk):
        """**Never a guess.** The lowest-ranked available player is not a starter.

        Section 3.2 turns on the expectation being the same function everywhere,
        and a fallback would be a different function on exactly the rows where the
        data is thinnest.
        """
        rows = [{"id": 9, "teams": [{"team": "Texas", "categories": []}]}]
        rosters = qb_expectations(rows, crosswalk, only_games={9})
        assert rosters[0].team == "texas"
        assert rosters[0].expected_qb is None

    def test_a_stat_value_without_a_slash_is_not_guessed_at(self, crosswalk):
        """A shape change leaves the team with no expectation, not a wrong one."""
        rows = [
            {
                "id": 9,
                "teams": [
                    {
                        "team": "Texas",
                        "categories": [
                            {
                                "name": "passing",
                                "types": [
                                    {
                                        "name": "C/ATT",
                                        "athletes": [{"id": "1", "name": "A", "stat": "37"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        assert qb_expectations(rows, crosswalk, only_games={9})[0].expected_qb is None

    def test_rushing_attempts_are_not_mistaken_for_passing(self, crosswalk):
        """Both categories publish an attempts stat, spelled differently.

        Reading rushing would name a running back as the quarterback on every
        low-volume passing team, and the document would look entirely ordinary.
        """
        rows = [
            {
                "id": 9,
                "teams": [
                    {
                        "team": "Texas",
                        "categories": [
                            {
                                "name": "rushing",
                                "types": [
                                    {
                                        "name": "ATT",
                                        "athletes": [
                                            {"id": "5", "name": "A Back", "stat": "22"}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        assert qb_expectations(rows, crosswalk, only_games={9})[0].expected_qb is None


# --- what is ours, and what is merely in the response -------------------------


class TestTheSelection:
    """``/games/players`` returns every division; the crosswalk rates two of them."""

    def test_a_game_outside_the_selection_is_not_read(self, crosswalk):
        """**A selection, not a filter.**

        Week 2 of 2026 came back with 131 games against the 120 this project
        models, the extra eleven naming Bowie State, Central Oklahoma and
        Dickinson. Those teams are not in the crosswalk and correctly raise, so
        they are excluded by the vendor's own classification before any name is
        resolved -- through ``week_slate``, the one place that decides what the
        model rates.
        """
        rows = [
            {
                "id": 1,
                "teams": [
                    {
                        "team": "Texas",
                        "categories": [
                            {
                                "name": "passing",
                                "types": [
                                    {
                                        "name": "C/ATT",
                                        "athletes": [
                                            {"id": "1", "name": "Arch Manning", "stat": "23/37"}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {"id": 2, "teams": [{"team": "Central Oklahoma", "categories": []}]},
        ]
        rosters = qb_expectations(rows, crosswalk, only_games={1})
        assert [r.team for r in rosters] == ["texas"]

    def test_an_unmapped_team_inside_the_selection_still_raises(self, crosswalk):
        """The hard rule in ``cfb/CLAUDE.md`` survives the selection.

        Filtering on *whether the crosswalk resolved* would have turned this into
        a silent drop, and a genuinely unmapped FBS team would vanish along with
        the D-II ones.
        """
        from cfb.errors import UnmappedTeamError

        rows = [{"id": 1, "teams": [{"team": "Central Oklahoma", "categories": []}]}]
        with pytest.raises(UnmappedTeamError, match="Central Oklahoma"):
            qb_expectations(rows, crosswalk, only_games={1})


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
    """The two objects that land, and the order they land in."""

    #: The three fixture games as `/games` rows, which is what `week_slate` reads
    #: to decide which box scores are ours. Classified, so the per-capture rule in
    #: `RawGame.is_modelled` has evidence to work from.
    SLATE = [
        ("Virginia", "fbs", "Norfolk State", "fcs", 401858220),
        ("Alabama", "fbs", "Kentucky", "fbs", 401856674),
        ("Texas", "fbs", "Ohio State", "fbs", 401856682),
    ]

    def seeded(self) -> MemorySnapshotStore:
        store = MemorySnapshotStore()
        put_games(
            store,
            week="02",
            fetched_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
            games=[
                {
                    **cfbd_game(
                        game_id=game_id, week=2,
                        kickoff=datetime(2026, 9, 12, 23, 30, tzinfo=UTC),
                        home=home, away=away, home_points=24, away_points=17,
                    ),
                    "homeClassification": home_division,
                    "awayClassification": away_division,
                }
                for home, home_division, away, away_division, game_id in self.SLATE
            ],
        )
        return store

    def captured(self, client, crosswalk):
        store = self.seeded()
        snapshot = fetch_roster(
            store=store, client=client, resolver=crosswalk,
            season=SEASON, week="03", source_week="02", now=THURSDAY,
        )
        return store, snapshot

    def test_it_refuses_when_the_source_week_was_never_captured(self, client, crosswalk):
        """Without the games capture there is no way to tell which box scores are
        ours, and guessing is the one thing this must not do. The message names
        the command that fixes it.
        """
        with pytest.raises(ReplayError, match="uv run cfb fetch cfbd --resource games"):
            fetch_roster(
                store=MemorySnapshotStore(), client=client, resolver=crosswalk,
                season=SEASON, week="03", source_week="02", now=THURSDAY,
            )

    def test_the_api_call_is_still_spent_and_the_evidence_still_stored(
        self, client, crosswalk
    ):
        """**The refusal happens after the write, on purpose.**

        A missing games capture costs the call -- it has already been made -- but
        it must never cost the bytes. `raw/` is write-once and the response is
        gone if it is not stored, so the selection is read after the snapshot
        lands, not before.
        """
        store = MemorySnapshotStore()
        with pytest.raises(ReplayError):
            fetch_roster(
                store=store, client=client, resolver=crosswalk,
                season=SEASON, week="03", source_week="02", now=THURSDAY,
            )
        assert any(k.startswith("raw/cfbd/season=2026/week=02/players/") for k in store._objects)

    def test_only_the_modelled_games_are_read(self, client, crosswalk):
        """All three fixture games are modelled, so all six teams appear."""
        _, snapshot = self.captured(client, crosswalk)
        assert len(snapshot.teams) == 6
        assert all(team.expected_qb is not None for team in snapshot.teams)

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
        slate, _ = week_slate(store, SEASON, lambda raw: raw.partition == snapshot.source_week)
        again = qb_expectations(
            json.loads(store.get_bytes(snapshot.derived_from)),
            crosswalk,
            only_games={game.id for game, _ in slate},
        )
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
        assert manifest.team_count == 6
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
