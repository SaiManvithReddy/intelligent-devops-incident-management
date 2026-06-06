"""
End-to-end orchestration of the incident pipeline:

    log event -> AI classification -> structured report -> persistence -> alert

`IncidentPipeline.process_event` runs a single event through every stage and
is the unit the API's "manual triage" endpoint and the batch ingestion
scripts both build on. `run_batch` / `run_from_directory` / `run_from_queue`
provide convenient bulk entry points for demos and background workers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.models import Incident, Severity
from src.ingestion.log_reader import LogEvent, tail_log_directory
from src.ingestion.queue_consumer import RedisLogQueue
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import Classifier, ClassificationResult, get_classifier
from src.pipeline.reports import build_incident_report
from src.pipeline.schemas import IncidentReport

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Outcome of running a single event through the pipeline."""

    event: LogEvent
    classification: ClassificationResult
    report: IncidentReport
    incident: Incident | None = None
    alert_sent: bool = False


@dataclass
class IncidentPipeline:
    """Wires together classification, persistence, and alerting."""

    classifier: Classifier = field(default_factory=get_classifier)
    alert_dispatcher: AlertDispatcher = field(default_factory=AlertDispatcher)
    settings: Settings = field(default_factory=get_settings)

    def process_event(self, event: LogEvent, *, db: Session | None = None) -> PipelineResult:
        """Classify a single event, optionally persist it, and alert if needed."""
        classification = self.classifier.classify(event)
        report = build_incident_report(event, classification)

        incident: Incident | None = None
        if db is not None:
            incident = Incident(
                source=report.source,
                raw_message=report.raw_message,
                severity=Severity(report.severity),
                classification=report.classification,
                confidence=report.confidence,
                recommended_action=report.recommended_action,
                summary=report.summary,
                detected_at=report.detected_at,
            )
            db.add(incident)
            db.flush()

        alert_sent = self.alert_dispatcher.dispatch(report)

        return PipelineResult(event=event, classification=classification, report=report, incident=incident, alert_sent=alert_sent)

    def run_batch(self, events: list[LogEvent], *, db: Session | None = None) -> list[PipelineResult]:
        """Process a list of events sequentially, returning all results."""
        results = [self.process_event(event, db=db) for event in events]
        if db is not None:
            db.commit()
        return results

    def run_from_directory(self, directory: str, *, db: Session | None = None, limit: int | None = None) -> list[PipelineResult]:
        """Ingest events from `.log` files in `directory` and process them."""
        events = list(tail_log_directory(directory))
        if limit is not None:
            events = events[:limit]
        logger.info("Loaded %d log events from %s", len(events), directory)
        return self.run_batch(events, db=db)

    def run_from_queue(self, queue: RedisLogQueue, *, db: Session | None = None, max_items: int = 100) -> list[PipelineResult]:
        """Drain up to `max_items` events from a Redis queue and process them."""
        events = list(queue.drain(max_items=max_items))
        logger.info("Drained %d log events from Redis queue '%s'", len(events), queue.queue_name)
        return self.run_batch(events, db=db)
