# Phase 6: anomaly optimization and end-to-end validation

This phase preserves the import, metrics, forecasting, scenario, risk-weight and
local-LLM engines. It diagnoses the original detector, compares six candidate policies
under a declared chronological protocol, and adds calibrated alert review to the UI.
All accuracy figures describe fictional injected amount changes, never fraud detection.

## Evidence behind the false positives

The initial full suite reproduced **297 passing tests in 34.91 seconds**. Re-running
the original 480-train/240-test benchmark reproduced precision 0.077922, recall 1.0,
F1 0.144578, FPR 0.622807 and `[[86,142],[0,12]]`. No original tests were removed or weakened.

The diagnostics saved in `reports/phase6/results.json` support these findings:

- **The auto threshold is not calibrated to a financial review workload.** Its
  unusualness cutoff is a fixed 0.5. All 120 ordinary income transactions in training
  exceeded it (mean score 0.5599, minimum 0.5163). All 60 background test incomes also
  exceeded it (mean 0.5568, minimum 0.5181). Overflagging already exists in training.
- **Legitimate structure is treated as rarity.** The original six axes include global
  absolute amount, direction, weekday sine/cosine and weekday rarity alongside the
  category-relative amount. Ordinary higher-value income occupies a distinct minority
  cluster. This is consistent with the observed income flags and the better calibrated
  amount-only ablation; it is not an exact attribution of each forest decision.
- **No recurrence feature tells the original detector that a payment is expected.**
  In the bundled walk-forward demo all six scored monthly salaries and all six scored
  rents from February through July were flagged. Some subscriptions were also flagged.
  This is evidence of alert quality problems, not labeled fraud or accounting errors.
- **Scaling did not explain this failure.** Fitting the same seeded forest without
  RobustScaler on the original training features produced maximum training-score
  difference **0.0**. That is a measured ablation here, not a general scaling claim.
- **A large background distribution shift is not supported by these summaries.**
  Train/background-test log absolute amount means were 3.6715/3.6691; relative amount
  means 0.7020/0.6894; weekday rarity means 1.9457/1.9465. A small sample and these
  summaries cannot rule out every shift, but they do not explain all normal income
  being flagged in both periods.
- **Score direction, label identity and chronology check out.** Flags matched
  sklearn's predictions exactly. Ground truth remained separate and joined by unique
  ID after scoring. Existing future mutation, frozen-scaler and same-day isolation
  tests passed. No evidence of training leakage or reversed labels was found.

## Frozen selection protocol

[The protocol](phase6_protocol.md) was written before new final-test generation.
The old Phase 5 holdout was already known and is diagnostic only. New partitions:

| Partition | Dates | Rows | Seed | Use |
| --- | --- | ---: | ---: | --- |
| Training | 2025-01-01 through 04-30 | 492 | 1729 | Fit features and models |
| Calibration | 2025-05-01 through 06-29 | 247 | 2718 | Select thresholds and candidate family |
| Final | 2025-06-30 through 08-28 | 247 | 31415 | Matched frozen-model evaluation |

Each period contains variable groceries, transport, shopping and business receipts,
monthly salary/rent/subscriptions, and valid zero transport entries. Calibration/final
include twelve rotating category amount changes (multipliers 2/4/12), a 3x recurring
salary and one legitimate irregular insurance expense. There are thirteen injected
positives and 234 background rows per evaluation period. All labels are separate
from features; IDs and dates are disjoint. The task does not label every kind of
unusualness or simulate real-world prevalence.

Candidate features, seeds, threshold rules and selection ordering were fixed before
final evaluation. Calibration selects a 95th-percentile background threshold using
the `higher` order statistic and strict greater-than alerts. Statistical candidates
also have a predeclared minimum deviation threshold of 3.5. Calibration needs at least
30 reference records spanning 14 days; training needs 30 records spanning 30 days.

Among candidates with calibration FPR <= 5%, selection maximizes F1, then precision,
recall and simpler-model preference on an exact tie. Calibration scores are selection
evidence, not unbiased performance estimates. Selected family: **context_stat**, with
threshold **3.5**, calibration precision/recall/F1 **1.0000 / 0.6923 / 0.8182**, FPR 0.

The manifest `reports/phase6/selection.json` was saved before the CLI opened the final
partition. Its fingerprint is
`367539b12146d100f0aa6a924b8f4dbf454cca2f1a59193455fc2a9a00f2c037`.
Final evaluation cannot fit/calibrate models. Labels, input ordering and final-label
mutation tests verify identity alignment and frozen predictions. Reproduction checks
the saved selection and blocks a changed selection rather than silently retuning it.

## Models and matched final results

The original six-feature Isolation Forest remains intact. Its calibrated candidate
changes only its threshold. The amount forests use a single absolute robust log
amount deviation, with 200 trees, seed 42 and one worker. The statistical baseline
uses that deviation directly. For category/direction references with at least three
training examples:

```
z = abs(log1p(abs(amount_cents)) - median(training log amounts))
    / max(1.4826 * MAD(training log amounts), 0.15)
```

Sparse groups use direction/global references and display a warning. Zero reference
amounts retain a zero log center; amount ratios use a one-cent denominator floor.
No direction or weekday rarity axes enter the amount candidates, so weekday-only
anomalies are outside their scope.

Recurring context reuses existing forecast schedule detection, fitted only on training
rows. A supported due date within two days substitutes the expected amount as the
reference and uses a fixed 0.15 log-scale tolerance. It never exempts payments: an
inflated recurring salary remains eligible for an alert. Off-schedule payments use
the usual category reference. This can flag legitimate changes in payment timing.

Every row below uses the same 247 final examples. Matrix rows are background/injected;
columns are not flagged/flagged. Model selection did not use these results.

| Candidate | Precision | Recall | F1 | FPR | Matrix |
| --- | ---: | ---: | ---: | ---: | --- |
| Original IF auto | 0.1204 | 1.0000 | 0.2149 | 0.4060 | `[[139,95],[0,13]]` |
| Original IF calibrated | 0.4375 | 0.5385 | 0.4828 | 0.0385 | `[[225,9],[6,7]]` |
| Amount IF calibrated | 0.5909 | 1.0000 | 0.7429 | 0.0385 | `[[225,9],[0,13]]` |
| Recurring-context IF calibrated | 0.5909 | 1.0000 | 0.7429 | 0.0385 | `[[225,9],[0,13]]` |
| Statistical amount baseline | 0.9231 | 0.9231 | 0.9231 | 0.0043 | `[[233,1],[1,12]]` |
| **Selected statistical amount + recurring** | **1.0000** | **0.9231** | **0.9600** | **0.0000** | **`[[234,0],[1,12]]`** |

The selected model missed one injected amount change. Contextual/statistical review
flagged 0/5 legitimate recurring payments versus 3/5 for original IF auto and 1/5 for
the non-contextual statistical model. Both amount forests have the same aggregate
confusion matrix, although context changes which background payments are flagged.

Zero observed false positives among 234 examples does not imply a zero population
FPR. The synthetic distribution favors amount-based comparisons; real drift, new
categories, timing anomalies and mislabeled review outcomes remain untested. No
threshold was changed after opening the final partition to force a better result.

## Live alert policy and dashboard

The sidebar offers Calibrated amount review (selected family), Calibrated Isolation
Forest and Legacy Isolation Forest. Legacy APIs and their default outputs remain
available. The UI delegates to `dashboard_anomalies`; library callers can pass its
result as `build_dashboard(..., anomalies=report)`.

Live review uses earlier training plus a subsequent 60-calendar-day unlabeled
calibration window, refitting every 30 days on still earlier history. Both windows
precede scoring dates. Its reference quantile uses all recent records, which are
not confirmed normal; contamination can increase thresholds and reduce recall.
These live thresholds are not the benchmark's labeled-calibration threshold.
Sparse training/calibration stays unscored rather than silently falling back to
an uncalibrated detector. Risk validation rejects nonchronological calibration
provenance; engine changes invalidate private session analytics and AI evidence.

Severity is a deterministic review priority:

| Severity | Rule |
| --- | --- |
| Not scored | Insufficient training/calibration; no normality judgment |
| Informational | Score does not exceed the frozen calibrated threshold |
| Review recommended | Score exceeds the threshold |
| High priority | Alert, background-calibration rank >= 99%, and amount/reference >= 3 |

Ranks are empirical percentiles, not probabilities. Recurrence cannot downgrade an
inflated amount. Filters cover severity, recurrence, category, amount, description
and scoring status; no alerts are removed from the result data. Explanations include
training reference, count, amount ratio, deviation, threshold and calibration cutoff.
Comparison tables use the matching reference population through training_end only.

On the current bundled demo the selected live policy scores **118 rows**, leaves
**87 unscored**, flags **0**, and yields heuristic risk **15/100**; estimated cash
remains **16,268.23**. This is not an accuracy result. In particular, zero live alerts
does not prove the demo is normal; prior unusual records and initially sparse
recurring history can raise an unlabeled calibration threshold. The warnings and
legacy/calibrated-forest alternatives remain visible.

## Forecast and accounting verification

The forecasting engine was not replaced or modified in this phase. All saved
7/14/30-day Phase 5 MAE/RMSE/bias values reproduced within 1e-8 currency units.
Thirty-day balance MAE/RMSE/bias remain **207.7844 / 278.1315 / -79.6253**, versus
**2316.4167 / 2403.0912 / -2316.3352** for last-balance persistence.

Tests verify matched origin/date windows, cent-to-unit conversion, known opening
balance reconstruction at every naive origin, and pooling every origin/lead-day pair.
Changing held-out amounts cannot change the first-origin predictions. Adding 100
units to opening cash shifts predicted and actual balances by 100 while leaving all
errors unchanged. Daily-net and balance errors remain distinct; incomplete horizons
are excluded and missing calendar days are assumed zero flow. Existing sign, duplicate,
scenario scaling, payment delay and ledger reconciliation tests still pass.

## Real Gemma and fallback checks

Local Ollama and **gemma3:4b** were available. No model download was performed.
`scripts.validate_local_ai` explicitly used fictional evidence from the calibrated
dashboard pipeline, not mocks, through loopback-only HTTP:

| Real check | Result | Wall time |
| --- | --- | ---: |
| Full demo evidence | `source=ai`, five validated sections | 6.33 s |
| One-row insufficient history | `source=ai`, five validated sections | 7.10 s |
| One-second read-timeout probe | `source=deterministic`, `error_code=timeout` | 1.07 s |

Times include local verification, inference and response validation, not just token
generation. The timeout is a read timeout, not a total wall-time deadline. Accepted
responses had no unsupported numeric claims; trusted amounts remain separately
rendered from analytics outputs. The sparse response acknowledged unassessed activity
and uncertainty but stayed generic. Structure/quantity checks cannot prove every
qualitative interpretation. This small smoke test is not a comprehensive LLM evaluation.
Validated responses, context fingerprints and exact times are saved in `local_gemma.json`.

Automated tests use mocked responses and transport for missing Ollama, timeout,
unsupported figures, prompt injection and deterministic fallback. They need no real
model, do not download one, and ensure finance is not sent before local-model checks.

## Verification and reproduction

Final full suite: **333 passed in 53.01 seconds; 0 failed, 0 skipped**, including
all 297 previous cases and 36 new calibration, severity, recurrence, provenance,
financial, forecast, mocked-LLM and UI cases. Existing tests were not weakened.
Saved matrices/counts reconcile exactly with exported predictions/labels; JSON
floating metrics (serialized to ten decimal places) reconcile within 1e-9.
Dependency checks reported **No broken requirements found**. The actual local server
was restarted to load new modules. `scripts.smoke_dashboard` completed **15 live
Streamlit protocol runs**: startup, overview metrics, transactions, forecast, anomalies,
risk, scenarios, changed scenario income, evaluation page, forecast evaluation,
candidate comparison, quality, AI page, missing local model and deterministic fallback.
It checked actual application execution and exception elements, beyond HTTP health.
The live smoke requests no AI inference: the missing-model probe fails metadata
verification before inference. Actual Gemma inference is the separate test above.

No browser automation tool was available. **Visual layout/mobile browser QA remains
incomplete**; WebSocket execution and AppTest are not visual inspection. Machine/runtime
context and locked package versions are the same as the Phase 5 Windows/Python 3.12.10
environment; the installed Ollama client reports **0.40.5**. Test/dependency records
are saved in `reports/phase6/verification.json`. All runs were local; no deployment,
publishing or competition action occurred.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --calibration-only
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates
.\.venv\Scripts\python.exe -m scripts.validate_local_ai
.\.venv\Scripts\python.exe -m streamlit run app.py
# In another terminal while the app is running:
.\.venv\Scripts\python.exe -m scripts.smoke_dashboard
```

Start with `requirements.lock.txt` for the verified dependency environment. The
evaluation CLI saves `selection.json` before final generation and checks its
fingerprint. The final command writes measured comparisons, full predictions/labels,
training/calibration data and offline Plotly charts. Use the dashboard's **Run
calibrated candidate comparison** button for the same fixed protocol in private
session memory. Repeating the fixed final evaluation does not change model selection.

If Gemma is missing on another machine, check `ollama list` and install Ollama first;
start `ollama serve` only if a server is not already running. `ollama pull gemma3:4b`
downloads several gigabytes and must be run only when the user chooses that download.
The validation command reports missing dependencies without downloading anything.

Created source: `src/anomaly_features.py`, `src/calibrated_anomalies.py`,
`src/anomaly_experiments.py`, `scripts/evaluate_anomaly_candidates.py`,
`scripts/validate_local_ai.py`, `scripts/smoke_dashboard.py`.
Created tests: `tests/test_calibrated_anomalies.py`, `tests/test_phase6_evaluation.py`,
`tests/test_phase6_integration.py`. Added this report, the selection protocol and
`reports/phase6/` artifacts. Modified: `app.py`, `src/dashboard_service.py`,
`src/ui/pages.py`, `src/ui/model_evaluation.py`, `src/explainability.py`,
`src/risk_engine.py`, `pyproject.toml`, `README.md`, `docs/phase5_evaluation.md`.
No forecasting calculations, legacy detector defaults, dependency constraints or
existing tests were changed.

Primary references: [IsolationForest score/offset documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html),
[novelty detection and evaluation](https://scikit-learn.org/stable/modules/outlier_detection.html).
