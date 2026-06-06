"""Pydantic request/response models for the FastAPI layer."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IncidentOut(BaseModel):
    """Serialized representation of a persisted incident."""

    id: str
    source: str
    raw_message: str
    severity: str
    classification: str
    confidence: float
    recommended_action: str
    summary: str
    detected_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime
    is_resolved: bool
    resolution_seconds: float | None = None

    model_config = {"from_attributes": True}


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""

    total: int
    limit: int
    offset: int
    items: list[IncidentOut]


class SeverityBreakdown(BaseModel):
    severity: str
    count: int


class IncidentSummaryResponse(BaseModel):
    """Aggregate statistics used to power dashboard widgets."""

    total_incidents: int
    open_incidents: int
    resolved_incidents: int
    severity_breakdown: list[SeverityBreakdown]
    mttr_seconds: float | None = Field(
        default=None, description="Mean time to resolution across resolved incidents, in seconds"
    )
    mttr_human: str | None = Field(default=None, description="Human-readable MTTR, e.g. '14m 32s'")
    most_common_classification: str | None = None
    generated_at: datetime


class TriageRequest(BaseModel):
    """Manually trigger classification of an arbitrary log line."""

    raw_log_line: str | None = Field(
        default=None,
        description="A raw log line in 'TIMESTAMP | host=... | service=... | level=... | msg=...' format",
    )
    host: str | None = Field(default=None, description="Used when raw_log_line is not provided")
    service: str | None = Field(default=None, description="Used when raw_log_line is not provided")
    level: str | None = Field(default=None, description="Used when raw_log_line is not provided")
    message: str | None = Field(default=None, description="Used when raw_log_line is not provided")
    persist: bool = Field(default=True, description="Whether to store the resulting incident in the database")


class TriageResponse(BaseModel):
    """Result of a manual triage request."""

    severity: str
    classification: str
    confidence: float
    recommended_action: str
    summary: str
    alert_sent: bool
    incident: IncidentOut | None = None


class ResolveIncidentRequest(BaseModel):
    """Mark an incident as resolved (used for MTTR tracking)."""

    resolved_at: datetime | None = Field(default=None, description="Defaults to now if omitted")


class HealthResponse(BaseModel):
    status: str
    environment: str
    classifier: str
    database: str
    redis: str
