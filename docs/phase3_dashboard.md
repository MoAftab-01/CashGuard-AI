# Phase 3 dashboard

This records the Phase 3 dashboard. The subsequent optional Ollama integration is
documented in the [Phase 4 guide](phase4_local_ai.md); its AI page now supports explicit
local inference while preserving the calculated-summary fallback described here.

CashGuard now exposes the existing financial engines through a local Streamlit
interface. Their calculation, forecasting, model training and scenario rules have
not been rewritten. New code coordinates inputs, checks consistent data contexts,
renders results and formats exports.

## Launch

From the project directory in PowerShell, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**. Stop with **Ctrl+C**. For a fresh environment, follow
the README installation steps. Streamlit 1.66+ is required; the recorded environment
already has 1.66.0, so no new package installation was needed during Phase 3.

Select Synthetic demo or upload a CSV. Enter an opening balance immediately before
the earliest imported transaction; enter zero explicitly to assume zero. The demo
has no implied opening bank balance. Choose a currency label; amounts are never
converted between currencies. The sidebar analysis date defaults to the last
transaction date, not the computer clock. Estimated current balances are as of
that date, not a verified bank statement balance today.

## Navigation and controls

| Page | Available behavior |
| --- | --- |
| Overview | Four exact financial KPIs, risk status and sufficiency, projected cash outlook, monthly income/expenses, category spending and recent activity |
| Transactions | CSV upload in the shared sidebar, validation report, inclusive date range, categories, literal description search, direction filter and CSV download |
| Cash Flow Forecast | Historical estimated balances with a 30-day baseline, configurable threshold, below-threshold dates, supported recurring patterns, assumptions and daily projections |
| Anomaly Detection | Unusual/scored/unscored counts, signed-amount timeline, review status, category/search/minimum-amount filters, scores, prior training dates and feature comparisons |
| Risk Analysis | Overall indicator, data sufficiency, cash-buffer days, expense/income ratio, point contributions, explanations, projected threshold breaches and limitations |
| Scenario Simulator | Income reduction, expense increase, emergency amount/date, expected-payment selection and delay; baseline/scenario chart, minimum cash, closing change and changed shortage dates |
| AI Insights | Fixed-template summaries from current computed metrics, forecasts, anomaly coverage, risk and the most recent matching scenario |
| Data quality | Existing import-quality view retained, with transaction preview and duplicate/validation rules |

Anomaly investigation works without an opening balance because it does not use a
cash balance. Transactions and Data quality also work before a balance is entered.
Other analytics pages require an explicit valid opening balance. Incomplete imports
never produce financial totals. Sparse history shows the engines' coverage warnings
and retains unscored transactions; they are never described as normal.

The sidebar threshold and analysis date apply consistently to all financial outputs.
All transactions through that inclusive date contribute to reconstructed balances;
transactions after it cannot enter forecast estimates, anomaly training or risk inputs.
Transaction-table filters affect only the table and its download. They never silently
change the opening-balance basis. Categories, dates and all source rows remain available
for import review, including rows later than the selected analytics cutoff.

## Duplicate review and CSV export

The existing importer removes identical identified records and blocks conflicting
account/ID records. Identical rows without IDs remain available for inspection but
block dashboard analytics by default. Users must select either removal or the explicit
confirmation that repeated rows represent separate transactions. Legitimate repeated
purchases are not silently discarded, and ambiguous rows are not silently counted.
The underlying Phase 1 importer remains unchanged.

Filtered downloads contain canonical CSV columns and exact two-decimal amounts.
Internal cents and source-line columns are omitted. UTF-8 BOM assists spreadsheet
compatibility. Formula-like text fields are prefixed with an apostrophe for spreadsheet
safety; signed numeric amounts retain their original financial meaning. This export
formatting does not modify source transactions or financial calculations.

## Scenarios and honest summaries

Scenario controls call `ScenarioConfig` and `simulate_scenario`. No random future
transactions are created in the interface. Percentage adjustments, emergency timing
and delayed-event handling remain in the existing engine. Payments delayed beyond the
horizon are explicitly shown in a deferred-payment table, rather than disappearing.
An emergency uses its exact entered amount after percentage adjustments.

Scenario settings persist while navigating to another page and returning. The Insights
page includes the most recent valid scenario only when its source, cutoff, balance,
threshold and forecast settings match the current dashboard context. Invalid scenario
inputs clear this summary rather than presenting an old result as current. Changing
datasets clears the previous result; Clear session data resets all session inputs.

The AI Insights page explicitly states that **Gemma/Ollama is not connected**. Every
amount and count comes from engine results formatted with fixed templates. It does not
claim LLM-generated advice, bank verification, a credit score, confirmed fraud, calibrated
fraud probability or guaranteed future cash. Currency selection changes labels only.

## Session caching and input changes

- The only `st.cache_data` function reads the bundled fictional demo CSV. It accepts
  a modification timestamp to invalidate changes and retains at most two entries.
- Uploaded bytes are never passed to globally cached functions. CSV validation,
  anomaly reports, dashboard bundles and scenarios use a bounded, caller-owned
  dictionary in `st.session_state`, with one current value per computation namespace.
- Keys include a SHA-256 content fingerprint and duplicate policy. Forecast keys
  additionally include analysis date, opening balance, cash threshold, irregular-income
  setting and duplicate confirmation. Scenario keys include the full validated config.
- Anomaly caching is independent of balance/threshold changes because those settings
  do not affect the model. Reports are verified against the active date and transaction
  context before being reused in risk analysis.
- Replacing a source clears prior derived caches and the latest scenario result.
  Failed computations are never cached. The app displays current input errors instead
  of falling back to financial results from another upload or invalid configuration.
- Clear session data removes cached inputs/results and uploaded-file widget state.
  No uploaded data is written to SQLite, files or an AI service. Browser refresh can
  create a new session; durable persistence is outside this phase.

The application stays local. A future hosted version would need a separate deployment,
authentication and data-lifecycle design; none was added here.

## Presentation

The theme uses navy surfaces, restrained teal emphasis and native Streamlit status
components. Switch Light/Dark using the app's Settings menu. Plotly charts use transparent
surfaces, inherited theme text, explicit contrasting series colors and interactive hover
and zoom. Historical estimates, baseline projections, scenario projections and minimum
cash thresholds are labeled separately. Layout uses responsive Streamlit columns with
mobile spacing adjustments and native accessible widget labels. User data is never
interpolated into custom HTML; the only injected CSS is static application styling.

## Source changes

- `app.py`: page routing, source inputs, private session caching and orchestration.
- `src/dashboard_service.py`: UI-independent engine coordination, import readiness,
  cutoff/report checks, filtering, export, scenario comparison and computed summaries.
- `src/ui/components.py`, `src/ui/pages.py`: reusable presentation and page renderers.
- `src/visualizations.py`: preserves existing historical charts and adds forecast,
  anomaly and risk charts.
- `.streamlit/config.toml`: switchable light/dark themes with navy sidebars.
- Three new test modules plus a shared read-only integration fixture. Existing engine
  tests remain intact; the existing app tests continue to pass.

## Verification scope

Automated tests cover engine/KPI agreement, parameter recalculation, actual file uploads,
source replacement, duplicate blocking, session separation/invalidation, exact filtered
exports, formula-safe text, engine-derived summary amounts, plotted series, all required
pages, sparse/malformed inputs, payment deferral, scenario persistence and stale-summary
prevention. On October 17, 2026 the final full run reported **167 passed in 60.79s**
with no failures or skips; `pip check` reported no broken requirements. Local health
and application-entry requests both returned HTTP 200. The temporary server was stopped.
The README records the commands and environment.

Streamlit AppTest exercises application execution and widgets. It does not verify
browser rendering, visual contrast or mobile layout screenshots. No visual browser
inspection was available in this environment; light/dark styling uses Streamlit's native
theme support. A separate local launch check verifies the HTTP server.

## Primary references

- [Streamlit caching API](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)
  documents global versus session cache scope.
- [Session State](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
  documents per-session persistence across reruns.
- [Theming](https://docs.streamlit.io/develop/concepts/configuration/theming)
  documents switchable light/dark configuration.
- [Plotly integration](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)
  documents Streamlit-aware chart styling.
