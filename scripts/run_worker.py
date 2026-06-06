"""
Background worker that continuously drains the Redis log queue, classifies
each event through the AI pipeline, and persists resulting incidents to
PostgreSQL. This is the production-shaped counterpart to the one-shot
`scripts/seed_demo_data.py` script.

Usage::

    python -m scripts.run_worker
    python -m scripts.run_worker --max-batches 5   # exit after N drain cycles (useful for demos/CI)
"""
from __future__ import annotations

import argparse
import logging
import time

from src.config import get_settings
from src.db.session import init_db, session_scope
from src.ingestion.queue_consumer import RedisLogQueue
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import get_classifier
from src.pipeline.runner import IncidentPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("incident-worker")


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously classify log events streamed via Redis.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds to wait between empty drain cycles")
    parser.add_argument("--batch-size", type=int, default=50, help="Max events to drain per cycle")
    parser.add_argument("--max-batches", type=int, default=None, help="Stop after this many drain cycles (omit to run forever)")
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    queue = RedisLogQueue(settings)
    classifier = get_classifier(settings)
    pipeline = IncidentPipeline(classifier=classifier, alert_dispatcher=AlertDispatcher(settings=settings), settings=settings)

    logger.info("Worker started. classifier=%s queue=%s", type(classifier).__name__, queue.queue_name)

    batches = 0
    while args.max_batches is None or batches < args.max_batches:
        if not queue.ping():
            logger.warning("Redis unavailable at %s:%s -- retrying in %.1fs", settings.redis_host, settings.redis_port, args.poll_interval)
            time.sleep(args.poll_interval)
            batches += 1
            continue

        with session_scope() as db:
            results = pipeline.run_from_queue(queue, db=db, max_items=args.batch_size)

        if results:
            logger.info("Processed %d event(s); %d alert(s) dispatched", len(results), sum(r.alert_sent for r in results))
        else:
            time.sleep(args.poll_interval)

        batches += 1

    logger.info("Worker exiting after %d batch cycle(s).", batches)


if __name__ == "__main__":
    main()
