# Portfolio Phase 9: executed quality gates

Client date: October 19, 2026. This work is local on `portfolio-phase9`; no portfolio
commit was pushed and no cloud service or paid inference request was created. The
published contest commits and historical reports were preserved.

## Baseline and regression

The untouched baseline was **458 passed, 0 failed, 0 skipped**, 69.46 seconds.
The final Windows suite is **512 passed, 0 failed, 0 skipped**, 102.86 seconds.
The final Linux suite is **512 passed, 0 failed, 0 skipped**, 87.19 seconds.
Machine-readable results are in `reports/portfolio_phase9/final_verification.json`.
The original tests remain; 54 additional cases cover transport parity, malformed
tables, exact money and missing values, parameter invalidation, API-only rendering,
synthetic-only policy, authentication/CORS, session isolation, rate budgets, backpressure,
provider quotas/grounding/privacy, disabled inference, deployment and onboarding.
Existing chronological leakage and financial-invariant tests still run in full.

Both full suites report two upstream deprecations: Starlette's HTTPX TestClient
integration and MLflow's SQLAlchemy `noload` strategy. Neither was hidden or solved by
unnecessary dependency churn. Ruff's configured critical checks, `pip check`,
`compileall` and `git diff --check` passed. Linux ran as UID 10001 with no network,
read-only source and separate temporary writable directories. Private JUnit evidence:

- `var/portfolio-phase9/baseline.xml`
- `var/portfolio-phase9/final-windows.xml`
- `var/portfolio-phase9/linux-results/pytest.xml`

Milestone gates were executed during migration and overlap; do not sum their counts:

| Gate | Passed |
|---|---:|
| Overview AppTest | 10 |
| Forecast regression | 31 |
| Anomaly integration | 14 |
| Risk integration | 24 |
| Scenario integration | 38 |
| AI/API regression | 88 |
| Adapter/client final migration gate | 31 |
| Public security | 46 |
| Inference/API/model | 101 |
| Deployment/container configuration | 12 |
| Reliability/security/provider/configuration | 49 |
| Onboarding/UI/integration | 37 |

## Actual browser checks

An isolated headless Edge profile, unrelated to personal browser sessions, exercised
the running Docker staging URL `http://localhost:8510` through nginx, Streamlit,
the authenticated API and the existing engines. It exercised all nine pages at
1440 x 1000 and 390 x 844, each in light and dark mode: **36 page layouts**.
The final machine-readable summary records completion and screenshot counts.

Checks include visible page headings, no Streamlit exceptions, no upload widget,
expected financial/evaluation metrics, rendered Plotly charts, page overflow,
KPI clipping, chart title/legend boundaries and JavaScript runtime exceptions.
The final matrix passed all those checks and produced 104 local screenshots,
including the clarified disabled model-generation controls.
Representative screenshots across all nine pages were also visually inspected,
including mobile and dark charts. This is browser emulation, not physical-device
testing, a screen-reader assessment or a formal accessibility/contrast audit.

Browser journeys changed the cash threshold to 20,000 and observed breaches, restored
500, entered a 500 emergency and observed exactly -500 closing cash change, reduced
income and observed an additional change, then returned to unchanged historical
cash of 16,268.23. Table/financial values came from the real API. No model inference
was requested by this browser matrix. Private captures remain under
`var/portfolio-phase9/browser/`; the summary is safe synthetic evidence.

## Containers, boundaries and small-load checks

The original runtime and optional MLflow tracking targets built successfully. The
new `portfolio` target built and started as UID 10001 with a read-only root filesystem,
dropped capabilities, temporary writable directories and one published loopback
port. Runtime `pip check` passed. No MLflow package/database or model weights are
included in the portfolio stage. `compose.yaml` retains its original local services.

Actual HTTP checks returned health/readiness 200; public metrics/docs/OpenAPI/API
routes 404; framework upload GET 403 and POST 405. Even the operations bearer did
not expose metrics through the public ingress. On container loopback, metrics required
the operations bearer and unauthenticated analytics returned 401. Correlation,
bounded labels and absence of sensitive logs are additionally checked by pytest.

A bounded synthetic-only probe executed 12 dashboard requests with two workers:
12 HTTP 200, p50 0.4831s, p95 0.5949s. With six workers, 18 requests produced two
HTTP 200 and 16 controlled HTTP 503 responses under the two-request concurrency
cap; rejected requests are not queued. This is a small local smoke check, not a
production throughput or availability benchmark. It ran separately from browser QA.
An idle post-check observation was 382.9 MiB, 13 PIDs, 0.74% CPU under a 1.5 GiB
container limit. Peak memory and cloud latency were not measured.

Terminating only the API child inside the dedicated staging container caused the
supervisor to stop the container with exit code 1. Restarting the same configuration
returned it to healthy operation. The final image digest and boundary summary are
recorded in the final verification report. No host application process was killed.

## Model and evaluation evidence

Real local `gemma3:4b` generated all five insight sections on fictional evidence and
passed existing structured/numerical grounding validation. Its output source was
`ai`, with no error code. This invocation did not separately measure inference latency.
Unavailable-model and invalid-output behavior are covered by the original/new tests.
Hosted Hugging Face/DeepInfra requests were **mocked only**; no provider key, paid
call, subscription or new model download was used. Public staging is deterministic.

Re-running calibration selection followed by the frozen final evaluation reproduced
`context_stat`, threshold 3.5, and fingerprint
`367539b12146d100f0aa6a924b8f4dbf454cca2f1a59193455fc2a9a00f2c037`.
On the **known synthetic 247-example final partition**, precision was 1.0000,
recall 0.9231 and F1 0.9600; confusion matrix `[[234, 0], [1, 12]]`.
Legacy automatic Isolation Forest on that same partition had F1 0.2149, with 95
false positives. This replay is not fresh independent validation, real-world
fraud-detection accuracy or an assurance about unflagged transactions.

The unchanged offline drift command completed. Both the background and deliberate
shift fixtures returned `review_required`; heuristic thresholds can flag natural
background variation. No realized residual ledger or comparable alert vectors were
provided, so those signals remain explicitly unassessed. No automatic retraining
or claims of calibrated drift accuracy are introduced. Keep user-supplied monitoring
reports private; only synthetic aggregate reports are included here.

## Failures found and resolved

- Wire round trips initially changed missing-value types; explicit object construction
  and dtype metadata now preserve them, with direct/API parity checks.
- A duplicated test-fixture argument and an isolation fixture exceeding its configured
  capacity were corrected; the separate one-slot backpressure test remains.
- A read-only staging launch exposed nginx's default `/var/lib/nginx` temporary paths;
  all runtime paths now use the private temporary directory.
- Cold browser startup exposed HTTP 429s on hashed widget/chart assets. Static files
  now have a separate bounded budget; dynamic/analytics limits remain in place.
- Running a load probe concurrently with browser QA correctly caused a busy scenario
  response. Checks now run separately; the useful busy message was confirmed.
- Ruff found a missing pandas import in the new public evaluation renderer. It was
  fixed and the public evaluation AppTest now executes that page.
- Screenshot review found local-only AI wording and an enabled generation button in
  deterministic API mode. Wording is provider-neutral and disabled generation is
  clearly explained, with a regression test retaining calculated summaries.

## Reproduction

From the project, with Python 3.12 and the locked environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q api src scripts deploy app.py config.py
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --calibration-only --output-dir reports/portfolio_phase9/evaluation
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --output-dir reports/portfolio_phase9/evaluation
.\.venv\Scripts\python.exe -m scripts.monitor_models --synthetic --output-dir reports/portfolio_phase9/drift
.\.venv\Scripts\python.exe -m scripts.check_local_ai --generate --opening-balance 2500.00
```

The Gemma command explicitly requests local inference and requires installed Ollama
and weights. For browser reproduction, first start staging as documented in
`phase9_deployment.md`, then launch a separate Edge instance using an isolated profile,
`--headless=new --remote-debugging-address=127.0.0.1 --remote-debugging-port=9224`,
and run `python -m scripts.qa_portfolio`. Never attach this helper to a personal profile.
`scripts/load_demo.py` accepts only loopback destinations and bounded request counts;
run it inside staging with its existing environment token to reach the private API.
Do not expose API ports merely to run the probe.

Cloud HTTPS/WebSocket behavior, provider billing, a built-image OS advisory scan,
large/adversarial load and physical/mobile accessibility testing remain unverified.
The historical GitHub Actions success concerns the initial release, not this unpushed
branch. Review these limits before any approved public deployment.
