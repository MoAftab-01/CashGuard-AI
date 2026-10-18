# Security and privacy

CashGuard AI is a local research/demo application. It does not provide public-service
authentication, multi-tenant isolation, TLS, regulated financial validation or a
production security certification. Keep Streamlit, FastAPI, MLflow and metrics on
loopback. Docker publishes host ports on loopback too. Do not port-forward them.

Uploaded CSVs are processed in the current session/request. The only shared dashboard
data cache is the bundled fictional demo. Raw transactions are not logged by the API.
Model generation sends computed aggregate evidence to local Ollama, excluding raw
descriptions, merchants, account identifiers and transaction IDs. Aggregates are still
financial information: control access to the machine, browser session and local model.
CashGuard rejects cloud-routed models and non-loopback model endpoints. For a strictly
offline Ollama server, configure `OLLAMA_NO_CLOUD=1` and restart Ollama. Initial package
and model installation requires downloads; offline operation assumes those are complete.

MLflow is optional and restricted to explicit approved synthetic evaluations. Do not
upload private histories to tracking artifacts. Operational metrics use bounded labels;
request correlation IDs must not contain account/customer identifiers. Logs and tracking
stores belong on the local machine and are excluded from the release package.

Never commit credentials, private `.env` files, personal transactions, model weights,
local databases, browser profiles or unreviewed screenshots. The release allowlist and
pattern scan help find mistakes but cannot prove absence of every possible secret.
If a secret was ever published, revoke it; deleting the latest file is insufficient.

Do not include credentials or financial records in public issues. Use GitHub private
vulnerability reporting only if the repository owner has enabled it; otherwise use a
private channel you already trust to contact the owner. No unverified reporting address
or response-time guarantee is supplied.

Balances/forecasts are estimates, risk scoring is heuristic, and anomaly flags are
review prompts. This application is not a bank, financial advisor or fraud service.
