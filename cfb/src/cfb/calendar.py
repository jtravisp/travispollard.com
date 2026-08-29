"""Season and week resolution (SPEC-phase0 section 3).

CFBD's `/calendar?year=YYYY` is authoritative, fetched once per season and
committed to ``data/calendar/2026.json``. Every run resolves locally from that
file, so the whole season costs one API call.

Two functions here behave differently on failure, and the difference is the
point. ``load_calendar`` raises: a missing, malformed, empty or wrong-season file
is a fact about the file, and there is nothing to reason from. ``resolve`` does
not raise: given a calendar it can read but a date it cannot place, it returns
``how="unknown"`` and lets the caller write the snapshot somewhere honest. SPEC
3.3 is explicit that this is the one place the project prefers a messy artifact
to a clean failure -- a Sagarin week not captured is gone permanently, and a
calendar bug is not a reason to lose it.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cfb.errors import WeekResolutionError

__all__ = [
    "Calendar",
    "CalendarEntry",
    "WeekRef",
    "coming_week",
    "in_season",
    "last_completed_week",
    "load_calendar",
    "resolve",
]

#: How far before the first calendar entry ``in_season`` opens (SPEC 3.1).
#:
#: Arbitrary, and deliberately so: the CFBD calendar carries no preseason
#: boundary to read, so a number had to be chosen. It sits on this side because
#: the two errors are not symmetric. Opening too early costs one wasted fetch of
#: a page that has not changed, and SPEC 4.6's freshness check skips rather than
#: alerts when ``page_date_stamp`` is null, which is exactly the preseason case.
#: Opening too late loses a snapshot permanently.
PRESEASON_LEAD = timedelta(days=21)

_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "calendar"


class CalendarEntry(BaseModel):
    """One week as CFBD publishes it."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    season: int
    week: int = Field(ge=1)
    season_type: str = Field(min_length=1, alias="seasonType")
    first_game_start: datetime = Field(alias="firstGameStart")
    last_game_start: datetime = Field(alias="lastGameStart")

    @property
    def is_postseason(self) -> bool:
        return self.season_type.lower() == "postseason"


class Calendar(BaseModel):
    """A season's weeks, ordered by when they start."""

    model_config = ConfigDict(frozen=True)

    season: int
    entries: tuple[CalendarEntry, ...]

    @property
    def has_postseason(self) -> bool:
        """Whether the calendar describes the end of its own season.

        A calendar without this cannot distinguish "after the season" from
        "past what this file knows", and must not pretend otherwise.
        """
        return any(entry.is_postseason for entry in self.entries)

    @property
    def opens(self) -> datetime:
        return self.entries[0].first_game_start

    @property
    def closes(self) -> datetime:
        return self.entries[-1].last_game_start


class WeekRef(BaseModel):
    """What a moment resolved to, and how much to trust it."""

    model_config = ConfigDict(frozen=True)

    season: int
    week: str
    how: Literal["calendar", "unknown"]


def load_calendar(season: int, *, data_dir: Path | None = None) -> Calendar:
    """The committed calendar for ``season``.

    Raises ``WeekResolutionError`` on anything that leaves nothing to resolve
    against. Every one of these has been a real failure somewhere: an unfetched
    calendar on a fresh checkout, a truncated write, a CFBD error body saved with
    a 200, and last season's file copied forward under this season's name.
    """
    path = (data_dir or _DEFAULT_DATA_DIR) / f"{season}.json"
    if not path.is_file():
        raise WeekResolutionError(f"no calendar for season {season} at {path}")

    try:
        raw = json.loads(path.read_bytes())
    except json.JSONDecodeError as exc:
        raise WeekResolutionError(
            f"calendar for season {season} at {path} is not valid JSON"
        ) from exc

    if not isinstance(raw, list):
        raise WeekResolutionError(
            f"calendar for season {season} at {path} is {type(raw).__name__}, expected a list of "
            f"weeks; a CFBD error body saved with a 200 looks exactly like this"
        )
    if not raw:
        raise WeekResolutionError(
            f"calendar for season {season} at {path} is empty; a zero-week calendar is a failed "
            f"call that returned 200, not a season with no games"
        )

    try:
        entries = [CalendarEntry.model_validate(item) for item in raw]
    except Exception as exc:
        raise WeekResolutionError(
            f"calendar for season {season} at {path} does not have the CFBD /calendar shape: {exc}"
        ) from exc

    wrong = {entry.season for entry in entries} - {season}
    if wrong:
        raise WeekResolutionError(
            f"calendar at {path} is filed under season {season} but its weeks are for "
            f"{sorted(wrong)}; resolving against the wrong season misfiles every snapshot it "
            f"touches under a plausible-looking key"
        )

    return Calendar(
        season=season,
        entries=tuple(sorted(entries, key=lambda entry: entry.first_game_start)),
    )


def resolve(now: datetime, *, calendar: Calendar) -> WeekRef:
    """Which partition ``now`` belongs to. Never raises -- see the module docstring."""
    if now < calendar.opens:
        return WeekRef(season=calendar.season, week="preseason", how="calendar")

    # A week owns everything from its first game until the next entry opens. The
    # scheduled Sagarin fetch is on a Tuesday (SPEC 11), which is nobody's game
    # day, so every real run lands in one of these gaps.
    for entry, following in zip(calendar.entries, calendar.entries[1:], strict=False):
        if entry.first_game_start <= now < following.first_game_start:
            return WeekRef(season=calendar.season, week=_partition(entry), how="calendar")

    last = calendar.entries[-1]
    if now <= last.last_game_start:
        return WeekRef(season=calendar.season, week=_partition(last), how="calendar")

    if calendar.has_postseason:
        return WeekRef(season=calendar.season, week="offseason", how="calendar")

    # Past the last week of a calendar that never described its own ending. It is
    # not that the season is over; it is that this file cannot say. Answering
    # "offseason" would be a guess dressed as an answer, and a snapshot filed
    # under a confidently wrong partition is never re-partitioned (SPEC 3.3).
    return WeekRef(season=calendar.season, week="unknown", how="unknown")


def last_completed_week(now: datetime, *, calendar: Calendar) -> str | None:
    """The regular week that has finished as of ``now``, or ``None`` if none has.

    SPEC 5.2's "N is the week that just completed". It lives here rather than in
    the workflow because SPEC 11 has the workflow call the same command a human
    calls -- a ``--week`` expression in YAML would be calendar arithmetic in the
    one place nothing tests it.

    **``None`` is a normal answer, not a failure.** On the real calendar week 1
    runs 2026-08-29 to 2026-09-08, so no week has completed on any Sunday before
    September 13. A caller that treated that as an error would turn the season's
    first two Sundays red before the pipeline had done anything wrong, and an
    alert that cries wolf twice before it ever means something is an alert nobody
    reads in October.

    A week counts as complete once ``now`` is strictly past its end. At exactly
    ``last_game_start`` the last game has kicked off and has not finished.

    Postseason is excluded, so from December onward this keeps answering ``15``.
    That is the honest answer rather than a good one: nothing here knows how to
    express a bowl slate as a CFBD week number, and inventing one would file real
    games under a wrong partition. Re-pulling week 15 is redundant, not wrong --
    SPEC 5.4 already says every invocation fetches for real.
    """
    completed = [
        entry
        for entry in calendar.entries
        if not entry.is_postseason and entry.last_game_start < now
    ]
    if not completed:
        return None
    return _partition(max(completed, key=lambda entry: entry.last_game_start))


def coming_week(now: datetime, *, calendar: Calendar) -> str | None:
    """The regular week about to be played, or ``None`` if none is left.

    SPEC-phase1 9's default for ``cfb predict``: "the week that is *about to* be
    played", which is the mirror of ``last_completed_week`` and lives here for the
    same reason -- a ``--week`` expression in YAML would be calendar arithmetic in
    the one place nothing tests it.

    The first week whose first game has not kicked off yet, so a Thursday run
    picks that Saturday's slate rather than the one three days gone. At exactly
    ``first_game_start`` the week has begun and predicting it is too late, which
    is what SPEC-phase1 8 means by the Friday publish deadline being first
    kickoff.

    **``None`` is a normal answer**, not a failure: from the last regular week's
    first kickoff onward there is no next week to predict, and every December
    Thursday would otherwise be a red run. Postseason is excluded for the same
    reason ``last_completed_week`` excludes it -- nothing here knows how to express
    a bowl slate as a CFBD week number, and inventing one would file real
    predictions under a wrong partition.
    """
    upcoming = [
        entry
        for entry in calendar.entries
        if not entry.is_postseason and now < entry.first_game_start
    ]
    if not upcoming:
        return None
    return _partition(min(upcoming, key=lambda entry: entry.first_game_start))


def in_season(now: datetime, *, calendar: Calendar) -> bool:
    """Whether the freshness check of SPEC 4.6 should run at all.

    Sagarin does not update from roughly February through August, and alerting
    through the off-season is how alerting dies. Both ends come from the loaded
    calendar; nothing here is a hardcoded date.
    """
    return calendar.opens - PRESEASON_LEAD <= now <= calendar.closes


def _partition(entry: CalendarEntry) -> str:
    """The ``week=`` segment for one calendar entry (SPEC 3.2).

    Zero-padded, because the value is a literal S3 path segment: a stray ``"4"``
    opens a second partition for a week that already has one, and every later
    prefix query silently reads half the data.
    """
    return "postseason" if entry.is_postseason else f"{entry.week:02d}"
