"""Tests for `src.pipeline.runner` - end-to-end classification orchestration."""
from __future__ import annotations

from src.db.models import Incident, Severity
from src.ingestion.log_reader import LogEvent
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import ClassificationResult, MockClassifier
from src.pipeline.runner import IncidentPipeline, PipelineResult


def test_process_event_returns_pipeline_result_with_report(pipeline, sample_event):
    result = pipeline.process_event(sample_event)

    assert isinstance(result, PipelineResult)
    assert result.report.raw_message == sample_event.message
    assert result.report.severity in ("INFO", "WARNING", "CRITICAL", "INCIDENT")
    assert result.report.summary
    assert result.incident is None


def test_process_event_persists_incident_to_db_when_session_provided(pipeline, sample_event, db_session):
    result = pipeline.process_event(sample_event, db=db_session)
    db_session.commit()

    assert result.incident is not None
    persisted = db_session.get(Incident, result.incident.id)
    assert persisted is not None
    assert persisted.raw_message == sample_event.message


def test_run_batch_processes_all_events_and_returns_a_result_per_event(pipeline, sample_event, info_event, db_session):
    events = [sample_event, info_event]

    results = pipeline.run_batch(events, db=db_session)

    assert len(results) == 2
    incidents = db_session.query(Incident).all()
    assert len(incidents) == 2


def test_run_from_directory_processes_log_files(tmp_path, db_session):
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2024-01-15T10:23:45Z | host=web-01 | service=nginx | level=ERROR | msg=Connection refused\n"
        "2024-01-15T10:23:50Z | host=api-01 | service=fastapi-app | level=WARNING | msg=High memory usage\n",
        encoding="utf-8",
    )

    pipeline = IncidentPipeline(classifier=MockClassifier(seed=0), alert_dispatcher=AlertDispatcher())
    results = pipeline.run_from_directory(str(tmp_path), db=db_session)

    assert len(results) == 2


def test_pipeline_dispatches_alert_for_critical_severity(sample_event):
    """Inject a classifier that always returns CRITICAL to test alert dispatch."""

    class _AlwaysCritical:
        def classify(self, event: LogEvent) -> ClassificationResult:
            return ClassificationResult(
                severity="CRITICAL",
                classification="Forced Critical",
                confidence=0.99,
                recommended_action="Page on-call",
                summary="Test critical event",
            )

    dispatcher = AlertDispatcher()
    pipeline = IncidentPipeline(classifier=_AlwaysCritical(), alert_dispatcher=dispatcher)

    result = pipeline.process_event(sample_event)

    assert result.alert_sent is True
    assert len(dispatcher.sent_alerts) == 1
    assert dispatcher.sent_alerts[0].severity == "CRITICAL"


def test_pipeline_does_not_dispatch_alert_below_threshold(info_event):
    """Inject a classifier that always returns INFO; no alert should be dispatched."""

    class _AlwaysInfo:
        def classify(self, event: LogEvent) -> ClassificationResult:
            return ClassificationResult(
                severity="INFO",
                classification="Routine Activity",
                confidence=0.99,
                recommended_action="No action required",
                summary="Everything is fine",
            )

    dispatcher = AlertDispatcher()
    pipeline = IncidentPipeline(classifier=_AlwaysInfo(), alert_dispatcher=dispatcher)

    result = pipeline.process_event(info_event)

    assert result.alert_sent is False
    assert len(dispatcher.sent_alerts) == 0
