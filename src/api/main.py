"""
FastAPI application entry point.

Run locally with::

    uvicorn src.api.main:app --reload --port 8000

Interactive API docs are then available at http://localhost:8000/docs
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health, incidents
from src.config import get_settings
from src.db.session import init_db

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Intelligent DevOps Incident Management API",
    description=(
        "REST API for an AI-powered DevOps incident management system. "
        "Ingests server logs/telemetry, classifies them with an "
        "LLM-backed (LangChain + OpenAI) pipeline -- with a deterministic "
        "mock fallback when no API key is configured -- and exposes "
        "structured incident data for dashboards and on-call tooling."
    ),
    version="1.0.0",
)

# Permissive CORS so the React dashboard (served from a different origin in
# local development, e.g. http://localhost:3000) can call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(incidents.router)


@app.on_event("startup")
def on_startup() -> None:
    """Ensure database tables exist before serving traffic."""
    try:
        init_db()
        logger.info("Database tables verified/created successfully.")
    except Exception as exc:  # pragma: no cover - depends on external services
        logger.warning("Could not initialize database on startup (%s). "
                       "The API will still start, but DB-backed endpoints may fail "
                       "until PostgreSQL is reachable.", exc)


@app.get("/", tags=["health"], summary="API root / welcome message")
def root() -> dict:
    return {
        "service": "Intelligent DevOps Incident Management API",
        "docs": "/docs",
        "health": "/health",
        "incidents": "/incidents",
        "summary": "/incidents/summary",
        "triage": "/incidents/triage",
    }
