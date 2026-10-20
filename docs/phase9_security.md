# Portfolio Phase 9 security boundaries

Updated October 19, 2026. These are application controls for a synthetic portfolio
demonstration, not regulatory compliance, a penetration test, or security certification.

## Modes and data

Local direct mode preserves private CSV analysis and local Ollama. Hosted/staging
profiles require API mode, synthetic-only public mode, strong service credentials
and positive request limits. Public UI has no upload widget. The API independently
rejects CSVs and transaction arrays that differ from the bundled fictional fixture.
Changing opening cash, thresholds and scenario controls is explicitly hypothetical.
Interactive private backtests remain local; public evaluation is a read-only artifact.

The existing validator still bounds CSV bytes/rows and prevents silent duplicate
counting. The API bounds JSON bytes, rows, response sizes, body deadlines and concurrent
analytics. Invalid imports block totals. No financial CSV is written to a database or
temporary file. UI financial caches and generated reports belong to the current
Streamlit session, and are cleared when the backend/profile changes.

## Authentication and ingress

API requests use a 32–256-character environment-supplied bearer token. Tokens are
compared in constant time, never put in URLs or logs, and masked in configuration
errors. `/metrics`, `/docs` and `/openapi.json` require a separate operations token in
public mode; without that token they remain inaccessible. Minimal `/health` and
`/ready` responses remain available without exposing data or model credentials.

The service token authenticates the UI server, not individual visitors. It must not
be embedded in browser code. The public demo is not a multi-tenant financial service.
Allowed Host values, API destinations and CORS origins are explicit. HTTPS is required
for approved remote API hosts; private HTTP is a separate operator-controlled opt-in.
Redirects and environment proxies are disabled in clients. Arbitrary user endpoint
URLs are not accepted.

Per-client and global request budgets use bounded in-process memory. Forwarded-IP
headers are not trusted. Authenticated UI requests carry a random, session-owned ID;
neither session IDs nor financial values become metric labels. Anonymous failures are
budgeted against the socket peer. Health stays responsive when analytics is busy.
These limits reset on restart and are not distributed: use one replica until shared
limits or an independently reviewed ingress policy are implemented.

Hiding Streamlit's uploader is not sufficient to block its framework upload route.
The deployment ingress must also reject `/_stcore/upload_file` and public POSTs,
limit body sizes/connections, and expose only the public UI port. The portfolio
deployment configuration implements that additional boundary. Do not expose a raw
Streamlit listener publicly as a substitute for the prepared ingress.

## Inference and privacy

`src/inference.py` defines the provider interface and conservative atomic budgets.
Local Ollama remains available. Public mode defaults to deterministic summaries.
The optional hosted HTTP adapter uses the existing requests dependency; no hosted
SDK, subscription, model download or paid request is introduced by installation.

Hosted requests require explicit operator approval before setting
`CASHGUARD_INFERENCE_HOSTED_ENABLED=true` and providing the provider key. They go only
to Hugging Face's fixed HTTPS router, using Gemma 3 4B via DeepInfra. Minimized
aggregates leave the machine in that mode; provider privacy/retention terms require
review before private data is considered. The public demo accepts synthetic data only.
Local direct mode intentionally continues to use local Ollama.

The same evidence construction, structured output and numeric grounding checks apply
to both model paths. Model output never replaces trusted financial calculations.
Input bytes, output tokens/bytes and timeouts are bounded. Inference is not
automatically retried. Per-session/global request limits and conservative cost
reservations are atomic; failures/timeouts retain their reservations because billing
may already have occurred. Budgets reset on process restart and cannot guarantee an
external provider bill: set account-level billing limits before enabling hosting.

Research on October 19 used [Hugging Face's model metadata](https://router.huggingface.co/v1/models),
[chat completion contract](https://huggingface.co/docs/inference-providers/en/tasks/chat-completion)
and [billing guide](https://huggingface.co/docs/inference-providers/en/pricing).
The listed DeepInfra route supports structured output at $0.05/million input tokens
and $0.10/million output tokens. An illustrative 3,000-input/512-output-token request
is about **$0.0002012**, or **$0.2012 per 1,000 such requests**, before any other costs.
Actual token counts and future prices vary. No hosted inference has been executed;
compatibility is documented and tested with mocks, not represented as live validation.

## Operations and remaining review

Preserve the optional local MLflow profile; never place MLflow or its database on the
public route. Do not mount private stores/uploads into the demo. Operational logs
allowlist event types, bounded codes, route templates, request correlation and timing;
they exclude bodies, prompts, model responses, exception text and credentials.

Rotate secrets through the platform environment, redeploy, and verify the previous
token fails. Use immutable image digests for rollback. Before a real public launch,
review platform access, TLS/headers, provider terms, dependency advisories, ingress
behavior under load and account-level spend controls. Real financial uploads, user
accounts, persistent customer storage and distributed quotas remain outside this demo.

## Executed checks

Milestone C targeted gate: **46 passed**, zero failures/skips. Tests cover masked
configuration errors, separate operational authentication, rejected non-synthetic
inputs without echo/logging, exact CORS, forged forwarding headers, bounded budgets
and distinct session IDs. Milestone D provider/API/model gate: **101 passed**.
The final suites passed 512 tests on Windows and Linux. Live local staging verified
non-root/read-only operation, blocked upload and operational routes, separate metrics
authentication and fail-closed child supervision. OSV returned zero advisories for 50
locked Python runtime packages; OS packages and optional development/tracking
dependencies were not covered by that query. The source allowlist scan found no
credential-pattern or unrecognized financial-data findings. Neither check proves
absence of every vulnerability or private datum. Exact results and limitations are
recorded in `phase9_testing.md` and `reports/portfolio_phase9/`.
