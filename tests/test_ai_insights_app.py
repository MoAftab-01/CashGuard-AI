from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from src.insight_prompts import StructuredInsights
from src.llm_service import LocalLLMError, MESSAGES, OllamaStatus

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def fake_local_model(monkeypatch, valid_ai_payload):
    state = SimpleNamespace(checks=0, generations=0, ready=True, failure=None, unsafe=False)
    class FakeService:
        def __init__(self, settings):
            self.settings = settings
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def check_availability(self):
            state.checks += 1
            return OllamaStatus(state.ready, "ready" if state.ready else "model_missing",
                                "Local model available" if state.ready else MESSAGES["model_missing"], self.settings.model)
        def generate(self, context):
            state.generations += 1
            if state.failure:
                raise LocalLLMError(state.failure)
            payload = deepcopy(valid_ai_payload)
            if context.scenario is not None:
                payload["scenario_interpretation"] = {
                    "explanation": "The configured scenario is hypothetical; review its projected balance against the baseline.",
                    "evidence_ids": ["scenario_change"], "status": "supported"}
            if state.unsafe:
                payload["financial_health"]["explanation"] = "PRIVATE_CANARY fabricated balance 999999999."
            return StructuredInsights.model_validate(payload)
    monkeypatch.setattr("src.ui.ai_insights.OllamaService", FakeService)
    return state


def insights_page():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="data_source").set_value("Upload CSV").run()
    raw = b"date,description,amount,category\n2026-01-01,Income,100,Income\n2026-01-02,Expense,-20,Other\n"
    app.file_uploader[0].set_value(("fixture.csv", raw, "text/csv")).run()
    app.sidebar.text_input(key="opening_balance").set_value("100.00").run()
    app.sidebar.radio(key="navigation").set_value("AI Insights").run()
    return app


def test_inference_requires_a_button_click_and_is_not_repeated_on_reruns(fake_local_model):
    app = insights_page()
    assert not app.exception and fake_local_model.generations == 0
    app.button(key="generate_ai_insights").click().run()
    assert not app.exception and fake_local_model.generations == 1
    assert any(item.value == "AI-generated explanations" for item in app.subheader)
    app.run()
    assert not app.exception and fake_local_model.generations == 1
    assert fake_local_model.checks == 1


def test_financial_changes_invalidate_ai_text_without_automatic_regeneration(fake_local_model):
    app = insights_page()
    app.button(key="generate_ai_insights").click().run()
    app.sidebar.text_input(key="opening_balance").set_value("200.00").run()
    assert not app.exception and fake_local_model.generations == 1
    assert not any(item.value == "AI-generated explanations" for item in app.subheader)
    assert any("changed" in item.value.lower() for item in app.info)
    assert "cashguard_ai_report" not in app.session_state


def test_model_change_invalidates_previous_explanation(fake_local_model):
    app = insights_page()
    app.button(key="generate_ai_insights").click().run()
    app.text_input(key="ai_model").set_value("qwen2.5:3b").run()
    assert not app.exception and fake_local_model.generations == 1
    assert not any(item.value == "AI-generated explanations" for item in app.subheader)
    assert fake_local_model.checks == 2


@pytest.mark.parametrize("failure", ["model_missing", "timeout", "connection_error", "invalid_response"])
def test_unavailable_or_failed_model_keeps_deterministic_financial_summaries(fake_local_model, failure):
    fake_local_model.ready = False
    fake_local_model.failure = failure
    app = insights_page()
    app.button(key="generate_ai_insights").click().run()
    assert not app.exception
    assert any(item.value == "Calculated financial summaries" for item in app.subheader)
    assert not any(item.value == "AI-generated explanations" for item in app.subheader)
    assert any(MESSAGES[failure] in item.value for item in app.warning)


def test_unsupported_model_claim_is_never_rendered(fake_local_model):
    fake_local_model.unsafe = True
    app = insights_page()
    app.button(key="generate_ai_insights").click().run()
    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "PRIVATE_CANARY" not in rendered and "999999999" not in rendered
    assert not any(item.value == "AI-generated explanations" for item in app.subheader)


def test_connection_refresh_and_invalid_endpoint_never_infer(fake_local_model, monkeypatch):
    app = insights_page()
    app.button(key="ai_check").click().run()
    assert fake_local_model.checks == 2 and fake_local_model.generations == 0
    monkeypatch.setenv("CASHGUARD_OLLAMA_URL", "https://external.invalid/private-secret")
    app.run()
    assert not app.exception and fake_local_model.generations == 0
    assert any("loopback" in item.value for item in app.error)
    assert not any("private-secret" in item.value for item in app.error)
