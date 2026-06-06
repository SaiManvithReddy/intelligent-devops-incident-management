import React from "react";

/**
 * MTTR (Mean Time To Resolution) and headline incident metrics, displayed as
 * a row of stat cards.
 */
export default function MttrMetrics({ summary }) {
  if (!summary) return null;

  const stats = [
    { label: "Total Incidents", value: summary.total_incidents },
    { label: "Open", value: summary.open_incidents, accent: "#fb7185" },
    { label: "Resolved", value: summary.resolved_incidents, accent: "#34d399" },
    { label: "MTTR", value: summary.mttr_human || "n/a", accent: "#38bdf8" },
    { label: "Top Classification", value: summary.most_common_classification || "n/a" },
  ];

  return (
    <section className="card mttr-metrics">
      <header className="card-header">
        <h2>MTTR &amp; Key Metrics</h2>
        <span className="pill pill-muted">
          updated {summary.generated_at ? new Date(summary.generated_at).toLocaleTimeString() : "--"}
        </span>
      </header>

      <div className="stat-grid">
        {stats.map((stat) => (
          <div className="stat-card" key={stat.label}>
            <p className="stat-label">{stat.label}</p>
            <p className="stat-value" style={stat.accent ? { color: stat.accent } : undefined}>
              {stat.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
