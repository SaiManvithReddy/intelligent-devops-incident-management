"""Tests for `src.ingestion.log_reader` - parsing raw log lines into events."""
from __future__ import annotations

from datetime import timezone

from src.ingestion.log_reader import parse_log_line, read_log_file, tail_log_directory

VALID_LINE = "2024-01-15T10:23:45Z | host=web-01 | service=nginx | level=ERROR | msg=Upstream timeout connecting to backend pool"


def test_parse_log_line_extracts_all_fields():
    event = parse_log_line(VALID_LINE)

    assert event is not None
    assert event.host == "web-01"
    assert event.service == "nginx"
    assert event.level == "ERROR"
    assert event.message == "Upstream timeout connecting to backend pool"
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.astimezone(timezone.utc).hour == 10


def test_parse_log_line_returns_none_for_blank_line():
    assert parse_log_line("") is None
    assert parse_log_line("   \n") is None


def test_parse_log_line_handles_malformed_line_gracefully():
    event = parse_log_line("this is not a structured log line at all", source="test")

    assert event is not None
    assert event.level == "UNKNOWN"
    assert event.host == "unknown"
    assert "this is not a structured log line" in event.message
    assert event.source == "test"


def test_read_log_file_yields_one_event_per_line(tmp_path):
    log_file = tmp_path / "sample.log"
    log_file.write_text(f"{VALID_LINE}\n{VALID_LINE}\n\n{VALID_LINE}\n", encoding="utf-8")

    events = list(read_log_file(log_file))

    assert len(events) == 3
    assert all(event.host == "web-01" for event in events)
    assert events[0].source == "file:sample.log"


def test_tail_log_directory_reads_all_matching_files_in_sorted_order(tmp_path):
    (tmp_path / "server-02.log").write_text(VALID_LINE + "\n", encoding="utf-8")
    (tmp_path / "server-01.log").write_text(f"{VALID_LINE}\n{VALID_LINE}\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text(VALID_LINE + "\n", encoding="utf-8")

    events = list(tail_log_directory(tmp_path))

    assert len(events) == 3
    # server-01.log (2 lines) must be processed before server-02.log (1 line)
    assert events[0].source == "file:server-01.log"
    assert events[2].source == "file:server-02.log"


def test_tail_log_directory_returns_empty_for_missing_directory(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert list(tail_log_directory(missing)) == []
