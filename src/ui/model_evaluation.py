"""Optional, explicit evaluation. Uploaded histories stay in private session state."""

import streamlit as st
import pandas as pd

from src.dashboard_service import session_value
from src.evaluation import evaluate_anomalies, evaluate_forecasts
from src.evaluation_data import anomaly_benchmark
from src.anomaly_experiments import run_candidate_benchmark
from src.metrics import money_to_cents
from src.ui.components import chart, warnings_panel
from src.visualizations import anomaly_confusion_chart, anomaly_score_chart, forecast_evaluation_chart


def render_model_evaluation(imported, opening, as_of, irregular, dataset_key, source):
    st.info("Evaluation runs only on request. Synthetic results demonstrate behavior on fictional data and do not establish real-world accuracy.")
    st.subheader("Forecast backtest | selected history")
    st.caption(f"Source: {source}. Expanding rolling origins, at least 90 training days, 30-day origin spacing, "
               "7/14/30-day complete horizons. Missing calendar days are assumed to have zero flows. "
               "Last-balance baseline predicts zero daily net flow. Both methods share all origins and dates within each horizon.")
    try:
        opening_cents = money_to_cents(opening)
    except ValueError:
        opening_cents = None
        st.warning("Enter a valid opening balance to evaluate reconstructed balances. Synthetic anomaly evaluation remains available below.")
    key = (dataset_key, as_of, opening_cents, irregular)
    if st.button("Run forecast evaluation", key="run_forecast_evaluation", disabled=opening_cents is None):
        with st.spinner("Evaluating chronological forecast origins..."):
            session_value(st.session_state, "forecast_evaluation", key,
                          lambda: evaluate_forecasts(imported.data, opening, as_of=as_of, include_irregular_income=irregular))
    cached = st.session_state.get("cashguard_private_cache", {}).get("forecast_evaluation")
    if cached and cached[0] == key:
        result = cached[1]
        st.dataframe(result.metrics, hide_index=True, width="stretch")
        st.caption("Errors are in the selected currency's units, with no conversion. Bias = mean(predicted - actual); "
                   "positive means overprediction. Net is daily signed flow; balance is reconstructed end-of-day cash. "
                   "Counts pool all lead days per origin; different horizons can have different eligible origins.")
        if result.predictions.empty:
            st.warning("Insufficient history for a complete backtest fold. No performance scores are available.")
        else:
            left, right = st.columns(2)
            target = left.selectbox("Evaluation target", ["balance", "net"], key="evaluation_target")
            metric = right.selectbox("Error metric", ["mae", "rmse", "bias"], key="evaluation_metric")
            chart(forecast_evaluation_chart(result.metrics, target=target, metric=metric), "evaluation_forecasts")
            with st.expander("Fold dates and training sample counts"):
                st.dataframe(result.folds, hide_index=True, width="stretch")
        warnings_panel(result.warnings, "Backtest assumptions")
    else:
        st.caption("No backtest has been run for these inputs. Changing history, cutoff, opening balance or income assumptions invalidates prior results.")
    st.divider()
    st.subheader("Legacy Isolation Forest | historical synthetic benchmark")
    st.caption("Separate benchmark, independent of uploads: seed 42, 480 training transactions over 120 days; "
               "240 test transactions over the following 60 days. Twelve grocery expenses are multiplied by twelve. "
               "Labels remain separate until scoring. No holdout tuning; the legacy auto threshold is score > 0.5. This is not the default calibrated review policy.")
    benchmark_key = ("synthetic-injection-v1", 42)
    if st.button("Run synthetic anomaly evaluation", key="run_anomaly_evaluation"):
        with st.spinner("Scoring a chronological synthetic holdout..."):
            def compute():
                benchmark = anomaly_benchmark()
                return evaluate_anomalies(benchmark.train, benchmark.test, benchmark.labels)
            session_value(st.session_state, "anomaly_evaluation", benchmark_key, compute)
    cached = st.session_state.get("cashguard_private_cache", {}).get("anomaly_evaluation")
    if cached and cached[0] == benchmark_key:
        result = cached[1]
        if result.metrics:
            for column, name in zip(st.columns(4), ("precision", "recall", "f1", "false_positive_rate")):
                value = result.metrics[name]
                column.metric(name.replace("_", " ").title(), f"{value:.3f}" if value is not None else "Unavailable")
            st.write(f"Test rows: {result.metrics['test_rows']} | Injected: {result.metrics['injected_count']} | "
                     f"Predicted unusual: {result.metrics['predicted_unusual']}")
            fpr = result.metrics["false_positive_rate"]
            if fpr is not None and fpr > .1:
                st.warning("This threshold flags many background transactions in this benchmark. Review precision and false positives "
                           "alongside recall. Independent calibration and a new holdout are needed before changing the operating threshold.")
            chart(anomaly_confusion_chart(result.metrics), "evaluation_confusion")
            chart(anomaly_score_chart(result.scored, result.metadata["score_threshold"]), "evaluation_scores")
            with st.expander("Split, threshold and false-positive review"):
                st.json(result.metadata)
                negatives = result.scored.loc[~result.scored["is_injected"]]
                grouped = negatives.groupby("category")["is_anomaly"].agg(["count", "sum", "mean"])
                st.dataframe(grouped.rename(columns={"count": "Background rows", "sum": "False positives", "mean": "False-positive rate"}), width="stretch")
        warnings_panel(result.warnings, "Synthetic evaluation limitations")
    _render_candidate_evaluation()


def render_public_evaluation():
    """Read-only public synthetic evidence; do not run user-controlled backtests."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "reports/phase6/results.json"
    st.subheader("Recorded synthetic model evaluation")
    st.caption("Read-only benchmark. Synthetic injected amount changes are not real-world fraud labels. The known holdout has been replayed; it is not a fresh independent validation.")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        results = report["final_metrics"]
        selected = next(row for row in results if row["selected"])
    except (OSError, ValueError, KeyError, StopIteration):
        st.info("The recorded evaluation artifact is unavailable. No performance numbers are invented.")
        return
    for column, name in zip(st.columns(3), ("precision", "recall", "f1")):
        column.metric(name.title(), f"{selected[name]:.4f}")
    st.write(f"Selected method: {selected['method']}. Final partition: {selected['test_rows']} synthetic examples.")
    st.dataframe(pd.DataFrame([{name: row[name] for name in ("method", "precision", "recall", "f1", "false_positive_rate")}
                               for row in results]), hide_index=True, width="stretch")
    chart(anomaly_confusion_chart(selected), "public_evaluation_confusion")
    st.caption("Local mode retains interactive evaluations. Public mode shows fixed reproducible evidence to bound compute and prevent private uploads.")


def _render_candidate_evaluation():
    st.divider()
    st.subheader("Phase 6 | calibrated candidate comparison")
    st.caption("Separate chronological synthetic train/calibration/final partitions, 120/60/60 days. "
               "Candidate family and thresholds are selected on calibration before final scoring. "
               "Final labels describe injected amount changes, not fraud. The historical Phase 5 benchmark above uses different examples.")
    key = ("phase6-chronological-v1",)
    if st.button("Run calibrated candidate comparison", key="run_candidate_comparison"):
        with st.spinner("Selecting on calibration, then scoring the separate final holdout..."):
            session_value(st.session_state, "candidate_evaluation", key, run_candidate_benchmark)
    cached = st.session_state.get("cashguard_private_cache", {}).get("candidate_evaluation")
    if not cached or cached[0] != key:
        return
    selection, metrics, predictions = cached[1]
    st.write(f"Selected on calibration: {selection.method}. Frozen threshold: {selection.threshold:.4f}.")
    st.caption(f"Selection fingerprint: {selection.fingerprint}. Final scores do not alter this selection. "
               "Live review uses the selected family with prior unlabeled calibration, so its threshold and results can differ.")
    st.dataframe(metrics.drop(columns=["confusion_matrix"]), hide_index=True, width="stretch")
    with st.expander("Calibration selection evidence; these are not test estimates"):
        st.dataframe(selection.calibration_metrics.drop(columns=["confusion_matrix"]), hide_index=True, width="stretch")
    method = st.selectbox("Candidate confusion matrix", metrics["method"].tolist(),
                           index=metrics["method"].tolist().index(selection.method), key="candidate_chart_method")
    row = metrics.loc[metrics["method"] == method].iloc[0].to_dict()
    chart(anomaly_confusion_chart(row), "candidate_confusion")
    scored = predictions.loc[predictions["method"] == method]
    chart(anomaly_score_chart(scored, row["threshold"]), "candidate_scores")
    st.warning("A small synthetic holdout cannot establish real-world accuracy. Amount-only methods miss weekday-only anomalies; "
               "zero observed false positives does not imply a zero population false-positive rate. No final-test tuning was performed.")
