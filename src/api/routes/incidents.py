"""Incident query, summary, triage, and resolution endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_pipeline
from src.api.schemas import (
    IncidentListResponse,
    IncidentOut,
    IncidentSummaryResponse,
    ResolveIncidentRequest,
    SeverityBreakdown,
    TriageRequest,
    TriageResponse,
)
from src.db.models import Incident, Severity
from src.ingestion.log_reader import LogEvent, parse_log_line
from src.pipeline.runner import IncidentPipeline

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=IncidentListResponse, summary="Query incidents")
def list_incidents(
    severity: str | None = Query(default=None, description="Filter by severity: INFO, WARNING, CRITICAL, INCIDENT"),
    service: str | None = Query(default=None, description="Filter by source/service substring"),
    resolved: bool | None = Query(default=None, description="Filter by resolution status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    """Return a paginated, filterable list of incidents, newest first."""
    stmt = select(Incident)

    if severity is not None:
        normalized = severity.upper()
        if normalized not in Severity.__members__:
            raise HTTPException(status_code=400, detail=f"Invalid severity '{severity}'. Must be one of {list(Severity.__members__)}")
        stmt = stmt.where(Incident.severity == Severity(normalized))

    if service is not None:
        stmt = stmt.where(Incident.source.ilike(f"%{service}%"))

    if resolved is not None:
        stmt = stmt.where(Incident.resolved_at.is_not(None) if resolved else Incident.resolved_at.is_(None))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(Incident.detected_at.desc()).limit(limit).offset(offset)
    incidents = db.scalars(stmt).all()

    return IncidentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[IncidentOut.model_validate(incident) for incident in incidents],
    )


@router.get("/summary", response_model=IncidentSummaryResponse, summary="Aggregate incident statistics")
def get_summary(db: Session = Depends(get_db)) -> IncidentSummaryResponse:
    """Return aggregate stats (severity breakdown, MTTR, etc.) for dashboards."""
    total_incidents = db.scalar(select(func.count()).select_from(Incident)) or 0

    open_incidents = db.scalar(select(func.count()).where(Incident.resolved_at.is_(None))) or 0
    resolved_incidents = total_incidents - open_incidents

    breakdown_rows = db.execute(
        select(Incident.severity, func.count()).group_by(Incident.severity)
    ).all()
    counts_by_severity = {row[0].value if isinstance(row[0], Severity) else row[0]: row[1] for row in breakdown_rows}
    severity_breakdown = [
        SeverityBreakdown(severity=level.value, count=counts_by_severity.get(level.value, 0))
        for level in Severity.ordered()
    ]

    mttr_seconds = _compute_mttr_seconds(db)

    classification_row = db.execute(
        select(Incident.classification, func.count().label("cnt"))
        .group_by(Incident.classification)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    most_common_classification = classification_row[0] if classification_row else None

    return IncidentSummaryResponse(
        total_incidents=total_incidents,
        open_incidents=open_incidents,
        resolved_incidents=resolved_incidents,
        severity_breakdown=severity_breakdown,
        mttr_seconds=mttr_seconds,
        mttr_human=_humanize_seconds(mttr_seconds) if mttr_seconds is not None else None,
        most_common_classification=most_common_classification,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/{incident_id}", response_model=IncidentOut, summary="Get a single incident by ID")
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> IncidentOut:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    return IncidentOut.model_validate(incident)


@router.post("/{incident_id}/resolve", response_model=IncidentOut, summary="Mark an incident as resolved")
def resolve_incident(incident_id: str, payload: ResolveIncidentRequest, db: Session = Depends(get_db)) -> IncidentOut:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    incident.resolved_at = payload.resolved_at or datetime.now(timezone.utc)
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return IncidentOut.model_validate(incident)


@router.post("/triage", response_model=TriageResponse, summary="Manually trigger triage of a log event")
def trigger_triage(
    payload: TriageRequest,
    db: Session = Depends(get_db),
    pipeline: IncidentPipeline = Depends(get_pipeline),
) -> TriageResponse:
    """
    Run a single, ad-hoc log event through the AI classification pipeline.

    Accepts either a raw, pipe-delimited log line (`raw_log_line`) or
    individual fields (`host`/`service`/`level`/`message`). Useful for
    on-call engineers who want to immediately classify a suspicious log
    line they spotted manually, without waiting for the ingestion loop.
    """
    event = _build_event_from_request(payload)

    result = pipeline.process_event(event, db=db if payload.persist else None)
    if payload.persist:
        db.commit()

    return TriageResponse(
        severity=result.classification.severity,
        classification=result.classification.classification,
        confidence=result.classification.confidence,
        recommended_action=result.classification.recommended_action,
        summary=result.classification.summary,
        alert_sent=result.alert_sent,
        incident=IncidentOut.model_validate(result.incident) if result.incident is not None else None,
    )


def _build_event_from_request(payload: TriageRequest) -> LogEvent:
    if payload.raw_log_line:
        event = parse_log_line(payload.raw_log_line, source="manual-triage")
        if event is not None:
            event.source = "manual-triage"
            return event

    if not payload.message:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'raw_log_line' or at minimum a 'message' field to triage.",
        )

    return LogEvent(
        timestamp=datetime.now(timezone.utc),
        host=payload.host or "manual",
        service=payload.service or "manual",
        level=(payload.level or "INFO").upper(),
        message=payload.message,
        source="manual-triage",
    )


def _compute_mttr_seconds(db: Session) -> float | None:
    rows = db.scalars(
        select(Incident).where(Incident.resolved_at.is_not(None))
    ).all()
    if not rows:
        return None

    total = sum((row.resolved_at - row.detected_at).total_seconds() for row in rows)
    return total / len(rows)


def _humanize_seconds(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
