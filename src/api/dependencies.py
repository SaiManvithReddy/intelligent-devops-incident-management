"""Shared FastAPI dependencies (DB sessions, pipeline singletons)."""
from __future__ import annotations

from functools import lru_cache

from src.config import get_settings
from src.db.session import get_db
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import get_classifier
from src.pipeline.runner import IncidentPipeline

__all__ = ["get_db", "get_pipeline"]


@lru_cache
def get_pipeline() -> IncidentPipeline:
    """Return a process-wide singleton `IncidentPipeline`.

    Cached so the (potentially expensive-to-construct) classifier backend is
    created once per process rather than per-request.
    """
    settings = get_settings()
    return IncidentPipeline(
        classifier=get_classifier(settings),
        alert_dispatcher=AlertDispatcher(settings=settings),
        settings=settings,
    )
