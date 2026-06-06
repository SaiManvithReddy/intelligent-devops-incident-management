"""Builds structured `IncidentReport` objects from classified log events."""
from __future__ import annotations

from src.ingestion.log_reader import LogEvent
from src.pipeline.classifier import ClassificationResult
from src.pipeline.schemas import IncidentReport


def build_incident_report(event: LogEvent, result: ClassificationResult) -> IncidentReport:
    """Combine a raw `LogEvent` and its `ClassificationResult` into a report."""
    return IncidentReport(
        source=event.source,
        raw_message=event.message,
        host=event.host,
        service=event.service,
        detected_at=event.timestamp,
        severity=result.severity,
        classification=result.classification,
        confidence=result.confidence,
        recommended_action=result.recommended_action,
        summary=result.summary,
    )
