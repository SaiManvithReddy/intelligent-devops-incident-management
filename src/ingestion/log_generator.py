"""
Generates realistic-looking server log files and telemetry samples for demo
and testing purposes, so the whole system can be exercised end-to-end without
any real production infrastructure.

Run directly to (re)generate the sample data set::

    python -m src.ingestion.log_generator
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import get_settings

HOSTS = ["web-01", "web-02", "api-01", "api-02", "worker-03", "db-primary", "cache-01", "lb-edge"]
SERVICES = ["nginx", "fastapi-app", "celery-worker", "postgresql", "redis", "auth-service", "payments-service"]

# Each tuple is (level, message_template, relative_weight).
# Templates intentionally span the full spectrum from routine INFO chatter to
# outright outage-level errors, so the classifier has a realistic mix to work
# with - and so the mock classifier's random output still "looks" plausible.
_TEMPLATES: list[tuple[str, str, int]] = [
    ("INFO", "Health check succeeded in {latency}ms", 30),
    ("INFO", "Request GET /api/v1/status completed with 200 in {latency}ms", 28),
    ("INFO", "Scheduled job '{job}' completed successfully", 18),
    ("INFO", "Cache hit ratio at {pct}% over the last 5 minutes", 14),
    ("INFO", "User session created for user_id={user_id}", 12),
    ("WARNING", "Response latency degraded to {latency}ms (threshold 500ms)", 16),
    ("WARNING", "Memory usage at {pct}% and climbing", 14),
    ("WARNING", "Connection pool utilization at {pct}% ({conns}/100 connections)", 12),
    ("WARNING", "Retrying failed request to {service} (attempt {attempt}/3)", 12),
    ("WARNING", "Disk usage on /var/log at {pct}% capacity", 10),
    ("ERROR", "Upstream timeout connecting to backend pool '{service}'", 10),
    ("ERROR", "Database query exceeded timeout after {latency}ms: SELECT * FROM orders WHERE status='pending'", 9),
    ("ERROR", "Unhandled exception in handler '{job}': ConnectionResetError", 8),
    ("ERROR", "Failed to acquire lock on resource '{job}' after {attempt} attempts", 7),
    ("ERROR", "TLS handshake failed for client {ip}: certificate verify failed", 6),
    ("CRITICAL", "Service '{service}' is not responding to health checks - 5 consecutive failures", 5),
    ("CRITICAL", "Out of memory: kernel invoked the OOM killer on process '{service}'", 4),
    ("CRITICAL", "Database replication lag exceeded {latency} seconds on db-replica-02", 4),
    ("CRITICAL", "Disk full on /var/lib/postgresql - write operations failing", 3),
    ("CRITICAL", "Payment gateway returning 5xx for {pct}% of transactions in the last 60 seconds", 3),
]

_JOBS = ["nightly-report", "cleanup-temp-files", "reindex-search", "send-digest-emails", "rotate-credentials"]


def _weighted_choice(rng: random.Random) -> tuple[str, str]:
    total = sum(weight for _, _, weight in _TEMPLATES)
    pick = rng.uniform(0, total)
    upto = 0.0
    for level, template, weight in _TEMPLATES:
        upto += weight
        if upto >= pick:
            return level, template
    return _TEMPLATES[-1][0], _TEMPLATES[-1][1]


def _render(template: str, rng: random.Random) -> str:
    return template.format(
        latency=rng.choice([120, 180, 240, 310, 480, 620, 850, 1200, 2400, 5000]),
        pct=rng.randint(55, 99),
        conns=rng.randint(40, 100),
        attempt=rng.randint(1, 3),
        job=rng.choice(_JOBS),
        service=rng.choice(SERVICES),
        user_id=rng.randint(1000, 99999),
        ip=f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
    )


def generate_log_lines(count: int, *, seed: int | None = None, start: datetime | None = None) -> list[str]:
    """Generate `count` realistic, chronologically-ordered raw log lines."""
    rng = random.Random(seed)
    start = start or (datetime.now(timezone.utc) - timedelta(hours=2))

    lines: list[str] = []
    timestamp = start
    for _ in range(count):
        timestamp += timedelta(seconds=rng.randint(1, 45))
        level, template = _weighted_choice(rng)
        message = _render(template, rng)
        host = rng.choice(HOSTS)
        service = rng.choice(SERVICES)
        ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{ts_str} | host={host} | service={service} | level={level} | msg={message}")

    return lines


def write_sample_log_files(
    output_dir: str | Path,
    *,
    total_lines: int = 200,
    files: int = 4,
    seed: int | None = 42,
) -> list[Path]:
    """Write `files` sample `.log` files containing `total_lines` events total.

    Returns the list of file paths written. Existing files are overwritten so
    repeated runs produce a stable, reproducible demo data set.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    per_file = max(1, total_lines // files)
    written: list[Path] = []

    base_start = datetime.now(timezone.utc) - timedelta(hours=files)
    for index in range(files):
        file_seed = rng.randint(0, 1_000_000)
        file_start = base_start + timedelta(hours=index)
        lines = generate_log_lines(per_file, seed=file_seed, start=file_start)
        file_path = out_dir / f"server-{index + 1:02d}.log"
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(file_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realistic sample server log files for demo purposes.")
    settings = get_settings()
    parser.add_argument("--output-dir", default=settings.sample_log_dir, help="Directory to write .log files into")
    parser.add_argument("--total-lines", type=int, default=settings.sample_log_count, help="Total number of log lines to generate")
    parser.add_argument("--files", type=int, default=4, help="Number of log files to split the output across")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible output")
    args = parser.parse_args()

    written = write_sample_log_files(args.output_dir, total_lines=args.total_lines, files=args.files, seed=args.seed)
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
