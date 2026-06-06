"""
Alert dispatching for high-severity incidents.

`AlertDispatcher` sends a structured notification (e.g. to a Slack incoming
webhook configured via `ALERT_WEBHOOK_URL`) whenever an incident report meets
or exceeds the configured `ALERT_MIN_SEVERITY` threshold. When no webhook URL
is configured (the default for local/demo runs), alerts are simply logged
in-process and recorded in `sent_alerts` for inspection/testing - no network
call is made and nothing ever fails for lack of credentials.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from src.config import Settings, get_settings
from src.db.models import Severity
from src.pipeline.schemas import IncidentReport

logger = logging.getLogger(__name__)


@dataclass
class AlertDispatcher:
    """Sends/records alerts for incident reports above a severity threshold."""

    settings: Settings = field(default_factory=get_settings)
    sent_alerts: list[IncidentReport] = field(default_factory=list)

    def _threshold_rank(self) -> int:
        try:
            return Severity(self.settings.alert_min_severity.upper()).rank
        except ValueError:
            return Severity.CRITICAL.rank

    def should_alert(self, report: IncidentReport) -> bool:
        try:
            severity = Severity(report.severity.upper())
        except ValueError:
            return False
        return severity.rank >= self._threshold_rank()

    def dispatch(self, report: IncidentReport) -> bool:
        """Send an alert for `report` if it meets the severity threshold.

        Returns True if an alert was sent/recorded, False if it was
        suppressed because the report's severity was below the threshold.
        """
        if not self.should_alert(report):
            return False

        self.sent_alerts.append(report)

        if not self.settings.alert_webhook_url:
            logger.warning(
                "ALERT [%s/%s] %s -- %s (no ALERT_WEBHOOK_URL configured; alert logged only)",
                report.severity,
                report.classification,
                report.summary,
                report.recommended_action,
            )
            return True

        payload = {
            "text": (
                f":rotating_light: *{report.severity}* incident detected\n"
                f"*Classification:* {report.classification}\n"
                f"*Summary:* {report.summary}\n"
                f"*Recommended action:* {report.recommended_action}\n"
                f"*Source:* {report.source} (host={report.host}, service={report.service})\n"
                f"*Detected at:* {report.detected_at.isoformat()}"
            )
        }

        try:
            response = httpx.post(self.settings.alert_webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to deliver alert webhook: %s", exc)

        return True
