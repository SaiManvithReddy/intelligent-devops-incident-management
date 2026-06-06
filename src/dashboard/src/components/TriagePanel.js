import React, { useState } from "react";
import SeverityBadge from "./SeverityBadge";

/**
 * Manual triage panel: lets an on-call engineer paste a raw log line (or a
 * free-text message) and immediately run it through the AI classification
 * pipeline via POST /incidents/triage.
 */
export default function TriagePanel({ onTriage }) {
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!message.trim()) return;

    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const response = await onTriage({ message: message.trim(), service: "manual-triage", host: "dashboard" });
      setResult(response);
      setMessage("");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card triage-panel">
      <header className="card-header">
        <h2>Manual Triage</h2>
      </header>
      <p className="muted-text">
        Paste a suspicious log message and run it through the AI pipeline immediately.
      </p>
      <form onSubmit={handleSubmit} className="triage-form">
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="e.g. Database connection pool exhausted, 0 of 100 connections available"
          rows={3}
        />
        <button type="submit" className="button-primary" disabled={submitting || !message.trim()}>
          {submitting ? "Classifying…" : "Run triage"}
        </button>
      </form>

      {error && <p className="error-text">{error}</p>}

      {result && (
        <div className="triage-result">
          <div className="triage-result-header">
            <SeverityBadge severity={result.severity} />
            <strong>{result.classification}</strong>
            <span className="muted-text">confidence {(result.confidence * 100).toFixed(0)}%</span>
          </div>
          <p>{result.summary}</p>
          <p className="muted-text">
            <strong>Recommended action:</strong> {result.recommended_action}
          </p>
          {result.alert_sent && <span className="pill pill-alert">alert dispatched</span>}
        </div>
      )}
    </section>
  );
}
