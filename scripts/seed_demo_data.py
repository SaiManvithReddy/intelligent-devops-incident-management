"""
Demo data seeding script.

Generates realistic sample log files (if they don't already exist), runs them
through the full classification pipeline, persists the resulting incidents to
PostgreSQL, and randomly marks a portion of them as "resolved" with a
plausible resolution time so the MTTR dashboard widget has something
meaningful to display.

Usage::

    python -m scripts.seed_demo_data
    python -m scripts.seed_demo_data --reset      # wipe existing incidents first
    python -m scripts.seed_demo_data --force-mock # ignore OPENAI_API_KEY, use MockClassifier
"""
from __future__ import annotations

import argparse
import random
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete

from src.config import get_settings
from src.db.models import Incident
from src.db.session import init_db, session_scope
from src.ingestion.log_generator import write_sample_log_files
from src.ingestion.log_reader import tail_log_directory
from src.pipeline.alerts import AlertDispatcher
from src.pipeline.classifier import get_classifier
from src.pipeline.runner import IncidentPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the database with realistic demo incidents.")
    parser.add_argument("--reset", action="store_true", help="Delete all existing incidents before seeding")
    parser.add_argument("--force-mock", action="store_true", help="Always use the MockClassifier, even if an OpenAI key is configured")
    parser.add_argument("--resolve-fraction", type=float, default=0.6, help="Fraction of seeded incidents to mark resolved (for MTTR demo)")
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    log_dir = Path(settings.sample_log_dir)
    if not any(log_dir.glob("*.log")):
        print(f"No sample logs found in {log_dir}, generating {settings.sample_log_count} lines...")
        write_sample_log_files(log_dir, total_lines=settings.sample_log_count)

    events = list(tail_log_directory(log_dir))
    print(f"Loaded {len(events)} log events from {log_dir}")

    classifier = get_classifier(settings, force_mock=args.force_mock)
    print(f"Using classifier backend: {type(classifier).__name__}")

    pipeline = IncidentPipeline(classifier=classifier, alert_dispatcher=AlertDispatcher(settings=settings), settings=settings)

    rng = random.Random(7)

    with session_scope() as db:
        if args.reset:
            deleted = db.execute(delete(Incident))
            print(f"Deleted {deleted.rowcount} existing incident(s)")

        results = pipeline.run_batch(events, db=db)

        resolved_count = 0
        for result in results:
            if result.incident is None:
                continue
            if rng.random() < args.resolve_fraction:
                resolution_minutes = rng.randint(2, 180)
                result.incident.resolved_at = result.incident.detected_at + timedelta(minutes=resolution_minutes)
                db.add(result.incident)
                resolved_count += 1

    severity_counts: dict[str, int] = {}
    for result in results:
        severity_counts[result.classification.severity] = severity_counts.get(result.classification.severity, 0) + 1

    print(f"Seeded {len(results)} incidents ({resolved_count} marked resolved).")
    print("Severity breakdown:")
    for severity, count in sorted(severity_counts.items()):
        print(f"  {severity:<10} {count}")
    print(f"Alerts dispatched: {len(pipeline.alert_dispatcher.sent_alerts)}")


if __name__ == "__main__":
    main()
