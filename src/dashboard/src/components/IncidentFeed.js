import React from "react";
import SeverityBadge from "./SeverityBadge";

function formatTimestamp(isoString) {
  if (!isoString) return "--";
  try {
    return new Date(isoString).toLocaleString();
  } catch {
    return isoString;
  }
}

/**
 * Real-time incident feed: a scrollable, auto-refreshing list of the most
 * recently detected incidents, newest first.
 */
export default function IncidentFeed({ incidents, loading, error, onResolve }) {
  return (
    <section className="card incident-feed">
      <header className="card-header">
        <h2>Real-Time Incident Feed</h2>
        {loading && <span className="pill pill-muted">refreshing&hellip;</span>}
      </header>

      {error && <p className="error-text">Failed to load incidents: {error}</p>}

      {!error && incidents.length === 0 && !loading && (
        <p className="empty-text">No incidents recorded yet. Run the seeding script to generate demo data.</p>
      )}

      <ul className="incident-list">
        {incidents.map((incident) => (
          <li key={incident.id} className="incident-row">
            <div className="incident-row-main">
              <SeverityBadge severity={incident.severity} />
              <div className="incident-row-text">
                <p className="incident-classification">{incident.classification}</p>
                <p className="incident-summary">{incident.summary}</p>
                <p className="incident-meta">
                  {formatTimestamp(incident.detected_at)} &middot; source: {incident.source}
                </p>
              </div>
            </div>
            <div className="incident-row-actions">
              {incident.is_resolved ? (
                <span className="pill pill-resolved">resolved</span>
              ) : (
                <button className="button-secondary" onClick={() => onResolve(incident.id)}>
                  Mark resolved
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
