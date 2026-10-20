"""User-triggered local AI explanations with session-only, context-bound results."""

import os
import time

import streamlit as st

from config import DEFAULT_OLLAMA_MODEL
from src.dashboard_service import DashboardBundle, financial_summaries
from src.api_client import ApiClientError
from src.financial_context import ContextError, build_financial_context
from src.insight_prompts import SECTION_TITLES
from src.insight_workflow import generate_report
from src.llm_service import OllamaService, OllamaSettings
from src.ui.components import warnings_panel

PROMPT_VERSION = "grounded-local-v1"
QUESTIONS = {
    "financial_health": "How is my cash doing?",
    "cash_flow_risk": "Could I fall below my cash floor?",
    "spending_insights": "What are my income and expenses?",
    "scenario_interpretation": "How does my plan change things?",
}


def concise(text, limit=360):
    """Presentation excerpt only; full validated output is always available."""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _conversation(bundle, currency, scenario, report):
    topic = st.pills("Suggested questions", list(QUESTIONS), default="financial_health", required=True,
                     format_func=QUESTIONS.get, key="assistant_topic", persist_state="session", wrap=True)
    with st.chat_message("user", avatar=":material/person:"):
        st.write(QUESTIONS[topic])
    if report and report.source == "ai":
        st.header("AI-generated explanations")
        with st.chat_message("assistant", avatar=":material/insights:"):
            st.caption(f"Model-generated · {report.model} · Validated against calculated evidence")
            section = getattr(report.insights, topic)
            if section.status == "insufficient_evidence":
                st.caption("Insufficient evidence — no unsupported conclusion")
            st.write(concise(section.explanation))
            for identity in section.evidence_ids[:2]:
                fact = report.evidence[identity]
                st.write(f"{fact.label}: {fact.value}")
        with st.expander("Full explanations and calculated evidence"):
            st.caption("Validated qualitative output, not a guarantee or hidden model reasoning. Review the evidence and assumptions.")
            for name, title in SECTION_TITLES.items():
                section = getattr(report.insights, name)
                st.subheader(title)
                st.write(section.explanation)
                for identity in section.evidence_ids:
                    fact = report.evidence[identity]
                    st.write(f"{fact.label}: {fact.value}")
                    st.caption(fact.basis)
    else:
        if report:
            st.warning(report.message)
            st.caption("Deterministic fallback · No rejected model output is displayed.")
        st.header("Calculated financial summaries")
        facts = dict(financial_summaries(bundle, currency, scenario=scenario))
        group = {"financial_health": "Estimated cash position", "cash_flow_risk": "Minimum cash threshold",
                 "spending_insights": "Historical cash flow", "scenario_interpretation": "Scenario outcome"}[topic]
        with st.chat_message("assistant", avatar=":material/insights:"):
            st.caption("Calculated summary · No model-generated answer")
            st.write(facts.get(group, "Create a plan to compare a hypothetical change with your baseline. No scenario has been assumed."))
    _calculated_summaries(bundle, currency, scenario)
    st.caption("Changing a question never triggers inference. Use Generate AI Insights to request a model explanation. Estimates and general budgeting guidance only.")


def render_ai_insights(bundle: DashboardBundle, currency: str, baseline_key: tuple, *, backend=None, payload=None) -> None:
    if backend is not None:
        return _render_backend_insights(bundle, currency, baseline_key, backend, payload)
    st.caption("Private local mode · Only calculated aggregates reach Ollama; raw descriptions and account IDs stay out of prompts.")
    status_area, answer_area, action_area = st.container(), st.container(), st.container()
    saved = st.session_state.get("cashguard_ai_settings", {})
    with st.expander("Model settings") as model_controls:
        left, right = st.columns([2, 1])
        with left:
            model = st.text_input("Local model", value=saved.get("model", os.getenv("CASHGUARD_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)),
                                   key="ai_model", help="Default: gemma3:4b. The model must already be installed in local Ollama.")
        with right:
            try:
                default_timeout = int(float(os.getenv("CASHGUARD_OLLAMA_TIMEOUT", "90")))
            except (ValueError, OverflowError):
                default_timeout = 90
            timeout = st.number_input("Inference timeout (seconds)", min_value=10, max_value=180,
                                       value=saved.get("timeout", min(max(default_timeout, 10), 180)), step=10, key="ai_timeout")
    st.session_state["cashguard_ai_settings"] = {"model": model, "timeout": int(timeout)}
    previous = st.session_state.get("cashguard_latest_scenario")
    scenario = previous[1] if previous and previous[0] == baseline_key else None
    try:
        settings = OllamaSettings.from_environment(model=model, timeout_seconds=float(timeout))
        context = build_financial_context(bundle, currency, scenario=scenario)
    except (ValueError, ContextError):
        st.session_state.pop("cashguard_ai_report", None)
        st.error("Check local model settings and current analytics. Only a loopback Ollama endpoint and validated financial evidence are permitted.")
        _calculated_summaries(bundle, currency, scenario)
        return
    status_area.caption(f"Selected model: {settings.model} · Inference restricted to local Ollama")
    check_clicked = model_controls.button("Check local model connection", key="ai_check")
    status_key = (settings.base_url, settings.model)
    saved_status = st.session_state.get("cashguard_ollama_status")
    if check_clicked or saved_status is None or saved_status[0] != status_key or time.monotonic() - saved_status[1] > 30:
        with OllamaService(settings) as service:
            status = service.check_availability()  # Metadata only: never inference.
        st.session_state["cashguard_ollama_status"] = (status_key, time.monotonic(), status)
    else:
        status = saved_status[2]
    if status.ready:
        status_area.success(status.message)
    else:
        status_area.warning(status.message)
        status_area.caption("Calculated summaries remain available without a model.")
    with st.expander("Set up Ollama and the selected model"):
        st.markdown("Install [Ollama for your operating system](https://ollama.com/download), then open a new terminal.")
        st.code("ollama serve\nollama list", language="powershell")
        st.caption("The Windows Ollama application may already be serving the local endpoint; another server is not needed in that case.")
        st.code(f"ollama pull {settings.model}", language="powershell")
        st.warning("Model downloads can be several gigabytes. Run the pull command yourself only when you want the download. CashGuard never downloads models automatically.")
        st.caption("For a strictly offline Ollama server, set OLLAMA_NO_CLOUD=1 before restarting Ollama. Cloud-routed models are rejected by CashGuard.")
    request_key = (context.fingerprint(), settings.base_url, settings.model, PROMPT_VERSION)
    record = st.session_state.get("cashguard_ai_report")
    if record is not None and record[0] != request_key:
        st.session_state.pop("cashguard_ai_report", None)
        record = None
        st.info("Financial inputs, scenario or model changed. Generate new explanations for the current context.")
    if action_area.button("Generate AI Insights", key="generate_ai_insights", type="primary"):
        with st.spinner("Generating and validating local financial explanations…"):
            with OllamaService(settings) as service:
                report = generate_report(bundle, service, currency, scenario=scenario)
        st.session_state["cashguard_ai_report"] = (request_key, report)
        record = (request_key, report)
    with answer_area:
        _conversation(bundle, currency, scenario, record[1] if record else None)
    if scenario is None:
        st.caption("Configure a scenario in Scenario Simulator to include its outcome here.")
    st.caption("Balances and forecasts are estimates; unusual transactions are not confirmed fraud. Suggestions are general, not investment or credit decisions.")
    warnings_panel(bundle.risk.warnings)


def _calculated_summaries(bundle, currency, scenario) -> None:
    with st.expander("All calculated evidence"):
        st.header("Calculated financial summaries")
        for title, text in financial_summaries(bundle, currency, scenario=scenario):
            with st.container(border=True):
                st.subheader(title)
                st.write(text)


def _render_backend_insights(bundle, currency, baseline_key, backend, payload):
    st.caption("Only calculated aggregates reach inference. The configured provider and its privacy boundary are shown below.")
    status_area, answer_area, action_area = st.container(), st.container(), st.container()
    with st.expander("Model settings") as model_controls:
        model = st.text_input("Model", value=os.getenv("CASHGUARD_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL), key="api_ai_model",
                              help="Requested local Ollama model. The server controls the provider; changing this field cannot enable a disabled or hosted provider.")
        timeout = st.number_input("Inference timeout (seconds)", min_value=1, max_value=90, value=30, key="api_ai_timeout")
    previous = st.session_state.get("cashguard_latest_scenario")
    scenario = previous[1] if previous and previous[0] == baseline_key else None
    context = build_financial_context(bundle, currency, scenario=scenario)
    status_key = (backend.settings.api_url, model)
    saved = st.session_state.get("cashguard_api_model_status")
    if model_controls.button("Check model availability", key="api_ai_check") or saved is None or saved[0] != status_key or time.monotonic() - saved[1] > 30:
        try:
            status = backend.model_status(model, int(timeout))
            saved = (status_key, time.monotonic(), status)
            st.session_state["cashguard_api_model_status"] = saved
        except ApiClientError as exc:
            st.warning(str(exc))
            saved = None
    if saved:
        (status_area.success if saved[2].ready else status_area.info)(saved[2].message)
        if saved[2].code == "hosted_unverified":
            status_area.warning("Hosted mode sends minimized aggregates to Hugging Face and DeepInfra. Public demo data is synthetic; provider processing is outside this computer.")
    key = (context.fingerprint(), backend.settings.api_url, model,
           (saved[2].model, saved[2].code) if saved else None, PROMPT_VERSION)
    record = st.session_state.get("cashguard_ai_report")
    if record and record[0] != key:
        st.session_state.pop("cashguard_ai_report", None)
        record = None
    disabled = bool(saved and saved[2].code == "disabled")
    if disabled:
        model_controls.caption("Model generation is disabled by the backend configuration. Calculated summaries remain available; a model name alone does not enable inference.")
    if action_area.button("Generate AI Insights", key="generate_ai_insights", type="primary", disabled=disabled):
        try:
            with st.spinner("Requesting and validating explanations…"):
                report = backend.insights(payload, model, int(timeout), scenario=scenario)
                if report.context_fingerprint != context.fingerprint():
                    raise ApiClientError("invalid_response")
            record = (key, report)
            st.session_state["cashguard_ai_report"] = record
        except ApiClientError as exc:
            st.session_state.pop("cashguard_ai_report", None)
            record = None
            st.warning(str(exc))
    with answer_area:
        _conversation(bundle, currency, scenario, record[1] if record else None)
    st.caption("Estimates and general budgeting guidance only. Unusual transactions are not confirmed fraud.")
