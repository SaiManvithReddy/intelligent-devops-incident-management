"""
Shared Pytest fixtures.

The whole suite runs fully offline and without any external services:
- An in-memory SQLite database stands in for PostgreSQL.
- A seeded `MockClassifier` stands in for the OpenAI/LangChain backend.

This mirrors the "no API keys, no infrastructure" demo mode the project
supports in production (see `src.pipeline.classifier.get_classifier`), which
makes the test suite a good smoke test for that mode too.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Make sure Settings() resolves to safe, offline-friendly defaults
# regardless of any local `.env` file, *before* any app modules are imported.
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ALERT_WEBHOOK_URL", "")
os.environ.setdefault("ALERT_MIN_SEVERITY", "CRITICAL")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.dependencies import get_pipeline
from src.api.main import app
from src.config import get_settings
from src.db.models import Base
from src.db.session import get_db
from src.ingestion.log_reader import LogEvent
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import MockClassifier
from src.pipeline.runner import IncidentPipeline


@pytest.fixture()
def db_session():
    """A fresh, isolated in-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def mock_classifier():
    """A seeded MockClassifier so classification results are reproducible."""
    return MockClassifier(seed=1234)


@pytest.fixture()
def alert_dispatcher():
    return AlertDispatcher(settings=get_settings())


@pytest.fixture()
def pipeline(mock_classifier, alert_dispatcher):
    return IncidentPipeline(classifier=mock_classifier, alert_dispatcher=alert_dispatcher)


@pytest.fixture()
def sample_event():
    """A representative ERROR-level log event used across pipeline tests."""
    return LogEvent(
        timestamp=datetime(2024, 1, 15, 10, 23, 45, tzinfo=timezone.utc),
        host="web-01",
        service="nginx",
        level="ERROR",
        message="Upstream timeout connecting to backend pool",
        source="file:server-01.log",
    )


@pytest.fixture()
def info_event():
    """A representative INFO-level (routine) log event."""
    return LogEvent(
        timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        host="api-01",
        service="fastapi-app",
        level="INFO",
        message="Health check succeeded in 120ms",
        source="file:server-01.log",
    )


@pytest.fixture()
def client(db_session, pipeline):
    """A FastAPI TestClient wired to the in-memory DB and seeded pipeline."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_pipeline] = lambda: pipeline

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
