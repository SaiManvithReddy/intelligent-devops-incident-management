import React from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SEVERITY_COLORS } from "./SeverityBadge";

/**
 * Severity breakdown chart: bar chart showing how many incidents currently
 * fall into each severity bucket (INFO / WARNING / CRITICAL / INCIDENT).
 */
export default function SeverityChart({ breakdown }) {
  const data = breakdown.map((entry) => ({ severity: entry.severity, count: entry.count }));

  return (
    <section className="card severity-chart">
      <header className="card-header">
        <h2>Severity Breakdown</h2>
      </header>

      <div className="chart-container">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="severity" stroke="#94a3b8" />
            <YAxis allowDecimals={false} stroke="#94a3b8" />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
              labelStyle={{ color: "#e2e8f0" }}
            />
            <Bar dataKey="count" radius={[6, 6, 0, 0]}>
              {data.map((entry) => (
                <Cell key={entry.severity} fill={SEVERITY_COLORS[entry.severity] || "#94a3b8"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="legend">
        {data.map((entry) => (
          <li key={entry.severity}>
            <span className="legend-swatch" style={{ backgroundColor: SEVERITY_COLORS[entry.severity] }} />
            {entry.severity}: <strong>{entry.count}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
