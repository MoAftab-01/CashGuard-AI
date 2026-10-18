# Phase 2 analytics: contracts, assumptions and validation

The original import, metrics and visualization modules are reused. Phase 2 adds core
Python analytics, tests and a local sample runner. At the completion of Phase 2,
Streamlit still had its Phase 1 interface. The subsequent dashboard integration is
documented in the [Phase 3 guide](phase3_dashboard.md), local Ollama integration in
the [Phase 4 guide](phase4_local_ai.md), and current evaluation in the
[Phase 5 report](phase5_evaluation.md). Results below are the historical Phase 2 record.

## API example

```python
from datetime import timedelta

from config import SAMPLE_DATA_PATH
from src.data_processing import validate_csv
from src.forecasting import forecast_cash_flow, rolling_backtest
from src.anomaly_detection import detect_anomalies
from src.risk_engine import assess_risk
from src.scenario_simulator import ScenarioConfig, simulate_scenario

imported = validate_csv(SAMPLE_DATA_PATH)
if imported.has_errors:
    raise ValueError("Correct the import before running analytics")

baseline = forecast_cash_flow(
    imported.data, opening_balance="2500.00", horizon_days=30,
    cash_threshold="500.00",  # as_of=date(2026, 6, 30) is optional
)
unusual = detect_anomalies(imported.data, as_of=baseline.as_of)
risk = assess_risk(imported.data, baseline, anomalies=unusual)
scenario = simulate_scenario(baseline, ScenarioConfig(
    income_decrease_pct=20,
    expense_increase_pct=10,
    emergency_expense="500.00",
    emergency_date=baseline.as_of + timedelta(days=1),
))
evaluation = rolling_backtest(imported.data, "2500.00", as_of=baseline.as_of)

print(baseline.daily)
print(baseline.shortage_dates)
print(risk.factors)
print(scenario.closing_balance_change_cents)
print(evaluation.metrics)
```

Inputs are successfully imported transaction DataFrames, not valid-row previews from
failed imports. Shared checks reject missing analytic columns, non-calendar dates,
invalid text and noninteger or unbounded cents. They copy and sort the input, filter
through the inclusive cutoff, then validate amounts in the retained rows. Required
columns are `date`, `description`, `category`, `amount_cents`; optional account and
merchant fields refine recurring-payment groups.

When omitted, `as_of` is the latest transaction date, never the machine clock. An empty
history requires an explicit `datetime.date` cutoff. All APIs leave supplied history
unchanged. Core currency fields use **integer cents**, with exact round-half-up
allocation where estimates require fractional cents. Use `Decimal(cents) / 100` to
format units. NumPy floating point is used for model features, risk ratios and errors,
not ledger arithmetic. A single currency with two decimal minor units is assumed.

## Forecasting and recurring payments

`forecast_cash_flow(data, opening_balance, *, as_of=None, horizon_days=30,
cash_threshold=0, lookback_days=180, include_irregular_income=False)` returns a
`ForecastResult` with:

- Inclusive cutoff, horizon, estimated current balance and threshold in cents.
- Estimation-window row/day counts, recurring patterns, assumptions and warnings.
- An event ledger with stable IDs, dates, signed cents, kinds and descriptions.
- A daily DataFrame: `date`, `inflow_cents`, `outflow_cents`, `net_cents`,
  `balance_cents`, `below_threshold`.
- `shortage_dates`, meaning projected balance **strictly below** the supplied
  threshold. This can include a positive balance if the threshold is positive.

Opening balance belongs immediately before the earliest imported transaction.
Current balance uses **all transactions through the cutoff**, even those outside
the estimation lookback. Future dates begin the day after the cutoff. Horizon must
be an integer from 1 through 365; lookback is 1 through 3660 days.

Recurring detection groups account, description, merchant, category and flow direction.
It requires at least three distinct transaction dates, no duplicate dates within a
group, and either consecutive calendar months or intervals consistently within one
day of 7 or 14 days. Every amount must be within 35% of the group's median. The
projected signed amount is that median rounded to cents. Groups with a missed expected
payment by the cutoff are no longer treated as active recurring schedules.

Monthly schedules use the largest observed day-of-month, clamped to each month's
last date; January 31 → February 28 → March 31 does not drift to March 28. Small
monthly timing variation (two days from the clamped anchor) is tolerated. Weekly
and biweekly schedules advance from the latest observed date.

Recognized recurring rows are removed before averaging residual spending, preventing
double counting. Residual expense total is divided by **calendar days**, from the
first transaction in the estimation window through the cutoff, including zero-flow
days. Cumulative expected cents are rounded half up and differenced into daily
amounts, avoiding systematic fractional-cent drift. This spreads occasional repairs
into a historical expected spending rate; it does not predict a specific repair date.

Irregular income is excluded by default. Opting into `include_irregular_income=True`
averages it over the same calendar-day denominator; this is an explicitly uncertain
baseline, not a scheduled client payment. Sparse history still returns a deterministic
baseline with warnings. No history returns a constant opening balance. Exports with
no records in the last seven days receive a staleness warning.

Limitations: three observations can establish a spurious pattern; changing descriptions
can hide a real one. Missing months, irregular amounts and cancelled schedules are
treated conservatively. No inflation, seasonal effects, predictive intervals or bank
balance verification are modeled. Missing records cannot be distinguished from genuine
zero-activity days. Estimates are not guaranteed outcomes.

## Rolling historical evaluation

`rolling_backtest(data, opening_balance=0, *, as_of=None, horizon_days=30,
min_history_days=90, step_days=30, lookback_days=180,
include_irregular_income=False)` returns per-origin/per-day predictions, fold metadata,
metrics and warnings. Only **complete observed horizons** are eligible.

For every fold, forecast fitting and balance reconstruction see rows through its
origin only. Held-out rows supply actual daily net cash flows and reconstructed
balances afterward. Later observations cannot contribute recurring patterns, residual
rates or training balances. Days without rows are zero flow, assuming the export is
complete. The first eligible origin is the 90th calendar day by default.

Metrics are pooled across `(forecast origin, target date)` pairs in currency units:

- `net_mae`, `net_rmse`: error in predicted daily signed net cash flow.
- `balance_mae`, `balance_rmse`: error in predicted end-of-day reconstructed balance.

MAE is mean absolute error; RMSE is the square root of mean squared error. If step
is shorter than horizon, horizons overlap and dates can be scored under multiple
origins; a warning explains the weighting. Without eligible folds, metrics are `None`,
not zero or invented accuracy. Backtests do not tune on held-out outcomes.

## Isolation Forest anomaly detection

`AnomalyDetector` supports independent `fit(history, as_of=...)` and `score(later_rows)`.
Training requires at least 30 transactions over 30 calendar days by default. Configuration
can raise those minima; the record minimum cannot be below 10. Scoring dates must be
**strictly later than every training date**, including all transactions on a date.
Failed refits invalidate the previous fitted state rather than leaving a stale model.

The scikit-learn pipeline is:

1. `TransactionFeatures`: log absolute amount, direction, log category-relative amount,
   cyclic weekday sine/cosine and smoothed weekday rarity by direction.
2. `RobustScaler`, fitted on training features only.
3. `IsolationForest`, 200 trees, fixed seed 42 and one training job.

Reference medians use category/direction groups with at least three examples. Otherwise
the direction median, then the global median, provides a documented fallback. A one-cent
floor makes zero amounts finite. Weekday rarity uses add-one smoothing. Feature
references, scaling and the forest are fitted together only on prior training data.

`detect_anomalies(data, *, as_of=None, min_training_rows=30, min_history_days=30,
refit_every_days=30, contamination="auto", random_state=42)` walks forward by calendar
date and refits periodically using strictly prior rows. Same-day transactions share
one frozen model and cannot affect each other's features or scores. Warmup rows retain
missing scores and nullable `is_anomaly`; they are not implicitly normal.

`AnomalyResult.data` preserves transaction fields and adds `anomaly_score`, `is_anomaly`,
`explanation`, and `training_end`. **Higher** `-score_samples` values are more unusual;
the forest's own prediction threshold determines flags. Scores are not probabilities.
The default `auto` threshold is scikit-learn's rule, not a specified anomaly percentage.
A configurable contamination in `(0, 0.5]` selects a training-score cutoff, not a fraud
prevalence estimate.

Explanations compare amounts to prior reference medians, identify sparse/new category
coverage and previously unseen weekday/direction combinations. They describe transparent
feature differences, not SHAP-style causal attribution. The sample has no verified fraud
labels, so precision, recall and fraud-detection accuracy are not reported. Many flags
can reflect legitimate rare bills, early small training windows, distribution changes
or threshold sensitivity. Investigate records before drawing conclusions.

## Rule-based risk indicators

`assess_risk(data, forecast, *, anomalies=None, history_window_days=90)` uses the
forecast cutoff and, by default, the last 90 calendar days of history. It returns an
overall score, level, data-sufficiency label, individual observed values/points and
actionable explanations. Future history is excluded. Anomaly reports with later
cutoffs or in-sample scores are rejected, since date filtering cannot repair fit leakage.

| Factor | Maximum points | Rules |
| --- | ---: | --- |
| Projected shortfall | 30 | 30 for any negative projected balance; otherwise 15 for a threshold breach; else 0 |
| Current cash buffer | 25 | 25 for negative cash or under 7 historical expense-days of cash; 12 for 7 to under 30; else 0 |
| Expense/income ratio | 20 | 20 for expenses above income or expenses with no income; 10 for ratio 0.8 through 1; else 0 |
| Expense volatility | 15 | 15 for daily coefficient of variation above 1; 7 above 0.5 through 1; else 0 |
| Unusual activity | 10 | 10 if more than 10% of scored rows are unusual; 5 if any through 10%; else 0 |

The sum is Low below 30, Moderate from 30 through 59 and High from 60. Ratio and
buffer are undefined where their denominator is zero; there are explicit no-income
and negative-cash rules instead of infinities. Volatility uses population standard
deviation divided by mean daily expenses, including zero-spend calendar days.

Fewer than 30 days or transactions gives limited-data warnings. Missing anomaly scores
make the contribution unevaluated; the total is a provisional lower bound, not evidence
of normal behavior. Unscored rows are excluded from the anomaly-rate denominator.
With no historical rows, the score is unavailable (`None`, `Insufficient data`).

These thresholds and weights are transparent design choices, **not empirically
calibrated**. An adequate-data label means enough inputs for these heuristics, not a
statistical confidence level. Lumpy rent can increase volatility despite predictable
spending. This is not a credit score, regulated rating, financial product recommendation
or independently validated risk model.

## Deterministic scenarios

`ScenarioConfig` is a frozen Pydantic model that rejects extra fields and invalid
amounts/percentages. `simulate_scenario(baseline, config)` recomputes daily balances and
threshold dates from a copied ledger, without mutating historical data or baseline outputs.

- `income_decrease_pct`: 0–100; includes the requested 10%, 20%, 30% presets.
- `expense_increase_pct`: 0–1000; applies to each baseline outflow.
- `emergency_expense`: nonnegative, finite, two-decimal amount with an explicit
  `emergency_date` inside the forecast horizon. Added after percentage adjustments,
  so the requested emergency amount is not itself inflated.
- `delayed_event_id` with positive integer `delay_days` (at most 365): delays one
  **positive recurring event**, selected from `baseline.events`. Expense events and
  unscheduled average-income events cannot be mistaken for expected payments.

Percentage changes round each event half up to cents; the starting balance is fixed.
Payment delays occur after scaling. A delay within the horizon conserves inflows and
changes timing; one beyond it removes the inflow from horizon totals while preserving
its amount/date in `ScenarioResult.deferred_events`, with a warning. It is never
clamped to the horizon endpoint. No future events are randomized. A zero-change scenario
has an identical daily projection. Outputs are hypothetical, not predictions.

## Executed verification and measured sample results

Environment: Windows, Python 3.12.10, installed versions recorded in
`requirements.lock.txt`. On October 17, 2026:

```text
python -m pytest -q
135 passed in 27.03s

python -m pip check
No broken requirements found.
```

All 53 preexisting tests and 82 new tests passed. An initial run had one faulty test
expectation for an April 1 payment outside a March 1 + 30-day horizon. Its horizon
was corrected to 31 days. The final run above also includes calendar-boundary hardening
and the integrated bundled-data pipeline.

Coverage includes exact forecast totals, no double counting, calendar-month ends,
weekly/biweekly schedules, missed cycles, irregular income, sparse/empty/future-only
history, lookback versus opening-balance semantics, strict thresholds, fractional cents,
no fabricated backtest metrics, malformed analytic inputs, new/constant categories,
zero amounts, warmup, invalid model/scenario controls, risk-weight boundaries, zero
income, zero-spend days, deferred payments and baseline immutability.

Leakage tests mutate/append later rows and compare earlier outputs; modify held-out
amounts while keeping fold forecasts unchanged; verify cutoffs exclude future records;
freeze fitted medians and scaling statistics during scoring; verify same-day peer
independence; reject same-day/in-sample anomaly scoring; and reject later anomaly
reports in historical risk assessments.

The sample runner, with an explicit 2500.00 opening balance, completed successfully:

| Computed sample result | Value |
| --- | ---: |
| Cutoff | 2026-07-29 |
| Estimated current cash | 16,268.23 |
| Projected 30-day closing cash | 17,859.81 |
| Recurring patterns recognized | 5 |
| Dates below the 500-unit threshold | 0 |
| Chronologically scored rows | 175 |
| Rows flagged unusual under default `auto` threshold | 58 |
| Heuristic risk score | 25 / 100 (Low) |
| Combined sample scenario closing-balance change | −1,600.89 |
| Complete rolling folds / origin-day pairs | 4 / 120 |
| Daily net cash-flow MAE / RMSE | 44.57675 / 115.33290987036904 |
| Reconstructed balance MAE / RMSE | 207.7844166666667 / 278.13145579473746 |

Amounts and errors use illustrative currency units. These are measured outputs on
the fixed synthetic history, not estimates of real-world predictive performance.
The 58 unusual rows are not 58 frauds or confirmed errors. The heuristic score's Low
label is not financial assurance. No thresholds were tuned to improve these results.

## Reference documentation

- [scikit-learn: common pitfalls and data leakage](https://scikit-learn.org/stable/common_pitfalls)
  — preprocessing must learn from training data only.
- [scikit-learn: IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
  — score direction, default threshold behavior and fitted estimator API.
- [scikit-learn: lagged time-series features](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html)
  — evaluation should respect temporal ordering.
