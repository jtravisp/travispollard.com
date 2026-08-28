"""Validated models for parsed source data (SPEC-phase0 section 4.5).

Validators raise. They never coerce, default, or return ``None``. The models are
strict and frozen: a parsed row is evidence about what a page said at a moment in
time, and nothing downstream has any business editing it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamRating(BaseModel):
    """One team row from section 1 of the Sagarin ratings page.

    ``rank`` is the identity, not ``rating``: Sagarin prints two decimals over more
    internal precision, so distinct teams display identical ratings (Virginia Tech
    and Northwestern both read 77.49 on the 2026 preseason page). Never sort,
    dedupe, or join on the rating value.

    ``conference`` is carried per row rather than per team because it is
    time-varying -- it belongs to this snapshot, not to the team.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

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
