# CashGuard AI Phase 5: technical evaluation

**Phase 6 update:** the original figures below were reproduced without changes.
The [Phase 6 report](phase6_anomaly_review.md) documents the false-positive diagnosis,
separate chronological calibration/final evaluation, alert severity and live checks.
On the new matched 247-row final holdout, legacy Isolation Forest produced
`[[139,95],[0,13]]` versus `[[234,0],[1,12]]` for the calibration-selected robust
amount/recurring-context model (precision 1.0000, recall 0.9231, F1 0.9600).
This is a different holdout from Phase 5; the old 0.0779 precision is not the before
value for that comparison. Gemma is now installed: real full/sparse evidence checks
validated five sections, with a separate successful timeout-fallback probe.

This local budgeting prototype estimates cash balances, scheduled/residual cash
flows, unusual transactions and transparent financial stress indicators. Phase 5
preserves the existing engines and adds reproducible evaluation and financial QA.
All measured model results below use fictional data. This is neither credit-model
validation nor evidence of real-world fraud detection or investment performance.

## Architecture and data contract

CSV validation produces dated transactions with exact integer `amount_cents`.
The metrics, forecasting, anomaly, risk and scenario engines are independent of
Streamlit. `dashboard_service` composes their outputs. The UI renders those outputs;
`financial_context` extracts bounded aggregate evidence for optional loopback Ollama.
`evaluation` reuses the forecast and detector APIs; labels are joined after scoring.

Required CSV columns: `date` (`YYYY-MM-DD`), nonblank `description`, signed finite
`amount` with at most two decimals, and nonblank `category`. Optional text columns:
`transaction_id`, `account`, `merchant`. Positive amounts are income; negative amounts
are expenses. Expense totals are positive magnitudes. Imports are limited to 10 MiB
and 100,000 rows; failed imports are previews only and block dashboard analytics.
Use a single currency with two decimal minor units. USD/INR/EUR/GBP selection changes
labels only; there is no exchange-rate conversion or multi-currency reconciliation.

User histories and evaluation results remain in private Streamlit session memory.
Only the bundled public demo CSV is globally cached. Model Evaluation runs explicitly
on a button click; changed data, cutoff, opening balance or income assumptions prevent
stale forecast results from displaying. The synthetic anomaly evaluation is separately
labeled and never evaluates an upload as if it had ground truth.

## Financial audit and confirmed fixes

The existing sign convention, cent arithmetic, opening-balance basis, income/expense
totals, duplicate policy and scenario scaling reconciled in the audit. No accounting
defect was found in normal validated imports. Explicit tests now check across empty,
zero, one-row, all-income, all-expense, irregular and extreme-amount datasets:

```
estimated ending balance = opening balance + positive income - positive expenses
forecast closing balance = current estimated cash + sum(signed future ledger events)
daily net = inflows - outflows = sum(that day's signed events)
```

Confirmed defensive defects fixed:

1. Public `project_events` accepted fractional or boolean cents. It now validates
   integer monetary inputs, calendar dates, horizon and nonblank event IDs, then
   accumulates Python integers. Normal engine callers already supplied valid cents.
2. Financial context validation could raise `OverflowError` for a projection beyond
   `date.max`. It now produces a validation failure, rejected before network access.
3. `rolling_backtest` previously checked `include_irregular_income` only when a fold
   called the forecaster. Invalid controls are now rejected even with no eligible fold.

Opening balance precedes the earliest imported transaction, and current cash uses
all known rows through the cutoff, including rows outside the estimation lookback.
Historical plots are estimates, not verified bank balances. Scenario percentages
apply once to future events, rounded half up; emergency expenses are added exactly
after scaling. Payment delays shift only supported recurring inflows, preserving
out-of-horizon payments separately. Zero-change scenarios preserve the baseline.
Identical account/ID records are counted once; conflicting identities block imports.
Identical ID-less rows require removal or explicit confirmation as separate purchases.

## Forecast method and chronological evaluation

The existing deterministic method detects supported monthly/weekly/biweekly groups
from the trailing 180 calendar days, using median amounts and at least three dates.
It removes recognized recurring rows before averaging residual expenses across all
calendar days. Irregular income is excluded by default. Fractional expected cents
are allocated by rounding cumulative totals and differencing. See the
[engine contract](phase2_analytics.md) for recurrence acceptance and stale schedules.

`evaluate_forecasts` delegates to the existing rolling backtest: minimum 90 training
days, expanding origins every 30 days, complete 7/14/30-day horizons. Training and
all preprocessing stop at each origin. The naive comparator persists the last known
balance and predicts zero daily net. Both methods use exactly the same origin/date
pairs within each horizon. No evaluation errors select parameters.

MAE measures typical absolute error, RMSE emphasizes larger errors, and signed bias
is mean(predicted - actual). Errors use currency units, separately for daily signed
net and reconstructed end-of-day balance. Metrics pool every lead day per origin,
not only the terminal forecast day. Overlapping horizons, if requested, weight
origin/date pairs separately and produce a warning. Missing calendar records are
assumed zero flow, which cannot prove export completeness. Insufficient histories
have unavailable metrics and zero counts, never invented scores.

Measured on the bundled 205-transaction, 210-day fictional history, opening 2500.00,
irregular income excluded. Origins: 2026-03-31, 04-30, 05-30 and 06-29. Evaluation
dates run from 2026-04-01 through 07-06 / 07-13 / 07-29 for the respective horizons;
these are separate fold windows, not one continuously evaluated period.

| Horizon | Target | Pairs (4 folds) | Existing MAE / RMSE / bias | Naive MAE / RMSE / bias |
| ---: | --- | ---: | ---: | ---: |
| 7 | Daily net | 28 | 32.19 / 50.27 / +2.10 | 814.99 / 1654.01 / -367.08 |
| 7 | Balance | 28 | 91.51 / 120.43 / +16.19 | 2864.29 / 3048.55 / -2863.94 |
| 14 | Daily net | 56 | 29.47 / 42.94 / -0.69 | 432.56 / 1170.99 / -158.47 |
| 14 | Balance | 56 | 110.34 / 138.00 / +6.66 | 2611.28 / 2728.42 / -2611.11 |
| 30 | Daily net | 120 | 44.58 / 115.33 / -1.13 | 229.91 / 807.97 / -57.10 |
| 30 | Balance | 120 | 207.78 / 278.13 / -79.63 | 2316.42 / 2403.09 / -2316.34 |

This demo has stable scheduled income and costs, making persistence weak near payday.
Four origins do not establish performance across users, economic regimes or seasonal
changes. No prediction intervals or formal significance estimates are provided.

## Anomaly method, threshold and measured holdout

Existing Isolation Forest: 200 trees, seed 42, one worker, `RobustScaler` pipeline.
Training-only features are log absolute amount, direction, log category-relative
amount, weekday sine/cosine and smoothed weekday/direction rarity. Category/direction
medians require three examples; sparse groups use direction/global references.
Reference denominators have a one-cent floor to avoid division by zero.

Production walk-forward scoring refits every 30 days, using strictly earlier dates.
The fixed benchmark instead fits once and scores a later untouched holdout, isolating
novelty detection. It measures one frozen model, not the live refit policy's accuracy.
Its unique IDs and separate boolean injection labels prevent feature contamination.

Predeclared benchmark: seed 42, four variable mixed income/expense transactions per
day; 480 training rows from 2025-01-01 through 04-30; 240 test rows from 05-01 through
06-29. On every fifth holdout day, multiply the grocery expense by twelve: 12 positives,
228 background rows. Other types of unusualness remain unlabeled. This narrow injected
amount task does not represent fraud, real-world prevalence or all unusual activity.

The unchanged sklearn `contamination="auto"` threshold is **unusualness > 0.5**:
unusualness is negative `score_samples`; sklearn's fitted offset is -0.5. It is not
a probability or an estimated fraud rate. Numeric contamination, if explicitly
requested via the API, selects a training-score quantile. Neither policy uses test
labels; this phase does not choose a replacement threshold after seeing the holdout.

| Measure | Actual result |
| --- | ---: |
| Precision | 0.077922 |
| Recall | 1.000000 |
| F1 | 0.144578 |
| False-positive rate | 0.622807 |
| True negatives / false positives | 86 / 142 |
| False negatives / true positives | 0 / 12 |
| Predicted unusual / total | 154 / 240 |

Confusion matrix: `[[86, 142], [0, 12]]`, rows background/injected, columns not flagged/
flagged. Background false positives by category: Groceries 18/48, Income 60/60,
Shopping 28/60, Transport 36/60. The auto threshold substantially overflags this
benchmark, including every background income. High recall alone is misleading.
Independent chronological calibration, an alert budget, a new holdout, broader
injections and real reviewed labels are needed before operational threshold selection.
Undefined denominators are reported unavailable. The dashboard shows the confusion
matrix, score distributions, threshold and category-level false-positive counts.

## Explainability and risk policy

Anomaly outputs now expose the fitted reference median, scope, sample count and amount
ratio. The UI shows up to three nearest historical absolute amounts from that same
reference population, restricted to the model's training cutoff. Sparse references
are explicitly identified. These are contextual comparisons, not exact attribution
of forest scores; SHAP is not added. Risk cards rank assessed contributions by points.
Threshold tables show previous cash, inflow, outflow, closing cash, gap to the configured
threshold, event types and whether cash crosses or remains below it.

Risk weights are explicit in immutable `RISK_WEIGHTS`; rules use a trailing 90-day
window and are fixed budgeting heuristics, not learned credit/regulatory coefficients.

| Component | Max | Point rules |
| --- | ---: | --- |
| Projected shortfall | 30 | 30 if minimum projected cash < 0; otherwise 15 if below the configured threshold; otherwise 0 |
| Current cash buffer | 25 | 25 if current cash < 0 or coverage < 7 days; 12 for coverage >= 7 and < 30; otherwise 0 |
| Expense / income | 20 | 20 if expenses exceed income, or expenses with zero income; 10 for ratio >= 0.8 and <= 1; otherwise 0 |
| Daily expense volatility | 15 | Population daily expense CV > 1: 15; > 0.5 through 1: 7; otherwise 0; includes zero-spend days |
| Unusual activity | 10 | Flagged/scored > 0.1: 10; > 0 through 0.1: 5; otherwise 0; excludes unscored rows |

Totals stay between 0 and 100: Low < 30, Moderate 30 through 59, High >= 60. With no
history, score is unavailable. Fewer than 30 days/30 transactions or no anomaly scores
produce limited sufficiency; an unavailable component's zero is a provisional lower
bound, not evidence of normality. No expenses makes buffer coverage undefined; zero
income makes the ratio undefined while expenses still trigger its documented rule.
Tests exercise all components, exact volatility/anomaly/cash/ratio boundaries, score
transitions at 30 and 60, and sensitivity to additional opening cash. A high model
false-positive rate can raise the unusual-activity factor; its maximum remains ten.

## LLM reliability and privacy

Automated tests mock model responses and transport. They check exact aggregate figures,
missing versus zero evidence, unsupported numeric claims, injected descriptions,
timeouts, failures, deterministic fallback, loopback-only defaults, disabled proxies/
redirects, cloud-model rejection, retries and stale UI results. New tests also pass
an injection through real CSV validation/dashboard/context construction to the mocked
HTTP boundary and reject an impossible calendar before any request.

The separate real check during this phase reached local Ollama but found `gemma3:4b`
**not installed**. Real Gemma inference was not run, response time is unavailable, and
no model was downloaded. The earlier Phase 4 Qwen compatibility test is historical,
not a Phase 5 Gemma result. No automated test requires Ollama or network access.

Deterministic facts and model prose remain separate. Model prose cannot provide
numeric amounts/dates; trusted engine evidence is rendered independently. Validation
does not prove every qualitative statement is correct. A trusted local Ollama server
and installed model metadata remain assumptions; application code enforces loopback
transport but cannot audit unrelated server/network behavior.

## Performance and software verification

Machine: Windows 11 build 26200, AMD64, Intel64 Family 6 Model 154 Stepping 3,
20 logical CPUs, Python 3.12.10. Runtime versions: pandas 2.3.3, NumPy 2.5.4,
scikit-learn 1.9.1, Streamlit 1.66.0, Plotly 6.9.0, Pydantic 2.14.1,
requests 2.34.2, pytest 9.1.1. Existing bounded requirements and full lockfile retained;
no new framework or dependency was installed.

Measurements use `perf_counter`, three repetitions per size, seed 42, 180 calendar
days, unique IDs and mixed lognormal transaction amounts. Times below are seconds,
median per operation. CSV parsing starts with bytes already in memory. Forecast is
30 days. Dashboard preparation is a fresh uncached composition including its own
anomaly run, excluding CSV parsing, browser rendering and LLM inference. Python/imports
are warm; CPU/background workload was not isolated. Individual samples and the UTC
run timestamp are saved in `results.json`; these are observations, not latency promises.

| Rows | CSV | Forecast | Anomaly | Dashboard preparation |
| ---: | ---: | ---: | ---: | ---: |
| 250 | 0.0034 | 0.0065 | 1.0936 | 1.3347 |
| 1000 | 0.0259 | 0.0657 | 1.5086 | 1.4263 |
| 5000 | 0.1014 | 0.1201 | 1.0708 | 1.2658 |

The final timing run began at 2026-10-17 18:56:39 UTC (October 18 in India).
Timing noise is visible: more rows were not consistently slower. Compare individual
samples in the artifact before drawing capacity or scaling conclusions.

The original per-day implementation took 4.52 / 5.90 / 6.35 seconds in one pre-change
measurement for those sizes (`anomaly_before.json`). Optimization scores whole frozen
refit intervals together and derives flags from the already-computed score and fitted
offset, avoiding duplicate forest traversals. An explicit regression compares scores,
flags and training cutoffs with original day-by-day behavior; existing future/same-day
leakage tests remain. Before/after repetition counts differ, so this is not a controlled
statistical speedup estimate. Larger imports, memory and browser performance are unmeasured.

Baseline inspection run: **247 passed in 65.19 seconds**. Final full suite:
**297 passed in 36.74 seconds; 0 failed, 0 skipped**, retaining all previous cases
and adding 50 cases. Existing tests were not weakened. `pip check` reported
**No broken requirements found**. The existing Streamlit health endpoint returned
**HTTP 200 / ok** and was left running. Streamlit AppTest exercises the new page,
explicit execution, changed-input invalidation and insufficient-data messages;
chart tests compare plotted values with measured values. No browser visual or
mobile screenshot QA was performed. See `reports/phase5/verification.json`.

## Reproduction and artifacts

From the existing workspace in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.evaluate_models --repeats 3 --check-local-llm
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501 and select Model Evaluation. Enter the opening balance
before requesting a forecast backtest. For faster standalone metrics without Ollama
or timings, use `--skip-performance --output-dir reports/phase5_quick`. For a separate
real-model smoke after manually installing Gemma, use:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_local_ai --model gemma3:4b --generate --opening-balance 2500.00
```

Generated evaluation artifacts contain fictional data only: `results.json`,
`forecast_predictions.csv`, `forecast_folds.csv`, `anomaly_holdout.csv` and standalone
`evaluation.html` with embedded Plotly (no CDN required). All metrics can be recomputed
from saved predictions/labels. Tests require no real LLM; numerical error checks use
appropriate floating tolerances while ledger reconciliation uses exact integer cents.

Created source files: `src/evaluation.py`, `src/evaluation_data.py`,
`src/explainability.py`, `src/ui/model_evaluation.py`, `scripts/evaluate_models.py`.
Modified: `src/forecasting.py`, `src/anomaly_detection.py`, `src/risk_engine.py`,
`src/financial_context.py`, `src/visualizations.py`, `src/ui/pages.py`,
`src/ui/components.py`, `app.py`, `pyproject.toml`, `README.md`,
`docs/phase2_analytics.md`. Added five test files: `test_evaluation.py`,
`test_phase5_invariants.py`, `test_explainability.py`, `test_phase5_llm.py`,
`test_model_evaluation_app.py`; plus this report and the seven result artifacts
(including the saved pre-change timing and verification records).

## References and limits

- [scikit-learn IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html): score sign, fitted offset and training contamination threshold.
- [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html): fit preprocessing inside training boundaries.
- [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html): error and binary classification metrics.

Remaining model limits: one favorable forecast demo and four origins; one narrow
synthetic anomaly task with poor precision; no independent calibration, real reviewed
labels, confidence intervals, seasonality or FX. Missing activity is assumed zero and
bank balances are unverified. Risk remains a heuristic with missing-data limitations.
Gemma compatibility/latency and browser visual/mobile QA remain unverified. No deployment,
GitHub publishing, competition submission or persistent financial storage was performed.
