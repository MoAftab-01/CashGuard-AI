"""Theme-aware Plotly figures; finance stays in the analytics engines."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure

from src.forecasting import ForecastResult
from src.metrics import balance_history, category_expenses, monthly_summary
from src.risk_engine import RiskResult

COLORS = {"income": "#0D9488", "expenses": "#D97706"}


def style_figure(figure: Figure, currency: str | None = None) -> Figure:
    """Transparent surfaces and inherited text let Streamlit supply light/dark colors."""
    figure.update_layout(template=None, paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=12, r=12, t=64, b=72),
                         font=dict(family="sans-serif", size=13), hovermode="closest",
                         title=dict(automargin=True, x=0, xref="container", y=1,
                                    yanchor="top", pad=dict(t=24, l=4)),
                         legend=dict(orientation="h", yanchor="top", y=-.25, x=0),
                         legend_title_text="", height=360)
    figure.update_xaxes(showgrid=False, zeroline=False)
    figure.update_yaxes(gridcolor="rgba(128,128,128,0.16)", zerolinecolor="rgba(128,128,128,0.35)")
    if currency:
        figure.update_yaxes(title_text=currency, tickformat=",.2f")
    return figure


def monthly_comparison(data: pd.DataFrame) -> Figure:
    frame = monthly_summary(data)
    figure = px.bar(frame, x="month", y=["income", "expenses"], barmode="group",
                    color_discrete_map=COLORS, title="Monthly income and expenses",
                    labels={"value": "Amount", "month": "Month", "variable": "Flow"})
    figure.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=50, b=10))
    return style_figure(figure)


def spending_distribution(data: pd.DataFrame) -> Figure:
    expenses = category_expenses(data)
    figure = px.bar(expenses, x="expenses", y="category", orientation="h",
                  title="Spending by category", color_discrete_sequence=["#0D9488"],
                  labels={"expenses": "Expenses", "category": "Category"})
    figure.update_yaxes(categoryorder="total ascending")
    if not len(figure.data) or expenses.empty:
        figure.add_annotation(text="No expenses in this period", x=0.5, y=0.5,
                              xref="paper", yref="paper", showarrow=False)
    return style_figure(figure)


def historical_balances(data: pd.DataFrame, opening_balance: str) -> Figure:
    figure = px.line(balance_history(data, opening_balance), x="date", y="estimated_balance",
                   title="Estimated balance history", color_discrete_sequence=["#0D9488"],
                   labels={"estimated_balance": "Estimated balance", "date": "Date"},
                   markers=True)
    return style_figure(figure)


def forecast_comparison(history: pd.DataFrame, baseline: ForecastResult, *,
                        scenario: ForecastResult | None = None, currency: str = "USD") -> Figure:
    """Show observed balance estimates and anchored future projections without gaps."""
    figure = go.Figure()
    if not history.empty:
        figure.add_trace(go.Scatter(x=history["date"], y=history["estimated_balance"],
                                   mode="lines", name="Historical estimate",
                                   line=dict(color="#64748B", width=2)))
    for forecast, label, color, dash in ((baseline, "Baseline projection", "#0D9488", "dash"),
                                         (scenario, "Scenario projection", "#A78BFA", "solid")):
        if forecast is None:
            continue
        dates = [forecast.as_of, *forecast.daily["date"].tolist()]
        balances = [forecast.current_balance_cents / 100, *(int(value) / 100 for value in forecast.daily["balance_cents"])]
        figure.add_trace(go.Scatter(x=dates, y=balances, mode="lines", name=label,
                                   line=dict(color=color, width=3, dash=dash),
                                   hovertemplate="%{x}<br>%{y:,.2f}<extra>%{fullData.name}</extra>"))
    figure.add_hline(y=baseline.cash_threshold_cents / 100, line_dash="dot", line_color="#D97706",
                     annotation_text="Minimum cash threshold", annotation_position="bottom right")
    figure.update_layout(title="Estimated cash balance", hovermode="x unified")
    style_figure(figure, currency)
    figure.update_layout(hovermode="x unified", height=420)
    return figure


def anomaly_timeline(data: pd.DataFrame, currency: str = "USD") -> Figure:
    frame = data.copy()
    frame["display_amount"] = frame["amount_cents"].map(lambda value: int(value) / 100)
    frame["review_status"] = ["Not scored" if pd.isna(flag) else "Unusual" if flag else "Not flagged"
                              for flag in frame["is_anomaly"]]
    figure = px.scatter(frame, x="date", y="display_amount", color="review_status",
                        color_discrete_map={"Unusual": "#D97706", "Not flagged": "#0D9488", "Not scored": "#94A3B8"},
                        hover_data={"description": True, "category": True, "anomaly_score": ":.4f", "display_amount": ":.2f"},
                        labels={"display_amount": currency, "date": "Date", "review_status": "Status"},
                        title="Transaction review timeline")
    figure.update_traces(marker=dict(size=8, opacity=0.85))
    return style_figure(figure, currency)


def risk_contributions(risk: RiskResult) -> Figure:
    frame = pd.DataFrame({"factor": [item.name.replace("_", " ").title() for item in risk.factors],
                          "points": [item.points for item in risk.factors],
                          "maximum": [item.max_points for item in risk.factors]})
    figure = px.bar(frame, x="points", y="factor", orientation="h", custom_data=["maximum"],
                    color_discrete_sequence=["#0D9488"], title="Contributions to the risk indicator",
                    labels={"points": "Points", "factor": "Factor"})
    figure.update_traces(hovertemplate="%{y}<br>%{x} of %{customdata[0]} available points<extra></extra>")
    figure.update_xaxes(range=[0, max(item.max_points for item in risk.factors)])
    return style_figure(figure)


def forecast_evaluation_chart(metrics: pd.DataFrame, *, target="balance", metric="mae") -> Figure:
    frame = metrics.loc[(metrics["target"] == target) & metrics[metric].notna()]
    figure = px.bar(frame, x="horizon_days", y=metric, color="method", barmode="group",
                    color_discrete_sequence=["#0D9488", "#94A3B8"],
                    labels={"horizon_days": "Forecast horizon (days)", metric: f"{metric.upper()} (currency units)"},
                    title=f"Rolling-origin {target} {metric.upper()}")
    figure.update_xaxes(tickmode="array", tickvals=sorted(frame["horizon_days"].unique().tolist()))
    return style_figure(figure)


def anomaly_confusion_chart(metrics: dict) -> Figure:
    figure = go.Figure(go.Heatmap(z=metrics["confusion_matrix"],
                                  x=["Not flagged", "Flagged unusual"], y=["Background", "Injected expense"],
                                  text=metrics["confusion_matrix"], texttemplate="%{text}",
                                  colorscale=[[0, "#E2E8F0"], [1, "#0F766E"]], showscale=False,
                                  hovertemplate="Actual: %{y}<br>Predicted: %{x}<br>Count: %{z}<extra></extra>"))
    figure.update_layout(title="Synthetic confusion matrix", xaxis_title="Prediction", yaxis_title="Known injection label")
    return style_figure(figure)


def anomaly_score_chart(scored: pd.DataFrame, threshold: float) -> Figure:
    figure = go.Figure()
    for injected, label, color in ((False, "Background", "#0D9488"), (True, "Injected expense", "#D97706")):
        figure.add_trace(go.Histogram(x=scored.loc[scored["is_injected"] == injected, "anomaly_score"],
                                      name=label, marker_color=color, opacity=.7, nbinsx=25))
    figure.add_vline(x=threshold, line_dash="dot", line_color="#A78BFA", annotation_text="Decision threshold")
    figure.update_layout(title="Synthetic score distribution", xaxis_title="Unusualness score (not probability)",
                         yaxis_title="Transactions", barmode="overlay")
    return style_figure(figure)
