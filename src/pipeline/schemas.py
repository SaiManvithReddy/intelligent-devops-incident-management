"""Shared Pydantic schemas for the classification pipeline and API layer."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

SEVERITY_LEVELS = ("INFO", "WARNING", "CRITICAL", "INCIDENT")

DEFAULT_RECOMMENDED_ACTIONS: dict[str, str] = {
    "INFO": "No action required. Continue routine monitoring.",
    "WARNING": "Monitor the affected service closely and review related metrics over the next 30 minutes.",
    "CRITICAL": "Page the on-call engineer for the affected service and begin investigating immediately.",
    "INCIDENT": "Declare a major incident, assemble the incident response team, and begin the runbook for service restoration.",
}


class ClassificationResultSchema(BaseModel):
    """Structured output contract returned by any classifier implementation."""

    severity: str = Field(description="One of INFO, WARNING, CRITICAL, INCIDENT")
    classification: str = Field(description="Short label describing the type of event, e.g. 'Database Latency'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    recommended_action: str = Field(description="Concrete next step an engineer should take")
    summary: str = Field(description="One or two sentence human-readable summary of the event")


class IncidentReport(BaseModel):
    """Structured incident report generated for each classified log event."""

    source: str
    raw_message: str
    host: str | None = None
    service: str | None = None
    detected_at: datetime
    severity: str
    classification: str
    confidence: float
    recommended_action: str
    summary: str

    def to_markdown(self) -> str:
        """Render the report as a small Markdown document (e.g. for Slack/alerts)."""
        return (
            f"### Incident Report - {self.classification}\n"
            f"- **Severity:** {self.severity}\n"
            f"- **Detected at:** {self.detected_at.isoformat()}\n"
            f"- **Source:** {self.source}"
            + (f" (host={self.host}, service={self.service})" if self.host else "")
            + "\n"
            f"- **Summary:** {self.summary}\n"
            f"- **Recommended action:** {self.recommended_action}\n"
            f"- **Confidence:** {self.confidence:.2f}\n"
            f"- **Raw message:** `{self.raw_message}`\n"
        )
