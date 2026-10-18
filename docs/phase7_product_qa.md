# Phase 7: Local application QA and product refinement

Executed October 18, 2026, in the existing Windows / Python 3.12.10 workspace.
Financial engines, frozen model selection, sample history, dependencies and historical
Phase 5/6 reports were preserved. No publishing, deployment or competition submission
was performed. This is local product QA, not real-world financial validation.

## Confirmed issues and changes

- Desktop KPI amounts were ellipsized. Cards now retain complete amounts, use a
  restrained responsive font size and wrap long values instead of abbreviating money.
- The first caption sat under Streamlit's toolbar. Header padding now clears it on
  desktop and narrow layouts. Viewer toolbar mode removes irrelevant developer actions
  while retaining Settings and display-theme selection.
- Mobile forecast/scenario legends overlapped the chart title. Legends now sit below
  plots; concise titles avoid Plotly multiline-title clipping on narrow screens. Calibration plots use
  the neutral label **Decision threshold**, rather than mislabeling calibrated cutoffs
  as training-only.
  Forecast evaluation ticks now show the actual tested horizons (7, 14 and 30 days)
  instead of automatically generated labels such as 21 and 28.
- Switching pages after scrolling retained a deep scroll offset (observed 1,834px
  before navigation and 1,943px afterwards). Navigation now resets the main panel to
  the top only when the selected page changes. This uses a small controlled local
  script with an internal integer token; transaction text never enters HTML/JavaScript.
- Transaction/anomaly review filters were discarded on navigation. Session-persistent
  widgets retain these choices; replacing a file clears old file-specific filters.
  Table filters continue to leave Overview/forecast history unchanged.
- Blank first-run opening cash provided little guidance. Onboarding now explains the
  next steps. **Start demo** explicitly sets fictional opening cash 2,500.00 and a
  500.00 threshold; no starting bank balance is invented on first run or upload.
  A state/default collision warning from this action was also removed.
- Upload guidance now offers a downloadable fictional CSV template, date/sign/decimal
  instructions, replacement-file guidance and a clear validation-blocking explanation.
- Privacy wording previously suggested no data could be sent to AI. It now identifies
  the explicit aggregate-evidence transfer to local Ollama and excludes raw descriptions,
  merchants, accounts and IDs. Ordinary navigation does not request inference.
- Zero alerts explicitly does not mean zero financial risk. Unscored history remains
  unassessed. The historical Isolation Forest benchmark is labeled separately from
  the default calibrated method. Existing estimate, forecast, risk-component and
  synthetic-validation warnings were retained.

## Browser evidence

Actual headless Microsoft Edge 155.0.4283.45, DevTools protocol 1.3, was available.
The local-only QA helper uses the already-installed requests/WebSocket dependencies;
no browser framework or application dependency was added. An isolated disposable
profile was used, with software/headless launch workarounds for this environment.
Those flags are not application settings or deployment recommendations.

All nine pages were exercised at **1440×1000** and **390×844**, in system light and dark
modes: **36 page/viewport/theme combinations**. Scrolling captures, page navigation,
complete KPI strings, chart counts, main-panel/document widths, title/legend bounds
and browser runtime exceptions are recorded in the
[screenshot manifest](../reports/phase7/screenshots/manifest.json). Dark/light background
colors were verified in the rendered DOM. Screenshots were visually inspected; this
is separate from Streamlit's Python-only AppTest and WebSocket execution checks.
The final matrix contains **104 scrolling captures**, with zero detected main-panel
overflow, truncated KPI values, title/legend boundary collisions or runtime exceptions.
All 36 navigation assertions opened at the top. See the
[summary](../reports/phase7/browser_summary.json). Additional narrow dark-mode captures
cover an active income/emergency scenario and all five completed evaluation charts;
their bounds and paths are in [browser_detail_summary.json](../reports/phase7/browser_detail_summary.json).

The [initial desktop capture](../reports/phase7/screenshots/initial.png) preserves the
original truncation/header defect. Final captures use `desktop-light-*`,
`desktop-dark-*`, `mobile-light-*` and `mobile-dark-*`. Numbered segments cover each
page's internally scrolling main panel. `journey-*` captures show onboarding, empty
filters, forecast assumptions, breaches, scenario stress, anomaly comparisons,
real Gemma loading/output, unavailable-model fallback and CSV validation.

## Executed user journeys

Actual browser results and observed monetary values are saved in
[browser_journeys.json](../reports/phase7/browser_journeys.json).

| Requested journey | Observed result |
| --- | --- |
| Load synthetic history | Start demo loads all 205 rows; no opening cash is silently assumed before clicking. |
| Upload valid CSV | Fictional income 100.00, expense 25.00 and explicit opening 10.00 give estimated cash 85.00. |
| Upload invalid CSV | A `not-money` amount shows validation feedback and blocks every financial KPI; a corrected replacement recovers. |
| Review metrics / navigate | Demo estimated cash 16,268.23, income 31,541.47, expenses 17,773.24, net 13,768.23 remain consistent across pages. |
| Generate 30-day forecast | Cutoff estimated cash matches Overview; projected closing cash 17,859.81 and baseline minimum 16,204.86. Supporting assumptions open successfully. |
| Inspect unusual activity | Default policy: 0 alerts, 118 scored, 87 unscored, explicit zero-alert caveat. All scored shows historical comparisons. Legacy engine exposes its alerts and explanations without fraud claims. |
| Change threshold | Changing 500.00 to 999,999.00 produces 30 breach dates while projected cash remains unchanged. |
| Emergency expense | A 500.00 emergency reduces projected closing cash by exactly 500.00; historical metrics remain fixed. |
| Reduced income | Adding 20% income reduction changes closing cash by -1,340.00 including the emergency. Returning to baseline pages preserves historical metrics. |
| Local Gemma | Generate explicitly produces validated AI sections; a visible loading indicator was captured. |
| Unavailable model | Metadata reports the missing model; Generate retains calculated summaries with an explicit deterministic fallback. |
| Model evaluation | Forecast, historical legacy and calibrated candidate actions complete; five interactive Plotly charts render. |

Additional browser checks verify filter persistence, helpful empty-table guidance,
invalid-upload recovery and a consistent return to the demo. Fourteen assertions/check
groups are saved in the browser journey report; they include the twelve requested
workflows, not fifteen independent financial models.

## Regression and evaluation results

- Complete pytest suite: **338 passed in 33.74s**, no failed or skipped tests. Five new Phase 7
  tests cover explicit demo setup, transaction/anomaly filter persistence, replacement
  uploads, threshold/scenario consistency and invalid-import recovery. Existing finance,
  chronological leakage, model and AI validation tests remain intact.
- Dependency check: `pip check` returned **No broken requirements found**.
- Live local Streamlit protocol: **15 successful execution checks**, covering all nine
  pages, scenario stress, both forecast/candidate actions and unavailable-model fallback.
  See [dashboard_smoke.json](../reports/phase7/dashboard_smoke.json). Its
  `browser_visual_qa: false` accurately describes that protocol script; browser evidence
  is recorded separately above.
- Chronological candidate evaluation was reproduced, using the unchanged calibration
  fingerprint `367539b12146d100f0aa6a924b8f4dbf454cca2f1a59193455fc2a9a00f2c037`.
  Selected `context_stat`: **precision 1.0000, recall 0.9231, F1 0.9600**, matrix
  `[[234, 0], [1, 12]]` on 247 final synthetic examples. One injected change was missed.
  See [current results](../reports/phase7/evaluation/results.json). This replays an
  already-known holdout; it is not new independent validation or a tuning opportunity.
- The existing forecast/legacy script also reproduced its results in a separate
  [output directory](../reports/phase7/forecast_evaluation/results.json): 30-day balance
  MAE **207.7844**, versus last-balance baseline **2316.4167**, using four matched
  origins and 120 origin/date observations. Performance timing repetitions were
  intentionally not rerun; this phase makes no new scalability claim.
- Local server startup, app entry and health were checked. No external hosting was used.

## Real Gemma status

Installed `gemma3:4b` is available through loopback Ollama; no model was downloaded.
The explicit real-model script returned five validated sections with full evidence in
**8.10s** and sparse evidence in **7.13s**. A one-second read-timeout probe returned the
deterministic fallback in **1.08s**. These are measured local wall times, not guarantees.
The actual browser Generate action also returned validated AI output.
See [local_gemma.json](../reports/phase7/local_gemma.json). Rejected raw model output
is never shown as a successful explanation. Structural/numeric validation cannot prove
every qualitative interpretation.

## Reproduce locally

From the project root, start the application and leave its terminal running:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. Start demo is available in the sidebar. General setup,
CSV schema, Gemma setup, limitations and troubleshooting are in the [README](../README.md).

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.smoke_dashboard --output reports/phase7/dashboard_smoke.json
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --calibration-only --output-dir reports/phase7/evaluation
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --output-dir reports/phase7/evaluation
.\.venv\Scripts\python.exe -m scripts.evaluate_models --skip-performance --output-dir reports/phase7/forecast_evaluation
# Explicitly requests real local inference on fictional evidence:
.\.venv\Scripts\python.exe -m scripts.validate_local_ai --output reports/phase7/local_gemma.json
```

Browser QA attaches only to an isolated local DevTools browser endpoint on port 9222,
not a personal profile. With that temporary browser and Streamlit running:

```powershell
.\.venv\Scripts\python.exe -m scripts.browser_qa --matrix
# Includes an explicit real Gemma request using only fictional data:
.\.venv\Scripts\python.exe -m scripts.browser_qa --journeys
```

## Remaining boundaries

Headless viewport emulation is not physical iOS/Android or Safari testing. Native
operating-system file-picker dialogs, touch keyboards, screen readers, unusual zoom
settings and a full accessibility audit remain unverified. Tables intentionally scroll
horizontally to retain their columns on narrow screens. A session refresh can reset
work. CashGuard has no authentication, database, verified bank balances or production
hosting. Forecasts lack calibrated uncertainty bands, risk remains heuristic, synthetic
benchmarks are small, and local AI is optional and fallible. No real-user financial
history was used in these checks.

## Files changed

- `app.py`, `.streamlit/config.toml`, `pyproject.toml`
- `src/ui/components.py`, `src/ui/pages.py`, `src/ui/model_evaluation.py`
- `src/visualizations.py`
- `tests/test_phase7_user_journeys.py`
- `scripts/browser_qa.py`, `scripts/smoke_dashboard.py`
- `README.md`, this report and new `reports/phase7/` artifacts

## References used during QA

Community observations informed the navigation/mobile checks, then actual local
rendering and tests determined the fixes: pipipi-dev's
[Designing Mobile-First UX: Responsive Design in Practice](https://dev.to/pipipi-dev/designing-mobile-first-ux-responsive-design-in-practice-g96)
and maicongilton's
[From Mobile UX Expectations to Better Tabs on the Web](https://dev.to/maicongilton/from-mobile-ux-expectations-to-better-tabs-on-the-web-3h7k).
Primary Streamlit references: [widget state](https://docs.streamlit.io/develop/concepts/architecture/widget-behavior),
[configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
and [controlled HTML/JavaScript](https://docs.streamlit.io/develop/api-reference/text/st.html).
