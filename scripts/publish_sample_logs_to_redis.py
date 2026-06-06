"""
Publishes the generated sample log events onto the Redis-backed log queue, to
simulate a live stream of telemetry arriving from many hosts (e.g. via a log
shipper such as Filebeat/Fluentd/Vector in a real deployment).

Pairs with `scripts/run_worker.py`, which drains the queue and runs each
event through the classification pipeline.

Usage::

    python -m scripts.publish_sample_logs_to_redis
    python -m scripts.publish_sample_logs_to_redis --count 50
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.config import get_settings
from src.ingestion.log_generator import write_sample_log_files
from src.ingestion.log_reader import tail_log_directory
from src.ingestion.queue_consumer import RedisLogQueue


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish sample log events to the Redis queue.")
    parser.add_argument("--count", type=int, default=None, help="Limit the number of events published")
    args = parser.parse_args()

    settings = get_settings()
    log_dir = Path(settings.sample_log_dir)
    if not any(log_dir.glob("*.log")):
        print(f"No sample logs found in {log_dir}, generating {settings.sample_log_count} lines...")
        write_sample_log_files(log_dir, total_lines=settings.sample_log_count)

    events = list(tail_log_directory(log_dir))
    if args.count is not None:
        events = events[: args.count]

    queue = RedisLogQueue(settings)
    if not queue.ping():
        raise SystemExit(
            f"Could not reach Redis at {settings.redis_host}:{settings.redis_port}. "
            "Start it via `docker compose up redis` or run Redis locally before publishing."
        )

    published = queue.publish_many(events)
    print(f"Published {published} events to Redis queue '{queue.queue_name}' (length now {queue.length()})")


if __name__ == "__main__":
    main()
