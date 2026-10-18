# Phase 8 architecture assessment

## Audit before implementation

The existing Python 3.12.10 environment passed **338 tests in 67.73s** before changes.
The repository has no Git metadata. Phase 5/6/7 reports and deterministic synthetic
data are present. Nine Streamlit pages use UI-independent financial modules through
`dashboard_service`; no algorithm relocation or rewrite is needed.

Reusable boundaries:

| Layer | Existing implementation | Phase 8 addition |
| --- | --- | --- |
| Presentation | `app.py`, `src/ui`, `visualizations` | Keep all nine pages and direct mode |
| Financial analytics | validation, exact metrics, forecasts, risk, scenarios | API service calls existing functions |
| ML | chronological detectors, calibration and evaluation | Explicit synthetic tracking, offline drift report |
| Generative AI | minimized context, validated prompts, loopback Ollama, fallback | Inject the existing service into an insights endpoint |
| API | None | Thin versioned FastAPI routes, typed contracts and bounded ingress |
| Configuration | constants in `config.py`, validated Ollama environment | Separate validated operational settings; retain existing constants |
| Observability | privacy-conscious engine log messages | Structured request logs, local Prometheus metrics |
| Experiments | reproducible scripts and saved reports | Optional local MLflow adapter; no autologging or dashboard-triggered runs |

## Minimal structural changes

Add `api/` for request/response contracts, dependency injection, routes and transport
policy; add operational modules under `src/` without moving old modules. API input is
normalized through the same CSV importer so identifier conflicts and duplicate-review
rules remain consistent. Currency is a label, never conversion. Money is exact decimal
text or integer cents on the wire. All analysis uses a common explicit cutoff.

Synchronous financial/ML functions run outside the ASGI event loop. Bodies, transaction
counts and concurrency are bounded. Requests have correlation IDs; errors and logs omit
payloads. There is no database for uploaded transactions and no shared financial cache.
Readiness concerns the analytics application; optional Ollama/MLflow outages do not
make deterministic financial calculations unavailable.

MLflow is optional and logs only allowlisted synthetic benchmark aggregates, fixed
configuration, fingerprints, library versions and generated evaluation figures. An
offline drift module compares strictly earlier/later windows and reports sufficiency;
it neither declares fraud/model failure nor triggers retraining.

Docker adds execution options, with loopback host port bindings and non-root services.
Existing `python -m streamlit run app.py` remains valid. Ollama's loopback-only privacy
boundary will not be loosened for Docker hostname convenience: default containers use
deterministic insights unless a documented local network arrangement provides loopback
access. The initial optional API client is tested separately; partial page migration
will not be presented as a working full API-backed dashboard.

## Controlled milestones

A: API and parity tests. B: optional tracking and actual local run verification.
C: pinned container inputs and local Docker checks where the engine is available.
D: CI, request/model monitoring and offline chronological drift. E: tested local API
client, full regression, startup checks and documentation. Tests gate each milestone.

## Initial environment findings

FastAPI, HTTPX, MLflow, Prometheus client and Ruff were not installed initially.
The Docker CLI exists, but its default engine pipe was unavailable; CLI presence alone
does not establish Docker build/runtime support. No cloud account, external financial
transfer, deployment, Git publishing or competition submission is part of this phase.

## Final verified implementation

The initial Docker engine limitation was resolved locally. All five milestone gates
completed: the final suite passed 451 tests on Windows and 451 in an offline non-root
Linux QA container. Actual application images built and all three services started
healthy. The native nine-page Streamlit app remains in direct mode; the shared typed
API client is tested, and coherent page migration remains explicitly deferred.
See [the operations guide](phase8_mlops.md) for exact results, recorded experiment
status, drift findings, CI's unexecuted status and remaining security boundaries.
