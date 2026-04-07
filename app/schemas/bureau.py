from datetime import datetime, timezone
from uuid import UUID
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict
from app.models.enums import BureauRiskBand, ScoreTrigger

class FactorDetail(BaseModel):
    """Score and inputs for one scoring factor."""
    score: int
    max: int
    weight_pct: int
    inputs: dict[str, Any]

class BureauSnapshotResponse(BaseModel):
    """A single score snapshot in history."""
    score: int
    risk_band: BureauRiskBand
    trigger_event: ScoreTrigger
    computed_at: datetime
    delta: int | None

class BureauScoreResponse(BaseModel):
    """Full bureau score response with factor breakdown."""
    user_id: UUID
    score: int
    risk_band: BureauRiskBand
    score_interpretation: str
    computed_at: datetime
    trigger_event: ScoreTrigger
    factor_breakdown: dict[str, FactorDetail]
    history: list[BureauSnapshotResponse] | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }
    )

class BureauHistoryResponse(BaseModel):
    """Score history with trend analysis."""
    user_id: UUID
    snapshots: list[BureauSnapshotResponse]
    count: int
    oldest_snapshot_at: datetime | None
    latest_score: int | None
    latest_band: BureauRiskBand | None
    score_trend: Literal["IMPROVING", "DECLINING", "STABLE"]

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }
    )
