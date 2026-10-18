"""UI-independent generation/fallback workflow; no prompt persistence or global cache."""

from dataclasses import dataclass

from src.dashboard_service import DashboardBundle
from src.financial_context import ContextError, EvidenceFact, FinancialContext, build_financial_context, evidence_catalog
from src.insight_prompts import OutputValidationError, StructuredInsights, validate_insights
from src.llm_service import LocalLLMError, OllamaService
from src.scenario_simulator import ScenarioResult


@dataclass(frozen=True)
class InsightReport:
    source: str
    model: str
    context_fingerprint: str
    insights: StructuredInsights | None
    evidence: dict[str, EvidenceFact]
    fallback: tuple[tuple[str, str], ...]
    message: str
    error_code: str | None


def generate_report(bundle: DashboardBundle, service: OllamaService, currency: str = "USD", *,
                     scenario: ScenarioResult | None = None) -> InsightReport:
    """Only validated explanations become AI reports; failures keep computed summaries."""
    try:
        context = build_financial_context(bundle, currency, scenario=scenario)
    except ContextError:
        return InsightReport("deterministic", service.settings.model, "", None, {},
                             (("Financial evidence unavailable", "Recalculate analytics before requesting an explanation; no missing amounts have been estimated."),),
                             "Financial context could not be validated. Recalculate analytics before generating insights.", "invalid_context")
    fallback = deterministic_fallback(context)
    try:
        generated = service.generate(context)
        validated = validate_insights(generated.model_dump_json(), context)
        return InsightReport("ai", service.settings.model, context.fingerprint(), validated,
                             evidence_catalog(context), fallback,
                             "AI-generated qualitative explanations. Calculated evidence is rendered directly from the analytics engines.", None)
    except (LocalLLMError, OutputValidationError) as exc:
        message = str(exc) if isinstance(exc, LocalLLMError) else "The response failed grounding checks. Calculated summaries remain available."
        code = exc.code if isinstance(exc, LocalLLMError) else "invalid_response"
        return InsightReport("deterministic", service.settings.model, context.fingerprint(), None,
                             evidence_catalog(context), fallback, message, code)


def deterministic_fallback(context: FinancialContext) -> tuple[tuple[str, str], ...]:
    """Fixed evidence labels/values only; never replace missing information with zero."""
    facts = evidence_catalog(context)
    groups = [
        ("Historical cash flow", ("historical_income", "historical_expenses", "historical_net")),
        ("Estimated cash position", ("estimated_balance", "analysis_date")),
        ("30-day projection", ("forecast_closing", "forecast_minimum", "threshold_breaches")),
        ("Unusual activity", ("anomaly_unusual", "anomaly_scored", "anomaly_unscored")),
        ("Financial risk indicator", ("risk_indicator", "risk_score", "data_sufficiency")),
    ]
    if context.scenario:
        groups.append(("Scenario outcome", ("scenario_change", "scenario_minimum", "scenario_breaches")))
    return tuple((title, "; ".join(f"{facts[key].label}: {facts[key].value} ({facts[key].basis})" if key in facts
                                  else f"{key.replace('_', ' ').title()}: unavailable" for key in keys))
                 for title, keys in groups)
