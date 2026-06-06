"""Health and readiness endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_pipeline
from src.api.schemas import HealthResponse
from src.config import get_settings
from src.db.session import engine
from src.ingestion.queue_consumer import RedisLogQueue
from src.pipeline.runner import IncidentPipeline

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health/readiness check")
def health(pipeline: IncidentPipeline = Depends(get_pipeline)) -> HealthResponse:
    """Report whether the API, database, Redis queue, and classifier are reachable."""
    settings = get_settings()

    database_status = "ok"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - depends on external services
        database_status = f"unavailable ({exc.__class__.__name__})"

    redis_status = "ok" if RedisLogQueue(settings).ping() else "unavailable"

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        classifier=type(pipeline.classifier).__name__,
        database=database_status,
        redis=redis_status,
    )
