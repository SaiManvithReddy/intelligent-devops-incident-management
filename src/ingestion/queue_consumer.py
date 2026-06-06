"""
Redis-backed message queue for streaming log/telemetry events.

`RedisLogQueue` wraps a simple Redis list used as a FIFO queue (`LPUSH` /
`BRPOP`) so that log producers (e.g. log shippers, telemetry agents) and the
ingestion pipeline can be decoupled. Events are serialized as JSON.

If Redis is unreachable (e.g. running the demo without Docker), callers
should catch `redis.exceptions.RedisError` and fall back to file-based
ingestion - see `src/pipeline/runner.py` for an example of that pattern.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator

import redis

from src.config import Settings, get_settings
from src.ingestion.log_reader import LogEvent


class RedisLogQueue:
    """Thin wrapper around a Redis list used as a log-event FIFO queue."""

    def __init__(self, settings: Settings | None = None, *, client: redis.Redis | None = None) -> None:
        self._settings = settings or get_settings()
        self._queue_name = self._settings.redis_log_queue
        self._client = client or redis.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            db=self._settings.redis_db,
            decode_responses=True,
        )

    @property
    def queue_name(self) -> str:
        return self._queue_name

    def ping(self) -> bool:
        """Return True if the Redis server is reachable."""
        try:
            return bool(self._client.ping())
        except redis.exceptions.RedisError:
            return False

    def publish(self, event: LogEvent) -> None:
        """Push a single log event onto the queue (JSON-encoded)."""
        self._client.lpush(self._queue_name, json.dumps(event.to_dict()))

    def publish_many(self, events: list[LogEvent]) -> int:
        """Push multiple events at once. Returns the number published."""
        if not events:
            return 0
        payloads = [json.dumps(event.to_dict()) for event in events]
        self._client.lpush(self._queue_name, *payloads)
        return len(payloads)

    def consume(self, *, timeout: int = 1) -> LogEvent | None:
        """Block (up to `timeout` seconds) for the next event, or return None."""
        result = self._client.brpop([self._queue_name], timeout=timeout)
        if result is None:
            return None
        _, payload = result
        return self._deserialize(payload)

    def drain(self, *, max_items: int | None = None) -> Iterator[LogEvent]:
        """Yield events currently buffered in the queue without blocking."""
        count = 0
        while max_items is None or count < max_items:
            payload = self._client.rpop(self._queue_name)
            if payload is None:
                return
            yield self._deserialize(payload)
            count += 1

    def length(self) -> int:
        return int(self._client.llen(self._queue_name))

    @staticmethod
    def _deserialize(payload: str) -> LogEvent:
        data = json.loads(payload)
        timestamp = data.get("timestamp")
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp) if timestamp else datetime.now(timezone.utc)
        except ValueError:
            parsed_timestamp = datetime.now(timezone.utc)

        return LogEvent(
            timestamp=parsed_timestamp,
            host=data.get("host", "unknown"),
            service=data.get("service", "unknown"),
            level=data.get("level", "UNKNOWN"),
            message=data.get("message", ""),
            source=data.get("source", "redis"),
        )
