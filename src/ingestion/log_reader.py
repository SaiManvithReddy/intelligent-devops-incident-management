"""
File-based log ingestion.

Reads structured log lines from simulated server log files (see
`src/ingestion/log_generator.py` for how the demo data is produced) and
converts them into normalized `LogEvent` objects ready for the AI
classification pipeline.

Expected line format (whitespace-delimited, pipe-separated fields)::

    2024-01-15T10:23:45Z | host=web-01 | service=nginx | level=ERROR | msg=Upstream timeout connecting to backend pool
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\S+)\s*\|\s*host=(?P<host>\S+)\s*\|\s*service=(?P<service>\S+)\s*\|\s*"
    r"level=(?P<level>\S+)\s*\|\s*msg=(?P<message>.+)$"
)


@dataclass(slots=True)
class LogEvent:
    """A normalized log/telemetry event ready to be classified."""

    timestamp: datetime
    host: str
    service: str
    level: str
    message: str
    source: str = "file"
    raw_line: str = field(default="", repr=False)

    @property
    def text(self) -> str:
        """Human-readable single-line representation used as LLM input."""
        return (
            f"[{self.timestamp.isoformat()}] host={self.host} service={self.service} "
            f"level={self.level} message={self.message}"
        )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "host": self.host,
            "service": self.service,
            "level": self.level,
            "message": self.message,
            "source": self.source,
        }


def parse_log_line(line: str, *, source: str = "file") -> LogEvent | None:
    """Parse a single raw log line into a `LogEvent`.

    Returns None for blank lines or lines that don't match the expected
    format (rather than raising), so a malformed line never halts ingestion
    of an entire file.
    """
    stripped = line.strip()
    if not stripped:
        return None

    match = _LINE_PATTERN.match(stripped)
    if not match:
        return LogEvent(
            timestamp=datetime.now(timezone.utc),
            host="unknown",
            service="unknown",
            level="UNKNOWN",
            message=stripped,
            source=source,
            raw_line=stripped,
        )

    groups = match.groupdict()
    timestamp = _parse_timestamp(groups["timestamp"])

    return LogEvent(
        timestamp=timestamp,
        host=groups["host"],
        service=groups["service"],
        level=groups["level"].upper(),
        message=groups["message"].strip(),
        source=source,
        raw_line=stripped,
    )


def _parse_timestamp(raw: str) -> datetime:
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)


def read_log_file(path: str | Path) -> Iterator[LogEvent]:
    """Yield `LogEvent` objects parsed from a single log file."""
    file_path = Path(path)
    source = f"file:{file_path.name}"
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = parse_log_line(line, source=source)
            if event is not None:
                yield event


def tail_log_directory(directory: str | Path, *, pattern: str = "*.log") -> Iterator[LogEvent]:
    """Yield `LogEvent` objects from every log file in `directory` matching `pattern`.

    Files are processed in sorted (deterministic) order, which keeps demo
    runs and tests reproducible.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return

    for file_path in sorted(dir_path.glob(pattern)):
        yield from read_log_file(file_path)
