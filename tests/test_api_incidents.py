"""
Tests for the FastAPI incident management REST API.

All tests use the `client` fixture from `conftest.py`, which overrides
the database (in-memory SQLite) and pipeline (seeded MockClassifier)
dependencies so no external services are required.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


def test_root_returns_welcome_payload(client):
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "Incident Management" in data["service"]
    assert "/incidents" in data["incidents"]


def test_health_endpoint_returns_ok_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["classifier"] == "MockClassifier"


def test_list_incidents_returns_empty_list_when_no_data(client):
    response = client.get("/incidents")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_triage_endpoint_classifies_and_returns_result(client):
    payload = {
        "message": "Database connection pool exhausted, 0 of 100 connections available",
        "service": "postgresql",
        "host": "db-primary",
        "level": "ERROR",
        "persist": True,
    }

    response = client.post("/incidents/triage", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["severity"] in ("INFO", "WARNING", "CRITICAL", "INCIDENT")
    assert data["classification"]
    assert data["recommended_action"]
    assert 0.0 <= data["confidence"] <= 1.0


def test_triage_endpoint_persists_incident_and_it_appears_in_list(client):
    client.post("/incidents/triage", json={
        "message": "Upstream service timeout",
        "service": "nginx",
        "host": "web-01",
        "level": "ERROR",
        "persist": True,
    })

    response = client.get("/incidents")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "manual-triage"


def test_list_incidents_filters_by_severity(client):
    client.post("/incidents/triage", json={"message": "test-event", "level": "INFO", "persist": True})

    list_all = client.get("/incidents")
    total = list_all.json()["total"]
    assert total >= 1

    result = client.get("/incidents")
    assert result.status_code == 200


def test_list_incidents_rejects_invalid_severity(client):
    response = client.get("/incidents?severity=BOGUS")

    assert response.status_code == 400
    assert "severity" in response.json()["detail"].lower()


def test_get_incident_by_id_returns_404_for_unknown_id(client):
    response = client.get("/incidents/nonexistent-id-12345")

    assert response.status_code == 404


def test_get_incident_by_id_returns_the_incident(client):
    triage_response = client.post("/incidents/triage", json={"message": "disk io error", "level": "CRITICAL", "persist": True})
    incident_id = triage_response.json()["incident"]["id"]

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == incident_id
    assert data["raw_message"] == "disk io error"


def test_resolve_incident_marks_it_as_resolved(client):
    triage_response = client.post("/incidents/triage", json={"message": "out of memory error", "level": "ERROR", "persist": True})
    incident_id = triage_response.json()["incident"]["id"]

    resolve_response = client.post(f"/incidents/{incident_id}/resolve", json={})

    assert resolve_response.status_code == 200
    data = resolve_response.json()
    assert data["is_resolved"] is True
    assert data["resolved_at"] is not None
    assert data["resolution_seconds"] is not None
    assert data["resolution_seconds"] >= 0


def test_summary_returns_severity_breakdown_and_counts(client):
    client.post("/incidents/triage", json={"message": "event 1", "level": "ERROR", "persist": True})
    client.post("/incidents/triage", json={"message": "event 2", "level": "WARNING", "persist": True})

    response = client.get("/incidents/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_incidents"] >= 2
    assert isinstance(data["severity_breakdown"], list)
    severity_names = [item["severity"] for item in data["severity_breakdown"]]
    assert "INFO" in severity_names
    assert "CRITICAL" in severity_names


def test_summary_mttr_is_none_with_no_resolved_incidents(client):
    client.post("/incidents/triage", json={"message": "unresolved event", "level": "ERROR", "persist": True})

    response = client.get("/incidents/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["mttr_seconds"] is None
    assert data["mttr_human"] is None


def test_summary_mttr_is_populated_after_resolving_incidents(client):
    triage_resp = client.post("/incidents/triage", json={"message": "disk full", "level": "CRITICAL", "persist": True})
    incident_id = triage_resp.json()["incident"]["id"]

    resolved_at = datetime.now(timezone.utc).isoformat()
    client.post(f"/incidents/{incident_id}/resolve", json={"resolved_at": resolved_at})

    response = client.get("/incidents/summary")
    data = response.json()

    assert data["mttr_seconds"] is not None
    assert data["mttr_human"] is not None
    assert data["resolved_incidents"] == 1
