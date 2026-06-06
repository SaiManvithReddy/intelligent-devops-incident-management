"""
AI-powered log classification.

Two interchangeable classifier implementations are provided behind the
`Classifier` protocol:

* `LangChainClassifier` - uses LangChain + the OpenAI chat completion API
  (via `langchain-openai`) with a structured-output parser to classify each
  log event as INFO / WARNING / CRITICAL / INCIDENT and produce a
  recommended action.

* `MockClassifier` - a fully local, dependency-free fallback that returns
  randomized-but-plausible classifications. It is automatically selected by
  `get_classifier()` whenever `OPENAI_API_KEY` is not configured, which is
  what allows this entire project to run end-to-end without any paid API
  access (see README "Running without an OpenAI API key").

Both implementations return a `ClassificationResult`, so the rest of the
pipeline never needs to know which one is in use.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.config import Settings, get_settings
from src.ingestion.log_reader import LogEvent
from src.pipeline.schemas import DEFAULT_RECOMMENDED_ACTIONS, SEVERITY_LEVELS, ClassificationResultSchema

_SYSTEM_PROMPT = """\
You are an expert Site Reliability Engineer (SRE) assistant embedded in an \
automated DevOps incident management pipeline. You will be given a single \
structured log/telemetry event. Classify it and respond ONLY with a JSON \
object matching this exact schema (no markdown, no commentary):

{{
  "severity": "INFO" | "WARNING" | "CRITICAL" | "INCIDENT",
  "classification": "<short label, e.g. 'Database Latency', 'Memory Pressure', 'Auth Failure'>",
  "confidence": <float between 0 and 1>,
  "recommended_action": "<concrete next step an on-call engineer should take>",
  "summary": "<one or two sentence human-readable summary of the event>"
}}

Severity guidance:
- INFO: routine, healthy operational activity. No human action needed.
- WARNING: early signs of degradation (elevated latency, resource pressure) \
that should be watched but are not yet customer-impacting.
- CRITICAL: a service or dependency is failing or about to fail in a way \
that requires prompt engineering attention (paging on-call).
- INCIDENT: active, customer-impacting outage or data-risk event requiring \
immediate incident response and cross-team coordination.
"""

_USER_PROMPT_TEMPLATE = """\
Classify the following log event:

Timestamp: {timestamp}
Host: {host}
Service: {service}
Log level: {level}
Message: {message}

Respond with the JSON object only.
"""


@dataclass(slots=True)
class ClassificationResult:
    """Normalized output of any classifier implementation."""

    severity: str
    classification: str
    confidence: float
    recommended_action: str
    summary: str
    model: str = "unknown"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_LEVELS:
            self.severity = "INFO"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @classmethod
    def from_schema(cls, schema: ClassificationResultSchema, *, model: str) -> "ClassificationResult":
        return cls(
            severity=schema.severity.upper(),
            classification=schema.classification,
            confidence=schema.confidence,
            recommended_action=schema.recommended_action,
            summary=schema.summary,
            model=model,
        )


@runtime_checkable
class Classifier(Protocol):
    """Protocol implemented by every classifier backend."""

    def classify(self, event: LogEvent) -> ClassificationResult:
        ...


class MockClassifier:
    """
    Deterministic-but-varied local classifier used when no OpenAI API key is
    configured (or when `force_mock=True`).

    It is intentionally *not* purely random: the original log `level` biases
    the chosen severity so demo output still looks coherent (an `ERROR` line
    is far more likely to be classified CRITICAL than an `INFO` line is),
    while still exercising the full INFO/WARNING/CRITICAL/INCIDENT spectrum.
    """

    name = "mock-classifier"

    _LEVEL_WEIGHTS: dict[str, dict[str, float]] = {
        "INFO": {"INFO": 0.75, "WARNING": 0.20, "CRITICAL": 0.04, "INCIDENT": 0.01},
        "WARNING": {"INFO": 0.15, "WARNING": 0.55, "CRITICAL": 0.25, "INCIDENT": 0.05},
        "ERROR": {"INFO": 0.05, "WARNING": 0.25, "CRITICAL": 0.50, "INCIDENT": 0.20},
        "CRITICAL": {"INFO": 0.02, "WARNING": 0.08, "CRITICAL": 0.55, "INCIDENT": 0.35},
        "UNKNOWN": {"INFO": 0.40, "WARNING": 0.30, "CRITICAL": 0.20, "INCIDENT": 0.10},
    }

    _CLASSIFICATION_LABELS: dict[str, list[str]] = {
        "INFO": ["Routine Activity", "Healthy Check-in", "Scheduled Job", "Normal Traffic"],
        "WARNING": ["Latency Degradation", "Resource Pressure", "Elevated Retry Rate", "Capacity Warning"],
        "CRITICAL": ["Service Outage Risk", "Database Latency", "Memory Pressure", "Dependency Failure"],
        "INCIDENT": ["Active Outage", "Customer-Impacting Failure", "Data Loss Risk", "Security Incident"],
    }

    def __init__(self, *, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def classify(self, event: LogEvent) -> ClassificationResult:
        severity = self._weighted_severity(event.level)
        classification = self._rng.choice(self._CLASSIFICATION_LABELS[severity])
        confidence = round(self._rng.uniform(0.55, 0.97), 2)
        recommended_action = DEFAULT_RECOMMENDED_ACTIONS[severity]
        summary = (
            f"[mock] {event.service} on {event.host} reported a {severity.lower()}-level "
            f"event classified as '{classification}': {event.message}"
        )
        return ClassificationResult(
            severity=severity,
            classification=classification,
            confidence=confidence,
            recommended_action=recommended_action,
            summary=summary,
            model=self.name,
        )

    def _weighted_severity(self, level: str) -> str:
        weights = self._LEVEL_WEIGHTS.get(level.upper(), self._LEVEL_WEIGHTS["UNKNOWN"])
        levels = list(weights.keys())
        cumulative = []
        total = 0.0
        for lvl in levels:
            total += weights[lvl]
            cumulative.append(total)

        pick = self._rng.uniform(0, total)
        for lvl, threshold in zip(levels, cumulative):
            if pick <= threshold:
                return lvl
        return levels[-1]


class LangChainClassifier:
    """
    Classifier backed by LangChain + OpenAI chat completions.

    The prompt instructs the model to return a strict JSON object, which is
    then validated against `ClassificationResultSchema`. If the model ever
    returns malformed output, we degrade gracefully to a `MockClassifier`
    result rather than crashing the pipeline.
    """

    name = "langchain-openai"

    def __init__(self, settings: Settings | None = None, *, llm=None) -> None:
        self._settings = settings or get_settings()
        self._fallback = MockClassifier()
        self._llm = llm if llm is not None else self._build_llm()

    def _build_llm(self):
        # Imported lazily so the dependency is optional at import time -
        # MockClassifier-only environments (e.g. CI without network access)
        # never need `langchain_openai` installed to import this module.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self._settings.openai_model,
            temperature=self._settings.langchain_temperature,
            api_key=self._settings.openai_api_key,
        )

    def classify(self, event: LogEvent) -> ClassificationResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=_USER_PROMPT_TEMPLATE.format(
                    timestamp=event.timestamp.isoformat(),
                    host=event.host,
                    service=event.service,
                    level=event.level,
                    message=event.message,
                )
            ),
        ]

        try:
            response = self._llm.invoke(messages)
            payload = self._extract_json(response.content)
            schema = ClassificationResultSchema.model_validate(payload)
            return ClassificationResult.from_schema(schema, model=self._settings.openai_model)
        except Exception:
            # Network failures, malformed JSON, schema mismatches, rate
            # limits, etc. should never take the whole pipeline down -
            # degrade to the local mock classifier for this single event.
            result = self._fallback.classify(event)
            result.model = f"{self.name}-fallback"
            return result

    @staticmethod
    def _extract_json(content) -> dict:
        """Best-effort extraction of a JSON object from an LLM response."""
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        text = str(content).strip()

        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"No JSON object found in LLM response: {text!r}")

        return json.loads(text[start : end + 1])


def get_classifier(settings: Settings | None = None, *, force_mock: bool = False) -> Classifier:
    """
    Factory that returns the appropriate classifier for the current
    configuration.

    Returns a `MockClassifier` whenever `force_mock=True` or no OpenAI API
    key is configured, and a `LangChainClassifier` otherwise. This is the
    single source of truth for "do we have AI access or not" - callers
    should always go through this function rather than instantiating a
    classifier directly.
    """
    settings = settings or get_settings()
    if force_mock or not settings.has_openai_key:
        return MockClassifier()
    return LangChainClassifier(settings)
