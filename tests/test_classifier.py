"""
Tests for the AI classification pipeline (`src.pipeline.classifier`).

These tests focus on `MockClassifier` and the `get_classifier` factory, since
they are guaranteed to run without network access or an OpenAI API key - the
exact "no infrastructure required" guarantee this project makes. Behavior of
`LangChainClassifier` around malformed-JSON fallback is also covered using a
stubbed LLM so no real API calls are made.
"""
from __future__ import annotations

from src.config import Settings
from src.pipeline.classifier import (
    ClassificationResult,
    LangChainClassifier,
    MockClassifier,
    get_classifier,
)
from src.pipeline.schemas import SEVERITY_LEVELS


def test_mock_classifier_returns_a_valid_classification_result(sample_event):
    classifier = MockClassifier(seed=42)

    result = classifier.classify(sample_event)

    assert isinstance(result, ClassificationResult)
    assert result.severity in SEVERITY_LEVELS
    assert result.classification
    assert 0.0 <= result.confidence <= 1.0
    assert result.recommended_action
    assert sample_event.message in result.summary


def test_mock_classifier_is_deterministic_given_the_same_seed(sample_event):
    first = MockClassifier(seed=2024).classify(sample_event)
    second = MockClassifier(seed=2024).classify(sample_event)

    assert first.severity == second.severity
    assert first.classification == second.classification
    assert first.confidence == second.confidence


def test_mock_classifier_biases_severity_based_on_log_level(sample_event, info_event):
    classifier = MockClassifier(seed=7)

    error_severities = [classifier.classify(sample_event).severity for _ in range(300)]
    info_severities = [classifier.classify(info_event).severity for _ in range(300)]

    error_high = sum(1 for s in error_severities if s in ("CRITICAL", "INCIDENT"))
    info_high = sum(1 for s in info_severities if s in ("CRITICAL", "INCIDENT"))
    info_low = sum(1 for s in info_severities if s == "INFO")
    error_low = sum(1 for s in error_severities if s == "INFO")

    # ERROR-level events should be classified as high severity far more often
    # than routine INFO-level events, and vice versa for low severity.
    assert error_high > info_high
    assert info_low > error_low


def test_classification_result_normalizes_invalid_severity_and_clamps_confidence():
    result = ClassificationResult(
        severity="not-a-real-severity",
        classification="Weird Event",
        confidence=5.0,
        recommended_action="Investigate",
        summary="A summary",
    )

    assert result.severity == "INFO"
    assert result.confidence == 1.0


def test_get_classifier_returns_mock_classifier_when_no_api_key_configured():
    settings = Settings(openai_api_key="")

    classifier = get_classifier(settings)

    assert isinstance(classifier, MockClassifier)


def test_get_classifier_returns_mock_classifier_when_force_mock_is_set():
    settings = Settings(openai_api_key="sk-fake-test-key-12345")

    classifier = get_classifier(settings, force_mock=True)

    assert isinstance(classifier, MockClassifier)


def test_get_classifier_returns_langchain_classifier_when_api_key_present(monkeypatch):
    settings = Settings(openai_api_key="sk-fake-test-key-12345")

    # Avoid constructing a real ChatOpenAI client (and any network setup) by
    # stubbing out the LLM-builder that the factory's chosen class relies on.
    monkeypatch.setattr(LangChainClassifier, "_build_llm", lambda self: _StubLLM('{"severity": "INFO"}'))

    classifier = get_classifier(settings)

    assert isinstance(classifier, LangChainClassifier)


def test_langchain_classifier_falls_back_to_mock_on_malformed_llm_output(sample_event):
    settings = Settings(openai_api_key="sk-fake-test-key-12345")
    classifier = LangChainClassifier(settings, llm=_StubLLM("not valid json at all"))

    result = classifier.classify(sample_event)

    assert isinstance(result, ClassificationResult)
    assert result.severity in SEVERITY_LEVELS
    assert result.model.endswith("-fallback")


def test_langchain_classifier_parses_well_formed_json_response(sample_event):
    settings = Settings(openai_api_key="sk-fake-test-key-12345")
    payload = (
        '{"severity": "CRITICAL", "classification": "Database Latency", '
        '"confidence": 0.91, "recommended_action": "Page on-call DBA", '
        '"summary": "Queries are timing out against the primary database."}'
    )
    classifier = LangChainClassifier(settings, llm=_StubLLM(payload))

    result = classifier.classify(sample_event)

    assert result.severity == "CRITICAL"
    assert result.classification == "Database Latency"
    assert result.confidence == 0.91
    assert result.recommended_action == "Page on-call DBA"


class _StubLLM:
    """Minimal stand-in for a LangChain chat model's `.invoke()` interface."""

    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages):
        return _StubResponse(self._content)


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content
