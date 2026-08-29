"""Betting lines, against the real capture (SPEC-phase1 4.2).

Every assertion here runs against `fixtures/cfbd_lines_2026_week01.json`, which is
a verbatim `/lines?year=2026&week=1` response: 143 games, 194 line entries, three
provider spellings, two books. Nothing in this file was written from a remembered
response shape, and four things the capture settled contradict what the spec said
before it existed.

## 1. There is no closing line

The fields are `spread` and `spreadOpen`. There is no `spreadClose`, no
`closingSpread`, nothing with "clos" in the name anywhere in the response. §4.2,
§5.3 and §6.3 all said "closing line" and none of them could have had one: a
Thursday fetch returns the line *at the moment of capture*, and the closing line
by definition does not exist until kickoff.

So the field is `market_line` and the document says what it is rather than what we
wished it were.

## 2. The sign is opposite to `predicted_margin`

`spread: -29.5` with `formattedSpread: "Iowa State -29.5"`, Iowa State home. So
**negative means the home team is favoured**, while `predicted_margin` positive
means the home team wins by that much. The two conventions point opposite ways.

Verified across all 194 entries in the capture, in both directions and with zero
exceptions: `spread < 0` exactly when `formattedSpread` names the home team, and
`spread > 0` exactly when it names the away team.

The vendor value is stored verbatim and `market_home_margin` is the one place the
conversion happens. `TestTheSign` is written to fail if that flip is dropped —
without it every ATS record in §5.3 would be plausible and backwards, which is the
kind of wrong that never announces itself.

## 3. Providers need normalizing before they can be selected

The capture spells one book two ways: `DraftKings` (131 entries) and
`Draft Kings` (12). Selecting before normalizing treats them as different books.

And selection is not cosmetic — **DraftKings and Bovada disagree on 21 of the 143
games**, so which one is preferred changes the stored number. That is why the
resolved provider is carried into the prediction row: §6.3's `line_source` was
going to be a guess, and now it is a fact about the run.

## 4. A null line is legal and must never become a zero

No game in *this* capture lacks a line and no `spread` is null, so the null path
is the join: a game on the `/games` slate with no entry in the `/lines` response
at all. `TestTheJoin` covers it, and asserts the value is `None` rather than
`0.0` — a zero would read as "pick'em", which is a real and very different claim.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb.elo.state import write_state
from cfb.errors import UnknownProviderError
from cfb.models import Manifest
from cfb.predict import predict_week
from cfb.replay import seed_state
from cfb.sources import (
    PROVIDER_PREFERENCE,
    PROVIDERS,
    RawGameLines,
    market_home_margin,
    market_line_for,
    normalize_provider,
    week_lines,
)
from cfb.storage import MemorySnapshotStore
from test_replay import PRESEASON_AT, cfbd_game, put_games, put_sagarin

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURE = FIXTURES / "cfbd_lines_2026_week01.json"

SEASON = 2026
LINES_PULLED_AT = datetime(2026, 8, 28, 22, 34, 43, tzinfo=UTC)

#: Real games from the capture, named so the assertions cite their source.
IOWA_STATE = 401856779  # DraftKings only, home favoured, spread -29.5
RUTGERS = 401858423  # both books, and they disagree: DK -29.5, Bovada -29
YOUNGSTOWN = 401867894  # spelled "Draft Kings"
PORTLAND_STATE = 401868154  # away favoured, spread +24.5


@pytest.fixture(scope="module")
def capture() -> list[dict]:
    """The raw response. Read as bytes -- `json.loads` detects UTF-8, and the
    capture holds accented names that Windows' default text encoding mangles.
    """
    return json.loads(CAPTURE.read_bytes())


@pytest.fixture(scope="module")
def records(capture) -> dict[int, RawGameLines]:
    return {row["id"]: RawGameLines.model_validate(row) for row in capture}


def put_lines(store, *, week: str, fetched_at: datetime, payload: list[dict]) -> str:
    """Store one `/lines` capture and its manifest."""
    data = json.dumps(payload).encode("utf-8")
    key = f"raw/cfbd/season={SEASON}/week={week}/lines/{fetched_at:%Y-%m-%dT%H%M%SZ}.json"
    store.put_bytes(key, data, "application/json")
    store.put_json(
        key.removesuffix(".json") + ".meta.json",
        Manifest(
            schema_version=1,
            source="cfbd",
            resource="lines",
            source_url="https://api.collegefootballdata.com/lines",
            http_status=200,
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
            encoding=None,
            fetched_at=fetched_at,
            season=SEASON,
            week=week,
            week_resolution="calendar",
            snapshot_key=key,
        ).model_dump(mode="json", exclude={"unmapped"}),
    )
    return key


# --- what the capture actually contains ---------------------------------------


class TestTheCaptureItself:
    """Facts this file's other assertions rest on. If the fixture is ever
    replaced, these fail first and say what changed.
    """

    def test_it_is_a_full_week_of_games(self, capture):
        assert len(capture) == 143
        assert {row["week"] for row in capture} == {1}
        assert {row["seasonType"] for row in capture} == {"regular"}

    def test_there_is_no_closing_line_field(self, capture):
        """The finding that renamed the field in three sections of the spec."""
        fields = {key for row in capture for line in row["lines"] for key in line}
        assert "spread" in fields
        assert "spreadOpen" in fields
        assert not [f for f in fields if "clos" in f.lower()]

    def test_one_book_is_spelled_two_ways(self, capture):
        spellings = {line["provider"] for row in capture for line in row["lines"]}
        assert {"DraftKings", "Draft Kings"} <= spellings

    def test_the_two_books_disagree_often_enough_for_selection_to_matter(self, capture):
        """21 of 143. Preference order changes the stored number, so it is a
        decision rather than a tidy-up.
        """
        disagreeing = [
            row
            for row in capture
            if len({line["spread"] for line in row["lines"]}) > 1
        ]
        assert len(disagreeing) == 21

    def test_no_game_lists_the_same_book_twice(self, capture):
        """Which is why selection can pick a provider without also reconciling it
        against itself.
        """
        for row in capture:
            resolved = [normalize_provider(line["provider"]) for line in row["lines"]]
            assert len(resolved) == len(set(resolved))


# --- providers ----------------------------------------------------------------


class TestProviderNormalization:
    """Exact lookup or it raises — the same rule the crosswalk follows.

    A whitespace-collapsing normalizer would merge these two spellings and would
    also merge two genuinely different books that happened to differ by a space.
    An alias table cannot.
    """

    @pytest.mark.parametrize(
        ("spelling", "resolved"),
        [("DraftKings", "DraftKings"), ("Draft Kings", "DraftKings"), ("Bovada", "Bovada")],
    )
    def test_the_spellings_in_the_capture_resolve(self, spelling, resolved):
        assert normalize_provider(spelling) == resolved

    def test_an_unrecognised_provider_raises_rather_than_being_skipped(self):
        """Skipping would drop a line silently, and a book this project has never
        seen is exactly when someone should look before its number is published.
        """
        with pytest.raises(UnknownProviderError):
            normalize_provider("ESPN Bet")

    def test_the_error_is_the_fix(self):
        with pytest.raises(UnknownProviderError) as excinfo:
            normalize_provider("ESPN Bet")
        message = str(excinfo.value)
        assert "ESPN Bet" in message
        assert "PROVIDERS" in message

    def test_every_provider_in_the_capture_is_known(self, capture):
        """The alias table against the real data rather than against memory."""
        for row in capture:
            for line in row["lines"]:
                assert normalize_provider(line["provider"]) in PROVIDER_PREFERENCE

    def test_every_alias_resolves_to_something_preferred(self):
        """A table entry that resolves to a name selection never considers is a
        line that parses and is then silently unusable.
        """
        assert set(PROVIDERS.values()) == set(PROVIDER_PREFERENCE)


class TestSelection:
    def test_it_takes_the_preferred_book_when_two_disagree(self, records):
        """Rutgers: DraftKings -29.5, Bovada -29. Preference decides, and it has
        to be deterministic or the same capture replays to two different numbers.
        """
        line, provider = market_line_for(records[RUTGERS])
        assert provider == "DraftKings"
        assert line == -29.5

    def test_it_resolves_the_alias_before_preferring(self, records):
        """Youngstown State's only line is spelled `Draft Kings`. Selecting before
        normalizing would find no preferred provider and drop the game.
        """
        line, provider = market_line_for(records[YOUNGSTOWN])
        assert provider == "DraftKings"
        assert line == -30.5

    def test_a_single_book_is_used_whatever_it_is(self, records):
        line, provider = market_line_for(records[IOWA_STATE])
        assert (line, provider) == (-29.5, "DraftKings")

    def test_the_capture_yields_a_line_for_every_game(self, records):
        """143 for 143 — so in this week the null path is the join, not the
        response. `TestMissingLines` covers the join.
        """
        assert all(market_line_for(record) is not None for record in records.values())

    def test_a_record_with_no_lines_is_none(self, records):
        empty = records[IOWA_STATE].model_copy(update={"lines": []})
        assert market_line_for(empty) is None

    def test_a_null_spread_is_skipped_rather_than_selected(self, records):
        """A provider can list a game without pricing it. That entry is not a
        line, and preferring it would store `None` while a usable Bovada number
        sat next to it.
        """
        record = records[RUTGERS]
        blanked = record.model_copy(
            update={
                "lines": [
                    line.model_copy(update={"spread": None})
                    if line.provider == "DraftKings"
                    else line
                    for line in record.lines
                ]
            }
        )
        line, provider = market_line_for(blanked)
        assert provider == "Bovada"
        assert line == -29


# --- the sign -----------------------------------------------------------------


class TestTheSign:
    """**The tests that fail if the flip is dropped.**

    `spread` is negative when the home team is favoured; `predicted_margin` is
    positive when the home team is favoured. Comparing them without converting
    produces an ATS record that is plausible, complete, and exactly backwards.
    """

    def test_a_home_favourite_converts_to_a_positive_home_margin(self, records):
        """Iowa State −29.5 means Iowa State by 29.5, which is +29.5 our way."""
        line, _ = market_line_for(records[IOWA_STATE])
        assert line == -29.5
        assert market_home_margin(line) == 29.5

    def test_an_away_favourite_converts_to_a_negative_home_margin(self, records):
        """Portland State hosting UC Davis: spread +24.5, `UC Davis -24.5`.

        The other direction, and the one a sign error cannot survive: get the
        flip wrong and this reads as the home team favoured by 24.5.
        """
        line, _ = market_line_for(records[PORTLAND_STATE])
        assert line == 24.5
        assert market_home_margin(line) == -24.5

    def test_the_conversion_is_its_own_inverse(self):
        for value in (-29.5, 24.5, 0.0, 3.0):
            assert market_home_margin(market_home_margin(value)) == value

    def test_the_sign_matches_the_vendors_own_words_for_every_entry(self, capture):
        """The property, over all 194 entries rather than the two named above.

        `formattedSpread` names the favourite. So a positive `market_home_margin`
        must coincide with the home team being named, and a negative one with the
        away team. This is the assertion that would catch a flip applied in the
        wrong place as well as one not applied at all.
        """
        checked = 0
        for row in capture:
            for line in row["lines"]:
                spread = line["spread"]
                if spread is None:
                    continue
                margin = market_home_margin(spread)
                names_home = line["formattedSpread"].startswith(row["homeTeam"])
                assert (margin > 0) == names_home, (
                    f"game {row['id']}: spread={spread} formatted="
                    f"{line['formattedSpread']!r} home={row['homeTeam']!r}"
                )
                checked += 1
        assert checked == 194

    def test_zero_is_not_special_cased(self):
        """A pick'em is a real line and must survive the conversion as one.

        It matters because `0.0` is also what a null would become if anything
        downstream coerced -- so the two have to stay distinguishable.
        """
        assert market_home_margin(0.0) == 0.0
        assert market_home_margin(0.0) is not None


# --- reading them out of the store --------------------------------------------


class TestWeekLines:
    @pytest.fixture
    def store(self, capture):
        store = MemorySnapshotStore()
        put_lines(store, week="01", fetched_at=LINES_PULLED_AT, payload=capture)
        return store

    def test_it_reads_a_week_keyed_by_game_id(self, store):
        found, keys = week_lines(store, SEASON, lambda record: record.week == 1)
        assert len(found) == 143
        assert found[IOWA_STATE].home_team == "Iowa State"
        assert len(keys) == 1

    def test_the_newest_capture_of_a_week_wins(self, store, capture):
        """Lines move. A re-pull is the current market, not extra evidence, and
        merging both would mix two moments into one number.
        """
        moved = [dict(row) for row in capture]
        moved[0] = dict(moved[0], lines=[dict(moved[0]["lines"][0], spread=-14.0)])
        put_lines(
            store, week="01",
            fetched_at=datetime(2026, 8, 29, 12, tzinfo=UTC), payload=moved,
        )

        found, _ = week_lines(store, SEASON, lambda record: record.week == 1)
        assert market_line_for(found[IOWA_STATE])[0] == -14.0

    def test_an_empty_prefix_is_an_empty_mapping_not_an_error(self):
        found, keys = week_lines(MemorySnapshotStore(), SEASON, lambda record: True)
        assert found == {}
        assert keys == []


# --- into the prediction rows -------------------------------------------------


#: Real games from the capture, rebuilt as `/games` rows so the ids match. The
#: kickoffs are the capture's own `startDate` values.
SLATE = [
    cfbd_game(
        game_id=IOWA_STATE, week=1, kickoff=datetime(2026, 9, 5, 17, 0, tzinfo=UTC),
        home="Iowa State", away="Southeast Missouri State",
        home_points=None, away_points=None,
    ),
    cfbd_game(
        game_id=RUTGERS, week=1, kickoff=datetime(2026, 9, 5, 18, 0, tzinfo=UTC),
        home="Rutgers", away="Massachusetts", home_points=None, away_points=None,
    ),
    cfbd_game(
        game_id=PORTLAND_STATE, week=1, kickoff=datetime(2026, 9, 5, 19, 0, tzinfo=UTC),
        home="Portland State", away="UC Davis", home_points=None, away_points=None,
    ),
    #: Not in the `/lines` response at all. This is where a null comes from -- the
    #: join, not a null field inside a line entry.
    cfbd_game(
        game_id=999_999_999, week=1, kickoff=datetime(2026, 9, 5, 20, 0, tzinfo=UTC),
        home="Ohio State", away="Michigan", home_points=None, away_points=None,
    ),
]

GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def crosswalk():
    from cfb.crosswalk import load

    return load(SEASON)


@pytest.fixture
def predicted(capture, crosswalk):
    """A week 1 prediction run over the real lines capture."""
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(
        store, week="01",
        fetched_at=datetime(2026, 9, 1, 12, tzinfo=UTC), games=SLATE,
    )
    put_lines(store, week="01", fetched_at=LINES_PULLED_AT, payload=capture)
    write_state(
        store,
        seed_state(
            store=store, season=SEASON,
            now=datetime(2026, 8, 28, 18, tzinfo=UTC), crosswalk=crosswalk,
        ),
    )
    log = predict_week(
        store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
    )
    return log, {game.cfbd_game_id: game for game in log.games}


class TestTheJoin:
    """`market_line` on the prediction rows, joined on `cfbd_game_id` (§5.1)."""

    def test_the_vendor_value_is_stored_verbatim(self, predicted):
        """Not converted on the way in. The document records what CFBD said, and
        `market_home_margin` is where the conversion happens instead.
        """
        _, rows = predicted
        assert rows[IOWA_STATE].market_line == -29.5
        assert rows[PORTLAND_STATE].market_line == 24.5

    def test_the_stored_sign_is_opposite_to_the_predicted_margin(self, predicted):
        """The one place in the document where two conventions coexist.

        Iowa State are heavy home favourites: the model likes them by a lot
        (positive) and the market prices them at −29.5 (negative). Same opinion,
        opposite signs, which is exactly why the conversion has a name.
        """
        _, rows = predicted
        row = rows[IOWA_STATE]
        assert row.predicted_margin > 0
        assert row.market_line < 0
        assert market_home_margin(row.market_line) > 0

    def test_the_resolved_book_travels_with_the_line(self, predicted):
        """§6.3's `line_source` stops being a guess."""
        _, rows = predicted
        assert rows[IOWA_STATE].market_line_source == "DraftKings"
        assert rows[RUTGERS].market_line_source == "DraftKings"

    def test_preference_decides_when_the_books_disagree(self, predicted):
        """Rutgers is one of the 21. Bovada says −29, DraftKings −29.5."""
        _, rows = predicted
        assert rows[RUTGERS].market_line == -29.5

    def test_a_game_with_no_line_is_null_in_both_fields(self, predicted):
        """The real null path: on the slate, absent from the `/lines` response."""
        _, rows = predicted
        assert rows[999_999_999].market_line is None
        assert rows[999_999_999].market_line_source is None

    def test_a_missing_line_is_never_a_zero(self, predicted):
        """Zero is a pick'em -- a real line saying the market has no favourite.

        If a missing line became a zero, every unpriced game would enter §5.3's
        against-the-spread record as a push against a spread nobody quoted, and
        the resulting number would look entirely reasonable.
        """
        _, rows = predicted
        missing = rows[999_999_999]
        assert missing.market_line is None
        # `None` and `0.0` are both falsey, so anything that tests a line with a
        # bare truthiness check treats them the same. Nothing may.
        assert not (missing.market_line == 0.0)  # noqa: SIM201 - == not `is`, on purpose

    def test_the_model_block_names_the_capture(self, predicted):
        """Same rule as the HFA and the Sagarin page: a number from a source, and
        the document says which one.
        """
        log, _ = predicted
        assert log.model.market_lines_from is not None
        assert log.model.market_lines_from.startswith(
            f"raw/cfbd/season={SEASON}/week=01/lines/"
        )

    def test_every_priced_game_agrees_with_the_capture(self, predicted, records):
        """The join, checked against the source rather than against three names."""
        _, rows = predicted
        for game_id, row in rows.items():
            if game_id not in records:
                assert row.market_line is None
                continue
            expected, book = market_line_for(records[game_id])
            assert row.market_line == expected
            assert row.market_line_source == book
