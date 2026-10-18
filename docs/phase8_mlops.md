# Phase 8: local ML engineering and operations

This extends the existing application; the financial algorithms and nine Streamlit
pages are preserved. It is a local demonstration with production-oriented structure,
not a production-secure service. No bank connection, trading, external financial-data
transfer, deployment or Git publishing is included.

See [architecture and pre-change audit](phase8_architecture.md). Runtime evidence is
saved separately under `reports/phase8/`; earlier reports are preserved.

## Installation and local processes

Use the existing Python 3.12 environment. For a reproducible full developer setup:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run app.py
# Separate terminal:
.\.venv\Scripts\python.exe -m api
```

The dashboard remains at **http://127.0.0.1:8501**, using direct analytics by default.
The API defaults to **http://127.0.0.1:8000**. No credentials are required for these
loopback processes. Do not publish their ports without a separate authentication,
authorization, TLS and operational security design.

Dependency groups:

- `requirements.txt`: existing dashboard runtime constraints, without MLflow.
- `requirements-api.txt`: API/metrics additions.
- `requirements-dev.txt`: API dependencies, HTTPX, pytest and Ruff.
- `requirements-mlops.txt`: optional MLflow server/client.
- `requirements-runtime.lock.txt`: exact dashboard/API dependency closure.
- `requirements-mlops.lock.txt`: exact optional tracking closure.
- `requirements.lock.txt`: full verified developer environment, with platform markers.

Locks were generated from installed metadata with `python -m scripts.lock_dependencies`,
including Windows/Linux/macOS conditional dependencies. The original Phase 7 lock is
preserved at `reports/phase8/baseline.requirements.lock.txt`. MLflow 3.17.1 requires
PyArrow below 26, so the combined environment pins 25.0.1. The official Python image
is pinned by digest. These pins are not a promise of perpetual security or identical
behavior on every CPU/OS; review dependency/base-image updates explicitly.

For dashboard/API without tracking or developer tools, install only
`requirements-runtime.lock.txt`. Add `requirements-mlops.lock.txt` for tracking.
The full lock supplies the complete test environment. Cross-platform lock regeneration
requires metadata for conditional dependencies of every target; it was performed in
the prepared Windows environment, including Linux-only Gunicorn metadata. Do not
silently invent pins when metadata is absent.

`.env.example` documents environment variables. Native Python commands do not silently
load `.env`; set variables in the launching terminal. Compose supports its usual `.env`
substitution. Normal dashboard usage neither imports MLflow nor creates experiments.

## API endpoints and contracts

| Method / path | Purpose |
| --- | --- |
| `GET /health` | Process liveness; optional services are not required |
| `GET /ready` | Analytics readiness, HTTP 503 when not ready |
| `POST /api/v1/transactions/validate` | Normalize and report duplicate/conflict decisions |
| `POST /api/v1/analytics/summary` | Exact historical metrics and estimated cash |
| `POST /api/v1/forecast` | Existing deterministic forecast, 1–365 days |
| `POST /api/v1/anomalies/detect` | Selected chronological review engine and coverage |
| `POST /api/v1/risk/analyze` | Existing weighted heuristic components |
| `POST /api/v1/scenarios/simulate` | Baseline, simulated ledger and date/cash differences |
| `POST /api/v1/insights/generate` | Explicit aggregate-only local inference or fallback |

`GET /openapi.json` provides typed request/response schemas. `/docs` is a fully local
readable OpenAPI reference; it deliberately loads no third-party JavaScript. Financial
handlers use the existing synchronous engines in FastAPI worker threads, rather than
blocking the ASGI event loop with synchronous ML work.

Example summary/forecast payload:

```json
{
  "transactions": [
    {"date":"2026-01-01","description":"Fictional receipt","amount":"100.25","category":"Income","transaction_id":"QA-1"},
    {"date":"2026-01-02","description":"Fictional expense","amount":"-25.10","category":"Other","transaction_id":"QA-2"}
  ],
  "opening_balance":"10.00",
  "currency":"USD",
  "horizon_days":7,
  "cash_threshold":"500.00"
}
```

The summary returns estimated cash **85.15**, with monetary totals as exact decimal
strings. Forecast/scenario ledgers use integer cents. Currency selection changes labels
only; USD, INR, EUR and GBP are supported. Reconstructed cash is never a verified bank
balance. The income/expense signs, normalization and duplicate rules match CSV imports.

All financial POSTs require JSON. The API bounds bodies to 1 MiB by default and lists
to 2,000 transactions; the direct dashboard retains its existing CSV limits. NaN,
infinity, booleans as numbers, non-calendar dates, excess precision, unknown fields,
invalid currencies and unsupported horizons are rejected. Opening cash and individual
amount magnitudes must be below 10 billion with at most two decimal places.
The minimum-cash threshold may be negative (for an explicitly chosen overdraft limit).

`transactions/validate` accepts only transactions and the two duplicate controls;
`anomalies/detect` also accepts analysis date, currency and engine. Other analytics
require opening cash. `as_of` is inclusive; later rows do not influence calculations.
Identifier conflicts block analytics. ID-less repeats require either explicit
`reviewed_duplicates: true` or `remove_ambiguous_duplicates: true`. Validation can return
`valid: true` but `analytics_ready: false` while this decision remains unresolved.

For scenarios, add `scenario` with `income_decrease_pct`, `expense_increase_pct`,
`emergency_expense`, `emergency_date`, `delayed_event_id`, and `delay_days` as needed.
An emergency date must be in the projection. Obtain recurring event IDs from the
forecast; delayed inflows beyond the horizon remain explicit deferred events.
For insights use a 30-day horizon, optional model and 1–90 second timeout; the existing
context/fallback templates describe that dashboard horizon. No inference occurs on GET
health/readiness. Missing local models retain deterministic evidence with source marked.

Errors follow:

```json
{"request_id":"opaque-correlation-id","error":{"code":"invalid_request","message":"Correct the indicated request fields.","issues":[{"row":null,"field":"body.opening_balance","message":"Invalid value: decimal_parsing","severity":"error"}]}}
```

Request IDs are returned as headers. Errors omit payload values, unknown user-supplied
field names, exception text and stack traces. Responses use `Cache-Control: no-store`.
HTTP 413 indicates the byte limit, 415 a transport type/encoding error, 422 an invalid
request/analysis, 408 a body-read timeout, 503 occupied analytics capacity, and 500 a
sanitized unexpected error. No unrestricted CORS or request-body logging is enabled.

## Explicit MLflow experiments

The default store is local `var/mlflow/mlflow.db`, with local file artifacts. MLflow is
optional; failures are recorded as failed/rejected tracking status without invalidating
the evaluation's saved results. No dashboard refresh or API request starts tracking.
The adapter disables MLflow telemetry, disallows HTTP redirects, restricts tracking to
SQLite or loopback HTTP, and bounds optional server requests. It never enables autologging.

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --calibration-only --output-dir reports/phase8/evaluation
.\.venv\Scripts\python.exe -m scripts.evaluate_anomaly_candidates --output-dir reports/phase8/evaluation --track-mlflow
.\.venv\Scripts\python.exe -m scripts.evaluate_models --skip-performance --output-dir reports/phase8/legacy_evaluation --track-mlflow
$env:MLFLOW_DISABLE_TELEMETRY = "true"
New-Item -ItemType Directory -Force var/mlflow | Out-Null
.\.venv\Scripts\python.exe -m mlflow server --host 127.0.0.1 --port 5000 --workers 1 --backend-store-uri sqlite:///var/mlflow/mlflow.db
```

The UI at **http://127.0.0.1:5000** reads the same native local database. Parameters
include actual feature names/configuration, thresholds, seeds, partition protocol,
dataset fingerprints, library versions and timestamps. Metrics include forecast
MAE/RMSE/bias and matched baseline comparisons, and anomaly precision/recall/F1/FPR.
Artifacts are allowlisted aggregate JSON, confusion matrices, score histograms and
evaluation charts—not raw transactions, prompts, model weights or pickles.

The approved fictional demo fingerprint is checked before logging; replacing that file
does not silently turn private activity into a "synthetic" run. Synthetic partition
data stays in the existing local evaluation outputs. Saved benchmark replays do not
establish independent or real-world accuracy and never retune the final holdout.

## Docker execution

The shared runtime image contains the same finance dependencies for API and dashboard;
an optional tracking target adds MLflow. No Gemma weights are downloaded. The build
context excludes secrets, arbitrary data files, reports, private caches and tracking
state. Application services have no persistent financial-data volume. Only the optional
MLflow database/artifact store uses a named volume. Containers run as UID/GID 10001,
drop capabilities, and the dashboard/API filesystems are read-only with bounded tmpfs.

```powershell
docker compose build
docker compose up -d --wait
# Optional local tracking server:
docker compose --profile tracking up -d --build --wait
docker compose ps
```

Stop native services first or choose alternate published ports to avoid conflicts:

```powershell
$env:CASHGUARD_DASHBOARD_PORT = "8502"
$env:CASHGUARD_API_PORT = "8001"
$env:CASHGUARD_MLFLOW_PORT = "5001"
docker compose --profile tracking up -d --build --wait
.\.venv\Scripts\python.exe -m scripts.check_services --api-url http://127.0.0.1:8001 --dashboard-url http://127.0.0.1:8502 --tracking-url http://127.0.0.1:5001 --output reports/phase8/container_services.json
# Actual Streamlit page execution, separate from health:
.\.venv\Scripts\python.exe -m scripts.smoke_dashboard --port 8502 --output reports/phase8/container_dashboard.json
docker compose --profile tracking down
```

`down` preserves the named tracking volume. Do not delete it unless you intend to lose
its experiments. Container tracking uses a separate SQLite store from the native UI.
Use `--tracking-uri http://127.0.0.1:5001` on evaluation commands to target that server;
artifact uploads use its local proxy and file-backed Docker volume.

Ollama on the host is not reachable through a container's loopback by default. CashGuard
intentionally preserves the existing strict loopback-only LLM validator. Consequently,
default bridge-network containers retain deterministic insights while native Python
can use host Gemma. `host.docker.internal` is a Docker Desktop convention and is rejected
by that validator. Linux host networking can share loopback, but application listeners
must then explicitly bind `127.0.0.1`; published port mappings do not apply. Docker
Desktop host networking requires separate platform support/settings and is not assumed
or automatically enabled. Native execution remains the verified path for host Gemma.

## CI quality workflow

`.github/workflows/ci.yml` defines Python 3.12.10 Linux quality and container jobs.
Pull requests, pushes to main/master, and manual invocation trigger it once the
repository is connected. It installs exact locks, checks dependencies, runs critical
Ruff diagnostics, compiles Python, executes the complete suite (including financial
invariants/API parity), freezes synthetic calibration before evaluation, verifies
finished local MLflow runs, and exercises offline drift. A dependent job builds and
starts all three containers, then executes HTTP and Streamlit WebSocket checks.
Official Actions v7 tags were checked against their current primary documentation.
Permissions are read-only, checkout credentials are not persisted, and artifacts are
restricted to synthetic aggregates and test summaries. No credentials, model downloads,
image pushes, or deployment steps are present. **The GitHub workflow has not run.**
Local test/build evidence does not establish hosted-runner success.

## Privacy-preserving application monitoring

`GET /metrics` exposes Prometheus text on the same local API listener. Disable with
`CASHGUARD_METRICS_ENABLED=false`. `/health` checks service liveness; `/ready` checks
analytics readiness independently of optional Ollama/MLflow. Metrics diagnose behavior;
they are neither financial forecasts nor proof of readiness. No extra monitoring stack
or remote collector is required.

| Metric | Meaning |
|---|---|
| `cashguard_http_requests_total` | Counts by allowlisted route, method, status class; 4xx/5xx support error rates |
| `cashguard_http_duration_seconds` | Request latency histogram |
| `cashguard_operation_duration_seconds` | Forecast/anomaly/LLM duration by fixed operation and success/error |
| `cashguard_llm_failures_total` | Bounded reasons including timeout, connection error and missing model |
| `cashguard_local_model_available` | Last requested model: -1 unknown, 0 confirmed unavailable, 1 generation succeeded |

Unknown URLs map to `unmatched`; model aliases, request IDs, queries, descriptions,
account identifiers and financial amounts never become metric labels. Registries are
per application/process. Availability is observation-based, not an active poll; a
timeout alone does not prove absence. API service operations are instrumented; the
unchanged direct Streamlit engine path does not publish those timers.

`python -m api` configures JSON logging with UTC timestamp, severity, component,
request ID, event type and request duration/status. It suppresses message bodies,
exception text and Uvicorn's raw access logs. `CASHGUARD_LOG_LEVEL` accepts standard
levels. Caller-provided request IDs must be safe bounded correlation tokens; never
put financial identifiers in them. Metrics/logs remain operational evidence; keep
their listener local and avoid unreviewed forwarding.

## Offline model monitoring

```powershell
.\.venv\Scripts\python.exe -m scripts.monitor_models --synthetic
# Explicit local files, with matching currency, policy and transaction semantics:
.\.venv\Scripts\python.exe -m scripts.monitor_models --reference reference.csv --current later.csv --output-dir reports/private-drift
```

`src/model_monitoring.py` requires strictly separated chronological windows, each
with at least 100 validated rows spanning 30 days. It reports KS distance on log
absolute amounts, Jensen-Shannon **divergence** in bits over the union of categories,
and expense-to-income ratio change. A missing income denominator is unassessed.
Optional aligned boolean anomaly flags require at least 50 scored rows per window;
nullable warmup rows are excluded. Use the same engine/calibration policy across
windows. Fixed review thresholds are KS 0.20, JS 0.10, ratio delta 0.20 and alert-rate
delta 0.10. They are heuristic effect thresholds, not calibrated significance bounds.

`compare_forecast_residuals` additionally requires finite bounded integer-cent
predictions/actuals, observed outcome dates after their forecast origins, unique
origin/date pairs, strictly later comparison outcomes, matching lead-day proportions,
at least 50 residuals and two origins per window. It reports realized error KS, MAE
and bias. Callers must retain actual forecast provenance; timestamps alone cannot
prove that upstream features were leak-free. No future outcome is scored. Because
transactions/residuals are dependent and discrete, IID KS p-values are withheld.

The executed synthetic report compares 492 training rows against 234 later background
rows. Amount KS 0.03966 and category JS 0.00216 remain below thresholds; ratio change
0.30942 requests review, reflecting that background windows can differ. A deliberately
shifted spending window produces amount KS 0.55999, category JS 0.70454 and ratio delta
7.48558, all flagged. Alert rates and actual residual drift remain **unassessed** in
this report because inputs were not supplied; synthetic unit tests verify both code
paths. Neither result triggers automatic retraining. Payday timing, seasonality,
correlated transactions and sample composition need human review.

The CLI writes `monitoring.json` and readable `monitoring.md` with aggregates and
fingerprints, never raw rows. User-supplied reports still contain financial evidence
and must remain private. Drift checks run explicitly offline, never on dashboard refresh.

## Operational limitations

These local controls do not supply authentication, multi-tenant authorization, TLS,
distributed rate limiting, durable jobs, hard CPU cancellation or regulated validation.
Byte limits, bounded concurrent work, body/model/client timeouts limit some failure
modes; Python worker threads are not a process-isolation sandbox. Keep services local.
Drift indicators and synthetic scores are review aids, not automatic model failure or
fraud decisions. No automatic retraining, publishing or deployment is configured.

## Streamlit compatibility and reusable API client

All nine pages continue to call the existing local service and calculations. Direct
mode is the default and currently the only dashboard mode. This intentionally uses
the Phase 8 scope allowance for a tested client rather than partially migrating pages.
No API-mode toggle is advertised in the interface.

`src/api_client.py` supports all nine endpoints with typed shared contracts. It
accepts only literal loopback/localhost HTTP addresses, disables environment proxies
and redirects, bounds request/response bodies, and uses configurable connect/read
timeouts. Timeout and connection messages never contain server bodies or payloads.
Read timeout is an inactivity timeout, not a hard total worker CPU deadline.

```python
from src.api_client import ApiClient

payload = {
    "transactions": [
        {"date": "2026-01-01", "description": "Fictional receipt",
         "amount": "100.25", "category": "Income"}
    ],
    "opening_balance": "10.00",
}
with ApiClient("http://127.0.0.1:8000", timeout_seconds=30) as client:
    result = client.call("summary", payload)
    print(result.value.metrics.estimated_balance)  # Decimal('110.25')
```

`call` returns `BackendResult(value, mode, warning)`. Fallback requires both
`allow_fallback=True` and a supplied direct callable accepting the validated request.
Only connection failures, timeouts and HTTP 503 qualify; invalid inputs, incompatible
responses, redirects and server errors are surfaced. The result identifies
`direct_fallback` and supplies a warning. It never silently switches. A future UI
must display provenance/warnings, choose one backend consistently for a whole analysis,
map normalized rows to requests, replace all bundle dependencies coherently, preserve
session cache invalidation, and rerun navigation/scenario/error-state parity checks.
There is currently no cross-container API client hostname exception; a future internal
network transport needs a separate, narrow trust design rather than arbitrary URLs.

## Executed verification

Baseline: **338 passed, 0 failed, 0 skipped in 67.73 seconds** before changes.
Final Windows Python 3.12.10 suite: **451 passed, 0 failed, 0 skipped in 88.88 seconds**,
including all original tests and 113 new tests. See `reports/phase8/pytest.xml` and
`pytest.log`. Two upstream deprecation warnings remain: Starlette's HTTPX TestClient
adapter and MLflow's SQLAlchemy `noload` strategy. Neither caused a failing assertion.
Dependency checks, critical Ruff diagnostics and Python compilation passed.

The complete suite also passed in a local Linux Python 3.12.10 QA container:
**451 passed, 0 failed, 0 skipped in 55.44 seconds**, with the same two upstream
warnings. It ran as UID 10001 with networking disabled, a read-only source mount and
temporary writable directories. `reports/phase8/linux_pytest.log` retains its output;
`Dockerfile.qa` there records the local test-only image layer. This is separate from
the application images and does not claim hosted GitHub workflow execution.

Native and final Docker execution each passed **13 HTTP service checks** and **15
Streamlit WebSocket execution checks**, covering every page, forecasts, scenarios,
evaluation, unavailable models and fallback. All three final containers were healthy,
ran as UID 10001, and container dependencies passed `pip check`. The images were
actually built and started locally using Docker Desktop's Linux engine. Phase 8 did
not repeat screenshot/desktop/mobile visual QA; prior Phase 7 browser evidence remains
separate and is not represented as a new visual pass.

Seven explicit native MLflow runs and two HTTP/proxied-artifact container runs were
read back as **FINISHED**. The selected synthetic anomaly F1 remained **0.9600**
(precision 1.0000, recall 0.9231, 247 final examples). Thirty-day estimated balance
MAE remained **207.7844**, against **2316.4167** for the last-balance baseline, in
illustrative currency units. Existing Phase 5/6/7 reports were preserved. The Windows
HTTP tracking termination check found and fixed MLflow's cp1252 emoji-print failure;
the initial failed run was retained and marked FAILED, not counted as successful.

Real `gemma3:4b` inference was executed on fictional financial evidence. Direct checks
returned validated AI explanations in **11.68s** (full evidence) and **6.91s** (sparse
history), plus deterministic timeout fallback at **1.06s**. The real API/client path
returned validated AI insights in **7.42s** and deterministic `model_missing` fallback
for an absent local alias. Metrics and JSON log checks confirmed operational fields
and absence of financial payloads. See `local_gemma.json`, `api_gemma.json` and
`observability_verification.json` under `reports/phase8/`.

GitHub Actions is **not executed**. Full API-backed page migration, real-world model
validation and realized residual drift evidence remain future work. Default Docker
Ollama fallback is expected; no privacy validator was loosened to reach the host.
Temporary Compose services were stopped after verification, preserving their tracking
volume. Native dashboard/API/MLflow were left serving on ports 8501/8000/5000.

## Files added or changed

- `api/`: factory, launcher, ingress policy, dependencies, versioned routes,
  request/response schemas and analytics adapter.
- `src/settings.py`, `observability.py`, `experiment_tracking.py`, `model_monitoring.py`,
  `api_client.py`: operational additions; original financial algorithms remain intact.
- `scripts/evaluate_models.py` and `evaluate_anomaly_candidates.py`: explicit optional
  tracking hooks; `lock_dependencies.py`, `check_services.py`, `monitor_models.py` added.
- Eight new test files: `test_api`, `test_api_policy`, `test_tracking`,
  `test_container_configuration`, `test_monitoring`, `test_model_monitoring`,
  `test_ci_configuration`, `test_api_client` (all `.py`).
- `Dockerfile`, `compose.yaml`, `.dockerignore`, `.env.example`, `.github/workflows/ci.yml`.
- Dependency groups/three lock files, `.gitignore`, `pyproject.toml`, `README.md`,
  this guide and `phase8_architecture.md`.
- `reports/phase8/`: baseline lock, milestone gates, synthetic evaluations, drift,
  experiment verification, test reports and service/Gemma execution evidence.

## Evidence and sources

Executed milestone gates are recorded in `reports/phase8/milestones.json`; recorded
runs in `tracking_verification.json` distinguish finished experiments from written code.
Final execution evidence is summarized above; machine-readable milestone and test
reports retain the actual counts independently of this prose.

Primary references consulted: [FastAPI concurrency](https://fastapi.tiangolo.com/async/),
[MLflow local tracking](https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/),
[Docker Compose networking](https://docs.docker.com/compose/how-tos/networking/),
[SciPy KS assumptions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html),
[Jensen–Shannon distance vs divergence](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html).
