const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`API request to ${path} failed (${response.status}): ${detail}`);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

/** Fetch a page of incidents, optionally filtered by severity/service/resolved status. */
export function fetchIncidents({ severity, service, resolved, limit = 25, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  if (service) params.set("service", service);
  if (resolved !== undefined && resolved !== null) params.set("resolved", String(resolved));
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return request(`/incidents?${params.toString()}`);
}

/** Fetch aggregate statistics (severity breakdown, MTTR, etc.). */
export function fetchSummary() {
  return request("/incidents/summary");
}

/** Trigger manual triage of an arbitrary log line / message. */
export function triggerTriage(payload) {
  return request("/incidents/triage", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Mark an incident as resolved (used to demonstrate MTTR updates). */
export function resolveIncident(incidentId) {
  return request(`/incidents/${incidentId}/resolve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/** Fetch backend/service health information. */
export function fetchHealth() {
  return request("/health");
}

export { API_BASE_URL };
