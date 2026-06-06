import React, { useCallback, useEffect, useState } from "react";
import "./App.css";
import IncidentFeed from "./components/IncidentFeed";
import MttrMetrics from "./components/MttrMetrics";
import SeverityChart from "./components/SeverityChart";
import TriagePanel from "./components/TriagePanel";
import { fetchIncidents, fetchSummary, resolveIncident, triggerTriage } from "./api";

const REFRESH_INTERVAL_MS = 15000;

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [severityFilter, setSeverityFilter] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [incidentPage, summaryData] = await Promise.all([
        fetchIncidents({ severity: severityFilter || undefined, limit: 25 }),
        fetchSummary(),
      ]);
      setIncidents(incidentPage.items);
      setSummary(summaryData);
      setError(null);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }, [severityFilter]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  async function handleResolve(incidentId) {
    try {
      await resolveIncident(incidentId);
      await loadData();
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  async function handleTriage(payload) {
    const response = await triggerTriage(payload);
    await loadData();
    return response;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Intelligent DevOps Incident Management</h1>
          <p className="muted-text">
            AI-classified server log &amp; telemetry incidents, in real time.
          </p>
        </div>
        <div className="severity-filter">
          <label htmlFor="severity-filter">Filter by severity</label>
          <select
            id="severity-filter"
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="">All severities</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="INCIDENT">INCIDENT</option>
          </select>
        </div>
      </header>

      {error && <p className="error-banner">{error}</p>}

      <MttrMetrics summary={summary} />

      <div className="grid-two">
        <SeverityChart breakdown={summary?.severity_breakdown || []} />
        <TriagePanel onTriage={handleTriage} />
      </div>

      <IncidentFeed incidents={incidents} loading={loading} error={null} onResolve={handleResolve} />

      <footer className="app-footer">
        <p>
          Data refreshes automatically every {REFRESH_INTERVAL_MS / 1000} seconds. Backend: FastAPI + LangChain
          + PostgreSQL + Redis.
        </p>
      </footer>
    </div>
  );
}
