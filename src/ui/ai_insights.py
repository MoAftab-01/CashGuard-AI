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


def render_ai_insights(bundle: DashboardBundle, currency: str, baseline_key: tuple, *, backend=None, payload=None) -> None:
    if backend is not None:
        return _render_backend_insights(bundle, currency, baseline_key, backend, payload)
    st.caption("Calculated evidence stays separate from optional AI-generated explanations. No paid API key is needed.")
    st.caption("Local requests contain computed summaries. Transaction descriptions, merchants, accounts and IDs are excluded.")
    saved = st.session_state.get("cashguard_ai_settings", {})
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
    st.caption(f"Selected model: {settings.model} · Inference restricted to local Ollama")
    check_clicked = st.button("Check local model connection", key="ai_check")
    status_key = (settings.base_url, settings.model)
    saved_status = st.session_state.get("cashguard_ollama_status")
    if check_clicked or saved_status is None or saved_status[0] != status_key or time.monotonic() - saved_status[1] > 30:
        with OllamaService(settings) as service:
            status = service.check_availability()  # Metadata only: never inference.
        st.session_state["cashguard_ollama_status"] = (status_key, time.monotonic(), status)
    else:
        status = saved_status[2]
    if status.ready:
        st.success(status.message)
    else:
        st.warning(status.message)
        st.info("Calculated financial summaries remain available below. AI-generated explanations require an available local model.")
    with st.expander("Set up Ollama and the selected model", expanded=not status.ready):
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
    if st.button("Generate AI Insights", key="generate_ai_insights", type="primary"):
        with st.spinner("Generating and validating local financial explanations…"):
            with OllamaService(settings) as service:
                report = generate_report(bundle, service, currency, scenario=scenario)
        st.session_state["cashguard_ai_report"] = (request_key, report)
        record = (request_key, report)
    if record is not None and record[1].source == "ai":
        report = record[1]
        st.subheader("AI-generated explanations")
        st.caption(report.message)
        st.caption("General budgeting guidance only. Review qualitative explanations; structural and numeric validation cannot prove every interpretation.")
        for name, title in SECTION_TITLES.items():
            section = getattr(report.insights, name)
            with st.container(border=True):
                st.subheader(title)
                if section.status == "insufficient_evidence":
                    st.caption("Insufficient evidence — no unsupported conclusion")
                st.write(section.explanation)
                st.caption("Calculated evidence")
                for evidence_id in section.evidence_ids:
                    fact = report.evidence[evidence_id]
                    st.write(f"{fact.label}: {fact.value}")
                    st.caption(fact.basis)
        with st.expander("Calculated financial summaries"):
            _calculated_summaries(bundle, currency, scenario)
    else:
        if record is not None:
            st.warning(record[1].message)
            st.caption("Deterministic fallback · No rejected model output is displayed.")
        else:
            st.caption("Click Generate AI Insights to request explanations. Inference never runs automatically on reruns.")
        _calculated_summaries(bundle, currency, scenario)
    if scenario is None:
        st.caption("Configure a scenario in Scenario Simulator to include its outcome here.")
    st.caption("Balances and forecasts are estimates; unusual transactions are not confirmed fraud. Suggestions are general, not investment or credit decisions.")
    warnings_panel(bundle.risk.warnings)


def _calculated_summaries(bundle, currency, scenario) -> None:
    st.subheader("Calculated financial summaries")
    for title, text in financial_summaries(bundle, currency, scenario=scenario):
        with st.container(border=True):
            st.subheader(title)
            st.write(text)


def _render_backend_insights(bundle, currency, baseline_key, backend, payload):
    st.caption("Explanations use the configured API backend. Financial calculations remain separate from model prose.")
    st.caption("Only minimized aggregate evidence reaches inference. No raw descriptions, merchants, accounts or transaction IDs are included.")
    model = st.text_input("Model", value=os.getenv("CASHGUARD_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL), key="api_ai_model",
                          help="Requested local Ollama model. The server controls the provider; changing this field cannot enable a disabled or hosted provider.")
    timeout = st.number_input("Inference timeout (seconds)", min_value=1, max_value=90, value=30, key="api_ai_timeout")
    previous = st.session_state.get("cashguard_latest_scenario")
    scenario = previous[1] if previous and previous[0] == baseline_key else None
    context = build_financial_context(bundle, currency, scenario=scenario)
    status_key = (backend.settings.api_url, model)
    saved = st.session_state.get("cashguard_api_model_status")
    if st.button("Check model availability", key="api_ai_check") or saved is None or saved[0] != status_key or time.monotonic() - saved[1] > 30:
        try:
            status = backend.model_status(model, int(timeout))
            saved = (status_key, time.monotonic(), status)
            st.session_state["cashguard_api_model_status"] = saved
        except ApiClientError as exc:
            st.warning(str(exc))
            saved = None
    if saved:
        (st.success if saved[2].ready else st.info)(saved[2].message)
        if saved[2].code == "hosted_unverified":
            st.warning("Hosted mode sends minimized aggregates to Hugging Face and DeepInfra. Public demo data is synthetic; provider processing is outside this computer.")
    key = (context.fingerprint(), backend.settings.api_url, model,
           (saved[2].model, saved[2].code) if saved else None, PROMPT_VERSION)
    record = st.session_state.get("cashguard_ai_report")
    if record and record[0] != key:
        st.session_state.pop("cashguard_ai_report", None)
        record = None
    disabled = bool(saved and saved[2].code == "disabled")
    if disabled:
        st.caption("Model generation is disabled by the backend configuration. Calculated summaries below remain available; a model name alone does not enable inference.")
    if st.button("Generate AI Insights", key="generate_ai_insights", type="primary", disabled=disabled):
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
    if record and record[1].source == "ai":
        st.subheader("AI-generated explanations")
        st.caption(f"Validated output from {record[1].model}")
        st.caption("Qualitative model output; financial evidence below comes from validated analytics.")
        for name, title in SECTION_TITLES.items():
            section = getattr(record[1].insights, name)
            with st.container(border=True):
                st.subheader(title)
                st.write(section.explanation)
                for evidence_id in section.evidence_ids:
                    fact = record[1].evidence[evidence_id]
                    st.write(f"{fact.label}: {fact.value}")
                    st.caption(fact.basis)
    elif record:
        st.info(record[1].message)
    else:
        st.caption("Inference runs only when requested. Calculated summaries remain available during service failures.")
    _calculated_summaries(bundle, currency, scenario)
    st.caption("Estimates and general budgeting guidance only. Unusual transactions are not confirmed fraud.")
