import React from "react";

const SEVERITY_COLORS = {
  INFO: "#38bdf8",
  WARNING: "#fbbf24",
  CRITICAL: "#fb7185",
  INCIDENT: "#ef4444",
};

export default function SeverityBadge({ severity }) {
  const color = SEVERITY_COLORS[severity] || "#94a3b8";
  return (
    <span
      className="severity-badge"
      style={{ backgroundColor: `${color}22`, color, borderColor: `${color}55` }}
    >
      {severity}
    </span>
  );
}

export { SEVERITY_COLORS };
