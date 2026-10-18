from types import SimpleNamespace
from dataclasses import replace

import pytest

from src.insight_prompts import StructuredInsights
from src.insight_workflow import deterministic_fallback, generate_report
from src.llm_service import LocalLLMError


class StubService:
    settings = SimpleNamespace(model="gemma3:4b")
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("code", ["connection_error", "timeout", "model_missing", "invalid_response"])
def test_failures_produce_deterministic_fallback_without_fake_ai(demo_dashboard, code):
    first = generate_report(demo_dashboard[1], StubService(LocalLLMError(code)))
    second = generate_report(demo_dashboard[1], StubService(LocalLLMError(code)))
    assert first == second
    assert first.source == "deterministic" and first.insights is None
    assert first.error_code == code
    assert "USD 16,268.23" in str(first.fallback)


def test_validated_ai_report_contains_only_typed_output_and_evidence(demo_dashboard, valid_ai_payload):
    report = generate_report(demo_dashboard[1], StubService(StructuredInsights.model_validate(valid_ai_payload)))
    assert report.source == "ai" and report.error_code is None
    assert report.evidence["estimated_balance"].value == "USD 16,268.23"
    assert not hasattr(report, "messages") and not hasattr(report, "prompt")


def test_workflow_rechecks_even_mocked_or_replaced_service_output(demo_dashboard, valid_ai_payload):
    valid_ai_payload["financial_health"]["explanation"] = "Your balance is 999999999."
    report = generate_report(demo_dashboard[1], StubService(StructuredInsights.model_validate(valid_ai_payload)))
    assert report.source == "deterministic" and report.insights is None
    assert "999999999" not in str(report)


def test_fallback_handles_missing_metrics(financial_context):
    context = financial_context.model_copy(update={"historical_income_cents": None})
    fallback = deterministic_fallback(context)
    assert "Historical Income: unavailable" in str(fallback)
    assert "USD 0.00" not in str(fallback)


def test_invalid_context_never_calls_the_model(demo_dashboard):
    bundle = demo_dashboard[1]
    service = StubService(None)
    report = generate_report(replace(bundle, risk=replace(bundle.risk, score=99)), service)
    assert service.calls == 0 and report.error_code == "invalid_context"
    assert report.source == "deterministic" and not report.evidence
