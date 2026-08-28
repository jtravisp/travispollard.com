"""Validated models for parsed source data (SPEC-phase0 section 4.5).

Validators raise. They never coerce, default, or return ``None``. The models are
strict and frozen: a parsed row is evidence about what a page said at a moment in
time, and nothing downstream has any business editing it.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb.errors import DuplicateRankError, ParseError

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


class TeamRating(BaseModel):
    """One team row from section 1 of the Sagarin ratings page.

    ``rank`` is the identity, not ``rating``: Sagarin prints two decimals over more
    internal precision, so distinct teams display identical ratings (Virginia Tech
    and Northwestern both read 77.49 on the 2026 preseason page). Never sort,
    dedupe, or join on the rating value.

    ``conference`` is carried per row rather than per team because it is
    time-varying -- it belongs to this snapshot, not to the team.
    """

    model_config = _STRICT

    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    rating: float
    predictor: float
    golden_mean: float
    recent: float
    division: Literal["A", "AA"]
    conference: str = Field(min_length=1)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)


class GamePrediction(BaseModel):
    """One game from the Predictions_with_Totals_and_Moneylines section.

    The page frames every row as FAVORITE over UNDERDOG and marks the nominal home
    team with ``@``. This model reframes it as home/away, which is how a prediction
    is scored against a closing line, and signs ``predicted_margin`` from the home
    team's perspective: positive means the home team is favored.

    Two fields beyond the five SPEC-phase0 4.5 lists, both because the five cannot
    represent something the page says:

    * ``rank`` -- the page's own row number. Rank is the join key everywhere else in
      this project, and it is the only stable identity a prediction row has.
    * ``site`` -- the flag after the rank. It is not decoration: it moves the
      home/away split columns, so ``home`` on a neutral row does not mean what
      ``home`` means on an ordinary row. A ``classic`` gets a partial home edge
      (26.60/25.40 on the 2026 preseason page) and a neutral gets none
      (26.00/26.00), so this is three states, not a bool.
    """

    model_config = _STRICT

    rank: int = Field(ge=1)
    home: str = Field(min_length=1)
    away: str = Field(min_length=1)
    site: Literal["home", "neutral", "classic"]
    #: The PREDICTOR column -- the margin-oriented one, and per SPEC-phase0 4.4 the
    #: column to benchmark forecasts against. Positive means home is favored.
    predicted_margin: float
    total: float | None
    moneyline: int | None

    @model_validator(mode="after")
    def home_and_away_are_distinct(self) -> "GamePrediction":
        if self.home == self.away:
            raise ParseError(
                f"prediction {self.rank} has {self.home!r} playing itself; the @ marker "
                f"or a team name was misread"
            )
        return self


class SagarinSnapshot(BaseModel):
    """One fetch of the Sagarin page, parsed and checked as a whole.

    The parsers already raise on everything checked here. This is deliberate
    defence in depth (SPEC-phase0 4.7): failing at the page is earlier and names
    the line, but a future parser change that reintroduces a duplicate rank should
    not be able to reach the manifest.
    """

    model_config = _STRICT

    fetched_at: datetime
    #: ``None`` on a preseason page -- it carries no internal date stamp at all, so
    #: the freshness check has nothing to compare until the first in-season page.
    page_date_stamp: date | None
    page_state: Literal["preseason", "in-season"]
    #: Read from the page per rating column. Never defaulted, never constant.
    hfa: dict[str, float]
    teams: list[TeamRating]
    predictions: list[GamePrediction]

    @model_validator(mode="after")
    def hfa_is_present(self) -> "SagarinSnapshot":
        if not self.hfa:
            raise ParseError("hfa is empty; there is no default home-field advantage")
        return self

    @model_validator(mode="after")
    def ranks_are_unique(self) -> "SagarinSnapshot":
        for label, ranks in (
            ("team", [t.rank for t in self.teams]),
            ("prediction", [p.rank for p in self.predictions]),
        ):
            seen: set[int] = set()
            for rank in ranks:
                if rank in seen:
                    raise DuplicateRankError(
                        f"{label} rank {rank} appears twice in this snapshot. Rank is the "
                        f"join key; a duplicate makes it unusable."
                    )
                seen.add(rank)
        return self

    @model_validator(mode="after")
    def preseason_degeneracy_is_flagged(self) -> "SagarinSnapshot":
        """A preseason page must actually be degenerate.

        Before any games all four rating columns are identical and every record is
        0-0. That is a legal state, not an error -- but a page whose title line says
        STARTING while the columns disagree is contradicting itself, and guessing
        which half is right is exactly the coercion this project forbids.
        """
        if self.page_state != "preseason":
            return self

        for team in self.teams:
            if not (team.rating == team.predictor == team.golden_mean == team.recent):
                raise ParseError(
                    f"page_state is 'preseason' but rank {team.rank} ({team.name}) has "
                    f"rating columns that differ: {team.rating}, {team.predictor}, "
                    f"{team.golden_mean}, {team.recent}"
                )
            if (team.wins, team.losses) != (0, 0):
                raise ParseError(
                    f"page_state is 'preseason' but rank {team.rank} ({team.name}) has a "
                    f"{team.wins}-{team.losses} record"
                )
        return self
