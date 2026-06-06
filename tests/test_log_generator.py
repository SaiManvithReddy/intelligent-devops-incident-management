"""Tests for `src.ingestion.log_generator` - realistic sample log generation."""
from __future__ import annotations

from src.ingestion.log_generator import generate_log_lines, write_sample_log_files
from src.ingestion.log_reader import parse_log_line


def test_generate_log_lines_returns_requested_count():
    lines = generate_log_lines(25, seed=1)

    assert len(lines) == 25
    assert all(isinstance(line, str) and "| host=" in line for line in lines)


def test_generate_log_lines_produces_parseable_well_formed_lines():
    lines = generate_log_lines(10, seed=2)

    for line in lines:
        event = parse_log_line(line)
        assert event is not None
        assert event.level != "UNKNOWN"
        assert event.host
        assert event.service
        assert event.message


def test_generate_log_lines_is_reproducible_given_same_seed():
    first = generate_log_lines(15, seed=99)
    second = generate_log_lines(15, seed=99)

    assert first == second


def test_generate_log_lines_differs_for_different_seeds():
    first = generate_log_lines(15, seed=1)
    second = generate_log_lines(15, seed=2)

    assert first != second


def test_write_sample_log_files_creates_expected_number_of_files(tmp_path):
    written = write_sample_log_files(tmp_path, total_lines=40, files=4, seed=7)

    assert len(written) == 4
    for path in written:
        assert path.exists()
        assert path.suffix == ".log"

    total_lines = sum(len(path.read_text(encoding="utf-8").strip().splitlines()) for path in written)
    assert total_lines == 40
