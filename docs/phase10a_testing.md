# Phase 10A verification

Executed locally on October 20, 2026, on `phase10a-ui`, based on `6a1f587`.
No Phase 10A commit, push, DEV publication, cloud deployment or paid inference occurred.

## Actual automated results

| Gate | Result |
|---|---|
| Fresh baseline | 512 passed, 0 failed/skipped; 146.77 s |
| Final complete Windows suite | **531 passed, 0 failed/skipped; 90.96 s** |
| Final complete Linux suite | **531 passed, 0 failed/skipped; 101.04 s** |
| AI/API refinement | 23 passed |
| Native Streamlit protocol smoke | 15 execution checks passed, all original capabilities and explicit evaluations included |
| Lint / compilation / dependencies | Configured Ruff checks, compileall, pip check passed |
| Deployment | Existing synthetic staging image built and started healthy; deployment configuration unchanged |

The 19 additional cases cover original route/deep-link compatibility, four primary
areas, exact Home parity and a single chart, all four presets, unchanged history,
reset, unsupported income delay, malformed scenarios, unknown URL/financial parameters,
short/full AI presentation, no extra inference for question changes, and named-only
screenshot release inclusion. All original assertions remain. Windows and Linux
report the same two upstream Starlette/HTTPX and MLflow/SQLAlchemy deprecations.
Tests still cover exact money, chronological leakage, authentication, quotas, session
isolation, public-data restrictions, provider grounding, MLflow and monitoring.

JUnit and detailed local evidence are intentionally ignored under `var/phase10a/`.
The public-safe aggregate record is `reports/phase10a/results.json`. The post-documentation
release/UI gate and final source scan are recorded there rather than inferred from
an earlier run. No live hosted inference or model download was performed.

## Rendered and visual QA

Actual isolated Edge/Chromium visited the running nginx/Streamlit/API staging app at
`http://localhost:8510`. All nine views were exercised at **1440 × 1000**, **834 × 1112**
and **390 × 844**, each in light and dark mode: **54 layouts**, **122 page screenshots**.
There were zero page overflows, clipped KPI values, chart title/legend boundary or
overlap failures, Streamlit exceptions or JavaScript runtime errors. Screenshots across
all nine views, including narrow/dark charts and tables, were visually inspected.

Actual Tab navigation and Enter activation passed for all six viewport/theme combinations.
Each moved focus from Home to Explore, showed a 3 px solid focus outline, and opened
Transactions using Enter. This is a focused navigation check, not exhaustive keyboard
coverage of every framework control. Native inputs/expanders/pills retain labels and
keyboard behavior. Risk uses text labels as well as color, and chart traces use names
and line styles.

Sampled rendered contrast minima were **15.188:1** for page headings, **10.835:1** for
context captions and **5.473:1** for primary action text, passing the selected 3:1/4.5:1
checks. These are computed samples of real rendered styles, not a full all-pixel,
chart-color or WCAG certification audit. The original bright primary button/white
text combination was replaced by explicit dark teal/white. Physical-device and
screen-reader testing, disabled-state/complete component contrast audits, and a real
30-second comprehension study remain outstanding.

## User journeys actually exercised

- Explicit Start demo loads the fictional opening assumption and matching engine values.
- Explore search produces a helpful empty state without changing historical totals.
- A 20,000 cash floor produces forecast breaches; restoring 500 recalculates them.
- Emergency preset changes closing cash by exactly -500; reduced income changes it;
  reset restores the baseline. An invalid amount blocks plan metrics and reset recovers.
- A suggested assistant question displays the existing scenario evidence without inference.
- Home remains at estimated cash 16,268.23 after all public-mode navigation and plans.
- A real local `gemma3:4b` response passed the unchanged structured/financial grounding
  workflow and rendered concise/full evidence in the redesigned assistant. The measured
  **9.753 s browser round trip** includes UI and validation, not just model inference.
- An absent local model retains explicitly calculated answers, with the actual failure
  message; no rejected output is displayed.
- Native direct mode accepted a valid two-row fictional CSV with a 485-character
  normalized description, produced 85.00 cash from explicit opening 10.00, blocked
  totals for invalid money, then recovered after a corrected CSV. The long table
  produced no page overflow.
- The unchanged public mode has no uploader; protected upload/API/ops boundaries and
  session isolation continue to pass their original tests. Local interactive evaluations
  and public read-only evaluation remain accessible under Advanced.

Synthetic benchmark numbers are existing, known-holdout evidence; no new independent
evaluation or real-world accuracy claim was made by the redesign. Financial-engine,
API, inference, tracking, monitoring and deployment implementation files have no diff
from the base. Only UI, QA helpers, screenshot packaging and documentation changed.

## Issues caught during the work

The early Home return initially omitted an empty session-cache container; it now
preserves the existing clear-session contract without retaining financial results.
The first chat refactor omitted the model error message for fallback answers; original
tests caught this, and warnings/calculated output were restored. Rendered review found
corrupted separator characters in two captions and model settings still above the
answer; both were corrected before final captures. Chat avatars were made neutral.

Two failures were in QA assumptions: CDP Enter needed a character event for native
button activation, and a 20,000 threshold does not imply every projected day is below
it. The driver now sends real key text and checks a positive bounded breach count.
A supposed valid long-description fixture was 513 characters and correctly rejected
by the unchanged 500-character validator; the fixture was corrected to 485 normalized
characters rather than weakening validation. These failed attempts were not counted
as successful journeys. Earlier full suites and matrices were rerun after refinements.

## Reproduce locally

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q api src scripts deploy app.py config.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port=8511
```

For synthetic API mode, start the existing staging configuration using the Phase 9
deployment instructions, with fresh environment credentials. Attach the QA helpers
only to dedicated headless Edge profiles on loopback CDP ports, never a personal browser:

```powershell
.\.venv\Scripts\python.exe -m scripts.qa_phase10a
.\.venv\Scripts\python.exe -m scripts.qa_phase10a_local
.\.venv\Scripts\python.exe -m scripts.smoke_dashboard --port 8511 --output var/phase10a/direct-protocol.json
```

The first helper expects staging on 8510/CDP 9224; the local helper expects the direct
app on 8511/CDP 9225 and explicitly requests real local inference only if installed
Ollama metadata confirms availability. Both use fictional data only. The browser
startup requires `--headless=new --remote-debugging-address=127.0.0.1`, the matching
`--remote-debugging-port`, and a dedicated `--user-data-dir` under ignored `var/`.
On Windows launch background browsers hidden. Defaults and overrides are documented
by each helper's `--help`. No hosting or account publication is part of these commands.

Six genuine unedited before/after assets and hashes are listed in
`reports/phase10a/screenshots.json`. The README gallery shows the fictional-data UI,
including a real Gemma answer separately from deterministic public mode. The complete
local captures remain in `var/phase10a/`; no private financial screenshot is included.

Next: test five nontechnical users on finding the forecast, changing a cash floor,
resetting a plan and identifying a calculated versus model-generated answer. Measure
task success/time before claiming a 30-second understanding improvement, then perform
a full assistive-technology audit before any separately approved public release.
