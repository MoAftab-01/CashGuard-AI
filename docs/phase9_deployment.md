# Portfolio deployment preparation

Historical Phase 9 assessment. The paid-plan recommendation below is superseded
by the [Phase 10B strict $0 configuration and measurements](phase10b_free_hosting.md).
Do not create the earlier paid service. The original report is retained as history.

No cloud service has been created, deployed or purchased. Owner approval is required
before publishing the portfolio branch, creating hosting resources or enabling paid
inference. Contest history and its published commits are preserved.

## Target and expected cost

Research checked October 19, 2026. Render supports Docker, environment secrets,
HTTPS, WebSockets, readiness checks and logs. Its [compute plans](https://render.com/docs/compute-plans)
and [pricing](https://render.com/pricing?trk=article-ssr-frontend-pulse_little-text-block)
list **1 CPU / 2 GB (`1c-2g`) at $25/month**. The prepared Blueprint selects that
single-instance starting point. This is an estimate before bandwidth, workspace
charges or optional inference; confirm the final platform quote before approval.

The [free tier](https://render.com/docs/free) has 512 MB and sleeps after 15 minutes
of inactivity. It is not the recommended target for combined Python/Streamlit/ML
processes or reliable first-visitor latency. The smaller paid 512 MB tier is $7/month
but also needs a separate memory fit check. No free-tier capacity claim is made.

The default demo uses deterministic summaries and needs no GPU or model weights.
Local Gemma stays on the developer's machine. Hosting a multi-GB local model in a
512 MB/2 GB web service is not proposed. Optional hosted inference has separate
approval, privacy and price controls described in `phase9_security.md`.

## One public boundary

The `portfolio` Docker target reuses the existing runtime without MLflow. A small
non-root supervisor starts API and Streamlit on container loopback and nginx on the
platform's `PORT`. Only nginx is published. This avoids separately billed services
and blocks Streamlit's framework upload endpoint, rather than relying on hidden UI.

Nginx rejects upload routes, public POSTs and operational paths; it bounds body sizes,
request rates and concurrent connections. API bearer authentication and independent
synthetic-data checks remain defense in depth. HTTPS terminates at Render; internal
requests stay on loopback. Nginx's [WebSocket handling](https://nginx.org/en/docs/http/websocket.html)
preserves Streamlit interactions. The [connection cap](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html)
is instance-wide, not a claim of per-person identity behind a platform proxy.

`/health` and `/ready` expose only minimal API health. Nginx starts after both child
services respond. If any child exits, the supervisor stops the instance so the
platform can restart it. A restart loses session data and resets process quotas.

No persistent disk is required. Do not attach private uploads, an MLflow store or
model weights. Local `compose.yaml` remains unchanged and retains optional private
MLflow; it is not the public deployment configuration.

## Local staging

PowerShell, from the existing project:

```powershell
$env:CASHGUARD_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:CASHGUARD_OPS_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose -f compose.staging.yaml config --quiet
docker compose -f compose.staging.yaml up --build -d --wait --wait-timeout 180
```

Open `http://localhost:8510`. The service publishes only host loopback. Use Start
demo, inspect all pages and confirm uploads are unavailable. Deterministic mode is
intentional. `deploy/public-demo.env.example` documents configuration, not a real
credential file. Do not put actual tokens on a command line or commit them.

Stop staging without deleting historical stores:

```powershell
docker compose -f compose.staging.yaml down
```

Direct local development remains `python -m streamlit run app.py`; local API remains
`python -m api`. Build the original image explicitly with `--target runtime` or use
the original Compose file. The new default Docker target is the synthetic portfolio
ingress; named runtime/tracking targets remain available.

## Approval, deployment and rollback

1. Finish and review the local quality gates and resource observations.
2. Approve the exact portfolio commit, estimated monthly budget and region.
3. Publish that reviewed commit only after approval; do not rewrite contest commits.
4. Create the prepared `render.yaml` service only after separate cloud approval.
   Automatic deployment is off. Store generated secrets in the platform environment.
5. Verify TLS, public readiness, WebSockets, blocked upload/operational routes and
   all nine pages in a signed-out desktop/mobile browser. This cloud check is untested.
6. Keep hosted inference disabled unless its provider, privacy terms and spend limits
   receive explicit approval. Mock tests are not evidence of live hosted availability.
7. Record the actual deployed image digest/commit, platform settings and smoke results.

For rollback, select the previous approved image digest/deploy in Render, restore its
matching environment settings, redeploy manually and repeat readiness plus the
synthetic journey. No financial database migration is involved. Keep secrets out of
rollback logs. If there is no known-good deployment, disable the service instead of
exposing a partly working demo. The API/Streamlit supervisor also terminates on child
failure. Python packages are locked; nginx OS packages resolve from the Debian repo
at build time, so retain the tested final image digest rather than claim byte-identical
future rebuilds.

## Limits requiring later review

Single-instance quotas are not durable/distributed. Real uploads and customer storage
remain disabled. Cloud memory/latency, TLS and platform-specific startup have not been
validated by a live deployment. Local small-load and resource observations passed,
but do not establish cloud capacity: one idle observation was 382.9 MiB across the
staging container, not peak memory. The prepared 2 GB plan leaves headroom; it still
needs a cloud fit check. Fifty runtime packages had no returned OSV advisories;
before-launch review must also cover the built OS image and optional dependencies.
See `phase9_testing.md` for executed results.
