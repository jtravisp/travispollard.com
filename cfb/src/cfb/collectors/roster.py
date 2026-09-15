"""Thursday-knowable roster capture (SPEC-phase3 section 3.2).

Elo's largest single blind spot is that it does not know who is playing. A
quarterback change is worth roughly 5-7 points and the ratings cannot see it.

**The constraint that shapes everything here.** This project's credibility rests
on forecasts written before kickoff. Historical data records *who did start*; it
does not record *who was expected to start on Thursday*. Training on actual
starters and deploying on Thursday is retrospective leakage wearing a feature's
clothes, and it would produce a backtest nobody could reproduce live.

So the feature is defined to make its historical and live versions the same
function of the same information set: **who started the previous game**. That was
knowable on a Thursday in 2017 and it is knowable on a Thursday now, and it
backfills from ``/games/players`` across the whole window with no leakage.

**This module is a clock, and that is the reason it exists before anything
consumes it.** What is *not* backfillable is the news layer -- who was ruled out
on Thursday. Every week that passes uncaptured is a week no model will ever cover,
and unlike everything else in Phase 3 that cost cannot be recovered later.

**The partition is the week being forecast; the evidence is the week before it.**
A Thursday run during week 3 writes ``raw/roster/season=2026/week=03/`` from week
2's box scores, because the document answers "who is expected to start in week 3".
Filing it under the week the data came from would make every consumer subtract one
and eventually one of them would forget.

**Derived, not received**, which is why it is its own source rather than a cfbd
resource. ``raw/cfbd/`` holds the vendor's bytes exactly as they arrived; this
holds one canonical id and one expectation per team, with the basis that formed
it. The vendor's own response is *also* snapshotted, under ``raw/cfbd/`` where it
belongs, so the immutability rule is satisfied by the bytes rather than by this.
"""

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cfb.collectors.cfbd import BASE_URL, CfbdClient
from cfb.crosswalk import Crosswalk
from cfb.errors import RosterBasisError
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest, validating
from cfb.storage import SnapshotStore

__all__ = [
    "BACKFILLABLE_BASES",
    "ROSTER_SCHEMA_VERSION",
    "ExpectedQb",
    "RosterSnapshot",
    "TeamRoster",
    "fetch_roster",
    "qb_expectations",
]

#: SPEC-phase3 3.2's schema for the derived document. Independent of every other
#: version in this project: it describes a `raw/roster/` payload and nothing else.
ROSTER_SCHEMA_VERSION = 1

#: The bases a model trained across eras may use.
#:
#: **Only one, and the narrowness is the point.** `previous-game-starter` comes
#: out of a completed box score, so it exists for every season `/games/players`
#: covers. The other two are captured prospectively and exist only from the day
#: this collector started running -- a model that uses them declares that it does
#: not cover the backfill (SPEC-phase3 3.2).
BACKFILLABLE_BASES = frozenset({"previous-game-starter"})

_BASES = ("previous-game-starter", "depth-chart", "reported-out")

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

#: The category `/games/players` files quarterbacks under.
_PASSING = "passing"

#: The stat this reads to decide who started.
#:
#: **Attempts rather than yards or a `starter` flag.** CFBD's box score carries no
#: starter field, and yards rank the effective quarterback rather than the one who
#: took the first snap. Attempts is the closest available proxy for "was the
#: quarterback that day" and it is the same proxy in 2017 as in 2026, which is the
#: property section 3.2 is built on.
_ATTEMPTS = "ATT"


class ExpectedQb(BaseModel):
    """Who a team is expected to start, and how that expectation was formed."""

    model_config = _STRICT

    player_id: int
    name: str = Field(min_length=1)
    #: **The load-bearing field** (SPEC-phase3 3.2). A consumer filters on it, and
    #: the values are not interchangeable -- see ``BACKFILLABLE_BASES``.
    basis: Literal["previous-game-starter", "depth-chart", "reported-out"]
    #: Completed games this player has started, by this collector's own reading of
    #: the box scores it has seen. Not a season total from the vendor.
    games_started: int = Field(ge=1)
    #: This player's share of the team's pass attempts in the source game. A
    #: timeshare or an injury mid-game shows up here as a number well under 1.0,
    #: which is a fact a consumer should be able to weigh rather than one this
    #: collector should decide on its behalf.
    usage_share: float = Field(ge=0.0, le=1.0)
    #: The game the expectation was read from, so it can be checked by hand.
    last_game_id: int


class TeamRoster(BaseModel):
    model_config = _STRICT

    #: A canonical id, via the crosswalk -- never a vendor spelling.
    team: str = Field(min_length=1)
    expected_qb: ExpectedQb | None
    #: ``None`` when there is no previous game to compare against, which is not
    #: the same fact as ``False``. A team's first captured week cannot know
    #: whether anything changed, and a bare ``False`` there would read as
    #: "confirmed unchanged" to every consumer downstream.
    qb_changed_from_last_game: bool | None = None


class RosterSnapshot(BaseModel):
    """The derived document written to ``raw/roster/``."""

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    source: Literal["cfbd"]
    resource: Literal["roster-status"]
    fetched_at: datetime
    season: int = Field(ge=1869)
    #: The week these expectations are *for*.
    week: str = Field(min_length=1)
    week_resolution: Literal["calendar", "unknown"]
    #: The week the box scores came from -- always the one before ``week``.
    #: Recorded because "previous" is a relationship, and a document that states
    #: only one end of it cannot be checked.
    source_week: str = Field(min_length=1)
    #: The `raw/cfbd/` key holding the vendor bytes this was derived from, so the
    #: derivation can be replayed without a network call.
    derived_from: str = Field(min_length=1)
    teams: list[TeamRoster]


def qb_expectations(
    rows: list[dict],
    resolver: Crosswalk,
    *,
    source_game_ids: dict[str, int] | None = None,
) -> list[TeamRoster]:
    """One expected starter per team, from a ``/games/players`` response.

    **Every team in the response, or the team is absent -- never a guess.** A team
    whose passing category holds no attempts gets ``expected_qb: None`` rather
    than a lowest-ranked player standing in for one. Section 3.2's whole argument
    is that the expectation has to be the same function in 2017 as today, and a
    fallback would be a different function on exactly the rows where the data is
    thin.

    Unmapped team names raise through the crosswalk, as everywhere else.
    """
    attempts: dict[str, dict[int, dict]] = defaultdict(dict)
    game_of: dict[str, int] = {}

    for game in rows:
        game_id = game.get("id")
        for team_block in game.get("teams", []):
            vendor = team_block.get("team")
            if not vendor:
                continue
            team = resolver.from_cfbd(vendor)
            game_of[team] = game_id
            for category in team_block.get("categories", []):
                if category.get("name") != _PASSING:
                    continue
                for stat in category.get("types", []):
                    if stat.get("name") != _ATTEMPTS:
                        continue
                    for athlete in stat.get("athletes", []):
                        taken = _as_int(athlete.get("stat"))
                        if taken is None:
                            continue
                        player = int(athlete["id"])
                        current = attempts[team].setdefault(
                            player, {"name": athlete.get("name", ""), "att": 0}
                        )
                        current["att"] += taken

    rosters: list[TeamRoster] = []
    for team in sorted(set(game_of) | set(attempts)):
        throwers = attempts.get(team, {})
        total = sum(entry["att"] for entry in throwers.values())
        if not throwers or total == 0:
            rosters.append(TeamRoster(team=team, expected_qb=None))
            continue

        player_id, entry = max(
            throwers.items(), key=lambda pair: (pair[1]["att"], -pair[0])
        )
        with validating(f"expected qb for {team}"):
            rosters.append(
                TeamRoster(
                    team=team,
                    expected_qb=ExpectedQb(
                        player_id=player_id,
                        name=entry["name"] or f"player {player_id}",
                        basis="previous-game-starter",
                        games_started=1,
                        usage_share=round(entry["att"] / total, 4),
                        last_game_id=(source_game_ids or game_of)[team],
                    ),
                )
            )
    return rosters


def check_basis(rosters: list[TeamRoster]) -> None:
    """Every stated basis is one this project recognises (SPEC-phase3 3.2).

    The model's ``Literal`` already refuses an unknown string, so this is not
    about parsing -- it is about the derivation. This collector can only ever
    produce ``previous-game-starter``, because a box score is the only evidence it
    reads; a row claiming ``depth-chart`` here would mean the writer and the
    evidence have come apart, and the value a consumer trusts most is exactly the
    one it would be most wrong about.
    """
    for roster in rosters:
        qb = roster.expected_qb
        if qb is None:
            continue
        if qb.basis not in BACKFILLABLE_BASES:
            raise RosterBasisError(
                f"{roster.team} was given basis {qb.basis!r}, which this collector "
                f"cannot form: it reads completed box scores and so produces only "
                f"{sorted(BACKFILLABLE_BASES)}. A prospective basis has to come from "
                f"the collector that captured it (SPEC-phase3 3.2)."
            )


def fetch_roster(
    *,
    store: SnapshotStore,
    client: CfbdClient,
    resolver: Crosswalk,
    season: int,
    week: str,
    source_week: str,
    now: datetime,
) -> RosterSnapshot:
    """Capture the previous week's starters as this week's expectation.

    **Two objects land, in this order.** The vendor's bytes go to ``raw/cfbd/``
    unmodified first, because the immutability rule is about what arrived; the
    derived document follows at ``raw/roster/``. A failure between them leaves the
    evidence stored and the derivation absent, which is replayable -- the reverse
    would not be.
    """
    data = client.get("/games/players", year=season, week=int(source_week))

    evidence = snapshot_key(
        source="cfbd",
        season=season,
        week=source_week,
        fetched_at=now,
        resource="players",
    )
    store.put_bytes(evidence, data, "application/json")
    with validating(f"manifest for {evidence}"):
        store.put_json(
            manifest_key(evidence),
            Manifest(
                schema_version=1,
                source="cfbd",
                resource="players",
                source_url=f"{BASE_URL}/games/players",
                http_status=200,
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
                encoding=None,
                fetched_at=now,
                season=season,
                week=source_week,
                week_resolution="calendar",
                snapshot_key=evidence,
            ).model_dump(mode="json", exclude={"unmapped"}),
        )

    rows = json.loads(data)
    if not isinstance(rows, list):
        raise RosterBasisError(
            f"{evidence} holds {type(rows).__name__}, expected the list "
            f"/games/players returns; an error body stored with a 200 looks like this"
        )

    rosters = qb_expectations(rows, resolver)
    check_basis(rosters)

    with validating(f"roster snapshot for season {season} week {week}"):
        snapshot = RosterSnapshot(
            schema_version=ROSTER_SCHEMA_VERSION,
            source="cfbd",
            resource="roster-status",
            fetched_at=now,
            season=season,
            week=week,
            week_resolution="calendar",
            source_week=source_week,
            derived_from=evidence,
            teams=rosters,
        )

    key = snapshot_key(source="roster", season=season, week=week, fetched_at=now)
    body = json.dumps(snapshot.model_dump(mode="json"), indent=2).encode("utf-8")
    store.put_bytes(key, body, "application/json")

    with validating(f"manifest for {key}"):
        store.put_json(
            manifest_key(key),
            Manifest(
                schema_version=1,
                source="roster",
                resource="roster-status",
                source_url=f"{BASE_URL}/games/players",
                http_status=200,
                sha256=hashlib.sha256(body).hexdigest(),
                bytes=len(body),
                # The derived document is JSON this project wrote, so there is no
                # encoding to sniff -- the same reason `fetch_cfbd` stores null.
                encoding=None,
                fetched_at=now,
                season=season,
                week=week,
                week_resolution="calendar",
                snapshot_key=key,
                parse_ok=True,
                team_count=len(rosters),
            ).model_dump(mode="json", exclude={"unmapped"}),
        )

    return snapshot


def _as_int(value) -> int | None:
    """CFBD sends stat values as strings, and occasionally as something else."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
