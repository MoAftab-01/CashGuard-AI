# Phase 10B: strictly free public-demo preparation

Assessed October 20, 2026. **No hosting account, cloud service, deployment, paid
resource or hosted inference was created or enabled. Budget: $0.**

## Recommended candidate and cost boundary

[Render's compute documentation](https://render.com/docs/compute-plans) lists the
`free` web-service plan at 0.1 CPU / 512 MB. The existing single-container design
was tested locally with equivalent CPU and memory caps and no swap. It is a
candidate for a small synthetic portfolio demo, conditional on the unexecuted
account, billing and cloud checks below. Local capacity is not a hosting guarantee.

`render.yaml` now selects `plan: free`, one service, automatic deployment off,
`/ready`, independent generated service/operations credentials, HTTPS forwarding,
synthetic-only API execution and deterministic inference. No database, disk,
worker, second API service, hosted model or automatic upgrade is configured.

Before any separately approved cloud launch, verify the account permits a free
Docker service **without adding a payment method or subscribing to a paid plan**.
If it does not, stop and retain the local demo. Never accept a paid alternative.
Use the supplied hostname; do not buy a domain. Keep optional inference disabled.

Render's [free-service policy](https://render.com/docs/free) documents sleep after
15 idle minutes, ephemeral files and shared monthly free hours. Bandwidth/build
overages can bill when a payment method exists; without one, the documented
behavior is suspension or blocked builds. Therefore a free plan alone does not
enforce $0: check the workspace has no billing method, paid subscription/add-ons,
automatic upgrades or purchased pipeline capacity. Accept suspension rather than
payment when a free allowance is exhausted. No such account audit was performed.

## Actual local measurements

Final tested image: `sha256:cd4bd3ba1aa4ae798d8d0eafef9ded4ec3fcbd471e9305b3688e73b37efd8988`.

Uncompressed image size: **834,731,703 bytes (796.06 MiB)**; compressed registry transfer size was not measured.

| Measurement | Free-tier approximation | Local control |
|---|---|---|
| Resource cap | 0.1 CPU / 512 MiB | 1.0 CPU / 1536 MiB |
| Start to public readiness | 57.944 s | 5.488 s |
| Idle working-set sample | 231.5MiB | 231.4MiB |
| Peak cgroup memory | 374.89 MiB | 374.86 MiB |
| Idle CPU (last three samples) | 0.45% / 0.45% / 0.36% | 0.41% / 0.41% / 0.42% |
| Maximum sampled CPU | 12.20% | 102.36% |
| Initial cold UI session | 18.140 s | 2.475 s |
| Single-session Start demo | 4.509 s | 0.625 s |
| Five-session burst wall time | 10.198 s | 1.288 s |
| Five-session behavior | 2 completed; 3 busy; 5/5 correct on retry | 2 completed; 3 busy; 5/5 correct on retry |
| OOM kills / memory limit hits | 0 / 0 | 0 / 0 |

Full local evidence: `var/phase10b/profile-final-free.json` and
`var/phase10b/profile-final-control.json`. Five live sessions were used per run,
not five browser tabs sharing one session. Both runs used the same immutable image.

## Method and capacity interpretation

`scripts/profile_public_demo.py` starts a fresh container by immutable image ID,
publishes only a dedicated host-loopback port, applies no-swap memory/CPU limits,
uses read-only storage with bounded tmpfs and drops capabilities. All model output
is deterministic; no Ollama weights or MLflow process are loaded in this image.
The script stops its own profiling container after recording evidence.

Timing starts before `docker run` and ends when public `/ready` returns 200; it
excludes image download and provider scheduling. The separate initial WebSocket
session measures cold Python/UI execution; Start demo measures the subsequent
analytics run. These are server-completion times, not full browser-paint latency.
The idle samples follow a ten-second settling period before analytics. Docker
stats report sampled working-set memory, not per-process RSS. cgroup v1 peak
includes page cache and the small final measurement process. CPU 100% corresponds
to one host core; short sampling/quota windows can exceed the configured percentage.
Tests shared a local Docker host with other QA work; no cloud latency SLA is claimed.

Five distinct live Streamlit WebSockets were warmed sequentially, then sent a
simultaneous burst of different opening-balance assumptions. The existing two-job
analytics limit admitted two and returned clear busy feedback to three. All five
then returned their own correct values on sequential retry, with no partial
financial results or cross-session state. This is controlled backpressure, **not
five simultaneous successful analytics jobs**. Do not raise concurrency merely to
make a benchmark appear successful. Neither this small test nor a memory fit
establishes sustained public traffic capacity or protection against every attack.

Expect a slow first visit and lost session state after host sleep/restart. Keep
the public demo synthetic-only and label deterministic explanations honestly.
Large local Gemma inference remains available in local mode; it is not suitable
for the free web-service memory cap. No model download was added.

## Boundary verification

| Control | Actual verification |
|---|---|
| Synthetic-only | UI contains no file upload; existing server tests reject nonfixture financial payloads and invalid public settings. |
| Framework upload block | Local ingress returned GET 403 and POST 405. |
| No exposed API/operations | `/api/v1/analytics/dashboard`, `/metrics`, `/docs`, `/openapi.json` and `/mlflow` returned 404. |
| Minimal health | `/health` and `/ready` returned only status/readiness booleans, without credentials, provider paths or financial totals. |
| Server-side API access | Loopback API/Streamlit behind one ingress; browser receives no service bearer token. Existing client/auth/CORS/host/redirect controls retained and tested. |
| HTTPS/WebSocket | Real localhost HTTPS and WSS passed through a separate bounded TLS QA proxy, validating a generated test certificate explicitly. This is not public CA/cloud TLS validation. |
| Deterministic fallback | Actual public browser displays calculated summaries and disables model generation; direct local missing-model fallback also passed. |
| Isolation | Five distinct live sessions retained their own different assumptions after retries; existing cache/session-isolation tests passed. |
| Safe logs/stores | No financial database or MLflow service in the public image. Public nginx access logs are disabled; existing tests enforce allowlisted API telemetry and credential redaction. Private QA logs and credentials stay ignored. |
| Lifecycle | Non-root supervisor starts ingress only after API/UI readiness and stops on child failure; health checks and bounded request/job controls retained. |

Unknown SPA paths such as `/.env` can return Streamlit's HTML shell with status
200; the local probes verified this was the application shell, not file contents.
No environment file or private dataset is copied into the public image.

## Other free offerings

The current [Hugging Face Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview)
lists CPU Basic as having no hourly cost but says creating a compute/Docker Space
requires a paid plan. That account prerequisite makes it unsuitable as an assumed
strict-$0 alternative for this task. No subscription was purchased or Space created.
Do not infer that a “FREE” hardware row guarantees a free account path.

Streamlit-only hosting was not configured: the validated public boundary includes
the existing loopback FastAPI service and restricted ingress. Exposing just the raw
UI or weakening that boundary to fit another platform is outside this stabilization.

## Remaining launch blockers and next action

No public launch is authorized. Before requesting approval for a free pilot:

1. Run the [prepared participant study](phase10b_usability_study.md) and resolve
   material misunderstandings; finish the manual accessibility checks listed in
   [the accessibility review](phase10b_accessibility.md).
2. Verify actual account eligibility, free allowances and **no billable fallback**.
   If zero spend cannot be enforced, use the local portfolio demo instead.
3. Present the exact local commit and free-only configuration for approval.
4. Only after approval, validate the real provider build/start deadline, public
   CA certificate, `wss://` connectivity, sleep/wake behavior, signed-out mobile
   navigation, health, blocked uploads/operations and resource usage on that host.

The Debian/nginx OS layer has not received a full image CVE scan in this phase.
OSV checked the public Python lockfiles, not OS packages or unknown vulnerabilities.
Retain the tested image identity; a future apt-based rebuild can resolve different
OS package versions. No public URL, production SLA or completed deployment is claimed.

## Local reproduction (no cloud)

```powershell
docker build --target portfolio -t cashguard-portfolio:phase10b .
.\.venv\Scripts\python.exe -m scripts.profile_public_demo --name cashguard-phase10b-profile-recheck --memory 512 --cpus 0.1 --port 8513 --env-file var/portfolio-phase9/staging.env --output var/phase10b/profile-recheck.json
```

The env file is an existing **ignored local QA file** containing two independently
generated credentials; it is not bundled or assumed to exist in a fresh clone.
To prepare a fresh local test, generate two random tokens of at least 32 characters
and store them only in an ignored env file with keys `CASHGUARD_API_TOKEN` and
`CASHGUARD_OPS_TOKEN`. Never paste tokens into Git, screenshots or public logs.
See [the README](../README.md) for the existing synthetic staging run command.
