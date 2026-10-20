# Phase 10B: local release readiness

Completed October 20, 2026 on **`phase10a-ui`**. No push, merge, public publication,
cloud deployment, paid service or hosted inference was performed. This is local
portfolio stabilization after the previously documented challenge cutoff; it is
not a claim of an on-time challenge submission.

## Commit and baseline review

The 29 reviewed Phase 10A files were committed locally as
**`7600b705e1f5437fbe2e44183ec6b4275902e0c4`** —
“Refine CashGuard UI into task-based portfolio experience”. The fresh baseline
passed **531 tests in 116.51 seconds**, with zero failures/skips.

Before that commit, the explicit release allowlist covered every changed file.
The scan reviewed 267 public candidates with no findings. Six approved dashboard
PNGs were the only new binaries; the largest changed file was 158,644 bytes. No
recordings, private CSVs, credentials, databases, weights, raw logs, test caches
or unreviewed screenshots were included. Relative Markdown file links resolved.
Pattern scanning and manual review cannot prove absence of every possible secret.

The Phase 10B fixes, reports and this document are prepared as a separate local
stabilization commit. Resolve its exact SHA after committing with:

```powershell
git log -1 --format=%H -- docs/phase10b_release_readiness.md
git show --stat --oneline HEAD
```

The final commit SHA is also returned in the task completion message. It is not
embedded in its own content, which would change the SHA. Origin remains
`https://github.com/MoAftab-01/CashGuard-AI.git`; no remote mutation is authorized.

## Preserved capabilities

Four primary areas remain **Home, Explore, Plan, AI Assistant**. Advanced retains
all nine original route IDs: Overview, Transactions, Cash Flow Forecast, Anomaly
Detection, Risk Analysis, Scenario Simulator, AI Insights, Model Evaluation and
Data quality. Direct execution and API-backed execution both ran successfully.

No financial, forecasting, anomaly, risk, scenario or inference engine was
rewritten. Public mode remains synthetic-only with uploads blocked at UI, API and
ingress boundaries. Local CSV imports and local Ollama/Gemma remain available.
Session caches, minimized prompts, grounding, credential separation, rate and
concurrency controls, telemetry allowlists, optional local MLflow and monitoring
remain covered by the complete regression suite.

## Stabilization changes

- Correct semantic section levels, light-theme status/error/table contrast,
  enlarged KPI wrapping and column reflow, focus visibility and reduced motion.
- Add chart descriptions and native HTML data alternatives using plotted values;
  add readable filtered transaction/review tables. Preserve original interactive
  charts, grids, analytics and downloads.
- Identify the scenario input that needs correction without displaying submitted
  values or partial financial results.
- Replace the former paid Render plan with **free**, retaining one restricted
  ingress, disabled automatic deployment and deterministic public inference.
- Add reproducible local axe/expanded-state checks, bounded resource profiling,
  eight meaningful regression cases and the unfilled participant study kit.

Details: [accessibility findings](phase10b_accessibility.md),
[usability study](phase10b_usability_study.md),
[measurements and $0 conditions](phase10b_free_hosting.md).

## Actual final verification

| Gate | Executed result |
|---|---|
| Complete Windows pytest suite | **539 passed**, 0 failed/skipped; **156.34 s** |
| Complete offline non-root Linux suite | **539 passed**, 0 failed/skipped; **114.70 s** |
| Dependencies / lint / compilation | `pip check`, configured Ruff checks and compileall passed |
| Python advisory check | OSV batch lookup of **111** distinct locked package/version pairs: **0 returned advisories**, no pagination pending; does not cover OS packages or unknown issues |
| Real browser accessibility | **36** page/theme/viewport combinations, plus expanded chart/empty/error states and **12** expanded light/dark states: zero detected axe violations; incomplete chart checks remain |
| Layout and scaling | No page overflow or clipped KPI values in the 36 combinations; 320/720px reflow and 200% root-font checks passed after fixes |
| Keyboard / accessibility tree | Actual Tab/Enter navigation and mobile sidebar opening; 3px focus indicator; chart label/native table exposed; invalid-plan alert role present |
| Direct-mode live protocol | **15** runs passed, including all nine capabilities, chronological forecast/candidate evaluations and unavailable-model fallback |
| API-backed browser journeys | Threshold changes, emergency expense, reduced income, reset, unchanged historical totals and deterministic assistant passed |
| Local AI browser journey | Real **gemma3:4b**, source `ai`, validated evidence; **9.402 s browser round trip**, not inference-only latency; missing-model fallback passed |
| Local CSV journeys | Valid fictional CSV, long description, invalid amount blocking totals, and corrected-file recovery passed |
| Container builds | Existing `portfolio`, `runtime` and optional `tracking` targets built successfully; both Compose configurations validated quietly |
| Restricted ingress | Health/ready passed; upload GET 403 / POST 405; API, metrics, docs, OpenAPI and MLflow paths 404 |
| TLS transport | Real localhost HTTPS and WSS passed with an explicitly trusted test certificate; no cloud/public CA claim |
| Log review | Final QA logs contained no known test credentials, raw fixture descriptions or bearer-header text; raw logs remain ignored |
| Resource fit | Final image 796.06 MiB uncompressed; 512 MiB / 0.1 CPU run: 231.5MiB idle, 374.89 MiB cgroup peak, 57.944 s ready, 4.509 s Start demo, no OOM/limit hits |
| Five live sessions | Two burst requests completed, three received bounded busy feedback; all five retained correct isolated values on sequential retry |

Two pre-existing upstream deprecation warnings remain: Starlette's HTTPX test
client integration and MLflow/SQLAlchemy `noload`. They are not test failures.
Eight new tests cover exact accessible forecast/reference values, all labeled
confusion counts, raw histogram observations, empty charts, free-only configuration,
actual accessible rendering/section levels and field-specific invalid-plan recovery, and literal table text without changing money or source data.
Existing heading tests now assert h2 where the semantics intentionally changed.

## Evidence and remaining limits

The compact [results record](../reports/phase10b/results.json) is suitable for source
review. Full JUnit files, pinned axe script, screenshots, browser manifests,
resource samples, test certificates and logs remain under ignored `var/phase10b/`.
All prior technical/evaluation reports and the original six Phase 10A screenshot
assets are preserved. No new screenshots or recordings are staged for Phase 10B.

No participant outcomes are claimed. No physical mobile, screen-reader, native
browser menu zoom, exhaustive manual contrast/target-size audit, OS image CVE scan,
real hosting account/billing review, provider build, public TLS, sleep/wake or cloud
load test was completed. A small synthetic load test is not production capacity
validation. Zero alerts does not mean zero risk, and synthetic model F1 is not
real-world fraud accuracy. Local Gemma is not offered within the free demo container.

**Readiness decision:** the application passes its local technical gates and fits
the measured free-tier resource approximation for a modest synthetic demonstration.
Public launch remains conditional on manual usability/accessibility work, an account
configuration that enforces $0, provider checks and explicit owner approval.
Recommended next action: run the participant study, then review a free pilot using
the exact local commit. Retain the local demo if zero spend cannot be guaranteed.

## Exact local run commands

Private direct mode (with the existing local model support):

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501
```

Synthetic-only restricted staging, from a shell with two independently generated
test credentials set as described in [the README](../README.md):

```powershell
docker compose -f compose.staging.yaml up --build -d --wait --wait-timeout 180
```

Open `http://localhost:8510` and select Start demo. The separate final Phase 10B QA
instance ran on `http://localhost:8512`; it is a local test instance, not deployment.

## Files changed by Phase 10B

- `README.md`
- `app.py`
- `docs/phase10b_accessibility.md`
- `docs/phase10b_free_hosting.md`
- `docs/phase10b_release_readiness.md`
- `docs/phase10b_usability_study.md`
- `docs/phase9_deployment.md`
- `render.yaml`
- `reports/phase10b/results.json`
- `scripts/profile_public_demo.py`
- `scripts/qa_phase10b_accessibility.py`
- `src/ui/ai_insights.py`
- `src/ui/chart_data.py`
- `src/ui/components.py`
- `src/ui/model_evaluation.py`
- `src/ui/pages.py`
- `src/visualizations.py`
- `tests/test_ai_insights_app.py`
- `tests/test_phase10b_readiness.py`
- `tests/test_portfolio_backend.py`
- `tests/test_portfolio_experience.py`
