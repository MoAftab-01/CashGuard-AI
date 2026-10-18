# Phase 4: local, evidence-linked financial explanations

CashGuard's existing import, metrics, forecast, anomaly, risk and scenario engines are
unchanged. The optional LLM interprets computed evidence; it does not calculate bank
balances, future transactions, risk points or scenario cash flows.

## Install and start

Download and install [Ollama](https://ollama.com/download) for your operating system.
The Windows installer normally starts an application serving the local endpoint.
Open a new PowerShell terminal after installation so `ollama` is on PATH.

If the Ollama application is not already serving:

```powershell
$env:OLLAMA_NO_CLOUD = "1"
ollama serve
```

If it is already running, keep that server or quit/restart it before changing server
environment variables. A second `ollama serve` may fail because the port is already
occupied; this does not mean the existing server is unavailable. Cloud disabling takes
effect in the Ollama server process, not merely in a new CashGuard terminal.

In another terminal, explicitly choose whether to download Gemma:

```powershell
ollama pull gemma3:4b
ollama list
```

The model download is several gigabytes and its runtime memory requirements depend on
the selected quantization, context and hardware. **CashGuard does not call `/api/pull`,
install Ollama, start/stop Ollama, or download any model automatically.** No paid API
key or cloud model is needed. The model has its own [Gemma model terms and metadata](https://ollama.com/library/gemma3:4b).

From the CashGuard project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501**, select data, enter an opening balance and visit
**AI Insights**. Choose an installed local model, check availability, then click
**Generate AI Insights**. If CashGuard is already running on that port, refresh it
instead of starting a second instance. All other pages work without Ollama.

The default model is `gemma3:4b`. This workspace already had Ollama running with
`qwen2.5:3b` and `llama3:latest`, but did not have Gemma installed during implementation.
No model download was performed.

## Configuration

| Setting | Default | Controls |
| --- | --- | --- |
| `CASHGUARD_OLLAMA_MODEL` | `gemma3:4b` | Default model, also editable in AI Insights |
| `CASHGUARD_OLLAMA_URL` | `http://127.0.0.1:11434` | HTTP loopback endpoint only |
| `CASHGUARD_OLLAMA_TIMEOUT` | `90` | Inference read timeout; UI supports 10–180 seconds |

For example, to use a model that is already installed:

```powershell
$env:CASHGUARD_OLLAMA_MODEL = "qwen2.5:3b"
$env:CASHGUARD_OLLAMA_TIMEOUT = "120"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Restart CashGuard to inherit changed environment settings, or use its model/timeout
controls. The Python service supports a 1–180 second inference read timeout and a
separate bounded connection timeout; metadata calls have a short read timeout. These
are HTTP connect/read limits, not a guaranteed total wall-clock generation duration.
At most two model attempts are made for rejected outputs. Connection/timeouts do not
cause automatic repeated inference requests.

Unqualified model names gain the `:latest` tag. Changing a model name does not download
it. Invalid settings produce safe setup messages without displaying configuration
values from exceptions. User-info URLs, non-loopback hosts, URL paths, queries and
fragments are rejected. `localhost` is normalized to a loopback IP.

## Context construction

`build_financial_context(bundle, currency, scenario=...)` extracts a frozen Pydantic
`FinancialContext` from the validated dashboard bundle. It includes:

- Currency, observed analysis period and inclusive cutoff.
- Estimated reconstructed balance, opening balance, historical income/expenses/net
  cash flow and transaction coverage.
- Expense/income ratio and cash-buffer coverage from the risk engine's historical
  window; these need not use the same period as the full historical totals.
- Forecast horizon, minimum/closing projected balances, configured cash threshold and
  actual projected threshold-breach dates.
- Heuristic risk score, label, sufficiency and assessed point contributions.
- Counts of scored, unscored and unusual transactions, plus flagged-expense count and
  largest flagged expense drawn from anomaly results.
- If configured, scenario reductions/increases, emergency amount, delay duration,
  minimum/closing balances, closing change, breach dates and deferred-payment count.

Money remains integer cents; ratios and scenario percentages preserve decimal values.
Missing metrics remain null, distinct from an actual zero. Period, count, balance and
score reconciliation checks reject inconsistent evidence. Scenarios must belong to the
same baseline. There are no new financial predictions or synthetic substitute values.

The context excludes descriptions, merchants, account names, transaction IDs, raw
histories, free-form category labels and engine explanation strings. CSV text is
untrusted and never becomes a prompt instruction. Even a description containing an
instruction or canary secret does not reach the inference payload.

## Prompts, schema and validation

The service sends a system message and a structured JSON user message, with current
context, an evidence catalog, allowed evidence IDs per section and a safe output-shape
example. Model settings use low temperature, a fixed seed, a bounded generation length
and a modest context limit. Low temperature does not guarantee deterministic wording
across hardware or Ollama versions.

The structured result has five required sections: financial health, cash-flow risk,
spending insights, scenario interpretation and suggested next steps. Each carries a
concise qualitative explanation, evidence IDs and either `supported` or
`insufficient_evidence`. Explicit abstention is valid when data is missing.

Guardrails are layered:

1. Ollama receives a JSON schema with bounded, digit-free explanation grammar and
   section-specific evidence choices.
2. Client parsing rejects malformed JSON, duplicate keys, invalid constants, missing
   sections, extra fields and invalid types.
3. Evidence IDs must exist, be relevant and not refer to missing metrics. They cannot
   invent amounts or reassign a known number to a different financial field.
4. Model prose cannot contain digits (including Unicode numeric characters), currency
   symbols/codes, English spelled-out quantities, calendar dates or relative-date
   assertions. Even a correct-looking copied financial amount is rejected.
5. Scope checks reject unsupported fraud claims, investment/trading recommendations,
   credit/loan approvals, guarantees, links, markup and prompt/configuration disclosure
   patterns. The exact disclaimer "not confirmed fraud" is allowed, but additional
   fraud claims remain blocked.
6. Additional checks reject a nonexistent configured scenario, an ignored configured
   scenario, contradictory risk labels, denial of supplied projected breaches and
   omitted uncertainty for limited data.

**Financial amounts and counts displayed beside an explanation are rendered directly
from the trusted evidence catalog, not copied from model prose.** Labels distinguish
historical observations, estimated balances, projected estimates and hypothetical
scenarios. The UI therefore keeps generated interpretation separate from calculated
figures, instead of relying on a numeric whitelist that could accept a valid number
attached to the wrong claim.

A rejected output is regenerated once with fixed corrective instructions. The rejected
text is not quoted back to the model, rendered, cached or logged. After a second
rejection the application uses deterministic calculated summaries.

Limits: structural, lexical and evidence checks do not mathematically prove every
qualitative assertion. English numeric-word checks are conservative and may reject
otherwise useful wording. Model quality varies, and small models can miss semantic
nuances or reach token limits. Users should review explanations; no calibrated AI
accuracy, fraud probability, credit decision or guaranteed financial outcome is claimed.

## Local transport and data lifetime

The `requests` dependency was already installed through Streamlit and is now declared
explicitly. Only `GET /api/tags`, `POST /api/show` and `POST /api/chat` are used.
Availability and local text-generation metadata are checked before any context is sent.
Cloud-tagged names and cloud-routing metadata are rejected, including remote aliases.
Redirects and environment proxies are disabled. HTTP bodies are bounded and closed.
The local Ollama server itself is assumed trusted; CashGuard is not a sandbox for an
arbitrary program masquerading as Ollama.

Connection failures, missing models, server errors, timeouts, invalid metadata and
invalid output become fixed user messages. Raw response/error bodies and financial
prompts never appear in those messages. Application logs contain only safe rejection
reason codes and attempt counts. `keep_alive=0` asks Ollama to unload after each request.
No prompt files, conversations or raw model outputs are persisted by CashGuard.

Model status is cached only in session state for a short interval. Generation happens
only on a button click. The latest validated report is held only in that browser
session, keyed by financial-context fingerprint, model, endpoint and prompt version.
Balance, threshold, currency, cutoff, scenario or source changes invalidate old text;
there is no automatic regeneration. Changing datasets and Clear session data remove the
stored report. No private financial prompts are placed in global Streamlit caches.

## Reproducible local checks

The default command checks metadata only and never requests inference or downloads:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_local_ai
```

A model-missing response with a nonzero exit code is expected until Gemma is installed.
For an installed model, the explicit synthetic-data smoke check is:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_local_ai --model qwen2.5:3b --generate --opening-balance 2500.00
```

For Gemma after an explicit download:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_local_ai --model gemma3:4b --generate --opening-balance 2500.00
```

The check prints only model/status, validated section names and safe error codes, not
the context or raw response. A successful alternate-model check is not evidence that
Gemma itself has been tested.

## Tests and executed checks

The automated tests use fake HTTP sessions and mocked Ollama services. They require
no installed model, network connection, paid API or model download. They cover context
construction, null versus zero, reconciliation, minimization/injection canaries, local
availability, cloud-alias rejection, proxy/redirect behavior, bounded bodies, safe errors,
timeouts, retry bounds, invalid/truncated responses, unsupported numerical claims,
evidence validity, abstention, deterministic fallbacks, explicit generation and session
result invalidation. The existing analytics and dashboard tests remain in the suite.

The final full-suite run reported **247 passed in 65.60s**, with no failures or skips,
including all 167 previous tests and 80 new cases. Dependency checks reported no broken
requirements. Automated model tests use mocks; no model is required to run Pytest. A real
local `qwen2.5:3b` request on fictional data returned five validated sections; earlier
invalid replies correctly exercised rejection/fallback during development. `gemma3:4b`
was missing, so no real Gemma inference test is claimed. The existing dashboard health
endpoint was checked without stopping the user's running server. No visual browser
inspection was performed.

## Files

| Created | Purpose |
| --- | --- |
| `src/financial_context.py` | Validated, minimized evidence and trusted display catalog |
| `src/insight_prompts.py` | Structured prompts, response schema and output validation |
| `src/llm_service.py` | Loopback Ollama client, model checks, bounded requests and regeneration |
| `src/insight_workflow.py` | Validated reports and deterministic fallback |
| `src/ui/ai_insights.py` | Explicit inference, connection status and session-bound display |
| `scripts/check_local_ai.py` | Metadata-only check or explicit synthetic-data inference |
| `tests/test_financial_context.py` | Context integrity, missing values and privacy minimization |
| `tests/test_insight_prompts.py` | Structured evidence, numeric and injection safeguards |
| `tests/test_llm_service.py` | Mocked local transport, model checks, failures and retry limits |
| `tests/test_insight_workflow.py` | Validated reporting and deterministic fallback |
| `tests/test_ai_insights_app.py` | Mocked UI inference, errors and stale-result invalidation |
| `docs/phase4_local_ai.md` | This setup and implementation guide |

| Modified | Purpose |
| --- | --- |
| `app.py` | Clear the previous AI report when replacing a source |
| `config.py` | Default local endpoint and Gemma model |
| `requirements.txt` | Explicitly declare the already-installed requests dependency |
| `pyproject.toml` | Version 0.4.0 |
| `src/ui/pages.py` | Delegate the existing AI page to its new renderer |
| `src/ui/components.py` | Update the AI page description |
| `tests/conftest.py` | Reusable validated context and safe structured-response fixtures |
| `tests/test_dashboard_app.py` | Replace the obsolete disconnected-only assertion with the generation-button contract |
| `README.md` | Setup, local commands, current capabilities and actual verification |
| `docs/phase3_dashboard.md` | Link its historical AI placeholder description to the Phase 4 implementation |

The financial processing, metrics, forecasting, anomaly, risk and scenario modules were
preserved. Dependency versions did not change; the existing lock file already includes
requests and remains applicable.

Phase 5 has not started and requires approval.

## Primary references

- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Chat API](https://docs.ollama.com/api/chat)
- [Model listing](https://docs.ollama.com/api/tags) and [model details](https://docs.ollama.com/api-reference/show-model-details)
- [Ollama Windows setup](https://docs.ollama.com/windows)
- [Cloud disabling and local-server configuration](https://docs.ollama.com/faq)
- [Gemma 3 4B model](https://ollama.com/library/gemma3:4b)
