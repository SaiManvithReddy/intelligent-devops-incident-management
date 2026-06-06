"""SQLAlchemy ORM models for the incident management system."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""


class Severity(str, enum.Enum):
    """Severity levels produced by the AI classification pipeline."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INCIDENT = "INCIDENT"

    @classmethod
    def ordered(cls) -> list["Severity"]:
        """Severity levels ordered from least to most severe."""
        return [cls.INFO, cls.WARNING, cls.CRITICAL, cls.INCIDENT]

    @property
    def rank(self) -> int:
        """Numeric rank used for sorting/comparison (higher = more severe)."""
        return self.ordered().index(self)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Incident(Base):
    """A single classified log/telemetry event persisted as an incident record."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)

    # Original raw data
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)

    # AI classification output
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=16), nullable=False, index=True
    )
    classification: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Lifecycle / MTTR tracking
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Incident id={self.id!r} severity={self.severity!r} "
            f"classification={self.classification!r} detected_at={self.detected_at!r}>"
        )

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    @property
    def resolution_seconds(self) -> float | None:
        """Time-to-resolution in seconds, or None if still open."""
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.detected_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "raw_message": self.raw_message,
            "severity": self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "classification": self.classification,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "summary": self.summary,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_resolved": self.is_resolved,
            "resolution_seconds": self.resolution_seconds,
        }
