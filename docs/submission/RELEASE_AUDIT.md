# Phase 9 release audit

Executed October 18, 2026 in the existing Python 3.12.10 workspace. This is local
release/submission preparation, not publication, deployment or real-world validation.

## Application readiness

The pre-change audit reran all **451 tests: 0 failures, 0 skips, 54.04 seconds**.
The final Windows suite passed **458 tests: 0 failures, 0 skips, 85.73 seconds**.
All original tests remain. Six release-allowlist/privacy/archive tests and one
financial-display regression were added. Two existing upstream warnings remain:
Starlette's HTTPX TestClient adapter and MLflow's SQLAlchemy `noload` deprecation.
`pip check`, critical Ruff diagnostics and Python compilation passed.

Actual native execution passed **13 HTTP checks** and **15 dashboard execution checks**
across all nine pages and evaluation/fallback workflows. The same 13/15 checks passed
in rebuilt local Docker services. Post-fix native and container startup/page execution
verification completed successfully and is recorded in `reports/phase9/`. Prior Phase 8 Linux
results remain historical evidence (451 tests); they are not represented as a new
Phase 9 Linux full-suite run. Hosted GitHub Actions has not run.

## Confirmed release-blocking display issue

The emergency scenario calculated a minimum-cash decrease correctly but displayed a
green upward delta. Its formatted string began with the currency label, preventing
Streamlit from recognizing the leading negative sign. The narrow fix places the sign
and numeric value first (`-500.00 USD`). An AppTest regression verifies that exact
delta alongside the unchanged calculated closing-cash decrease. No forecasting,
anomaly, risk or scenario calculation was rewritten.

The old native Streamlit process retained imported UI code. It was verified as this
workspace's Streamlit process and restarted so the screenshot/recording would reflect
the actual fix. A stale-server capture attempt stopped on its assertion instead of
presenting the old indicator as corrected. The final assets were reviewed against
the final capture manifest; obsolete attempts are not successful final evidence.

## Clean-source test configuration issue

The first extracted-archive test run passed 449 tests but had eight fixture setup
errors: pytest's configured temporary directory nested inside a cache directory that
did not yet exist. The long-lived workspace hid that prerequisite. The configuration
now uses an ignored top-level `.pytest_tmp` directory. A regression spawns pytest in a
fresh directory with its cache provider disabled and verifies fixture creation. This
is a test-runner/release configuration fix, not an analytics rewrite. Failed-attempt
logs remain local; final corrected clean-source verification is recorded separately.
After the fix, the extracted source release candidate passed **458 tests, 0 failures,
0 skips in 90.05 seconds**, including the new fresh-directory regression. Its
application/test/configuration bytes are compared with the final archive inputs;
subsequent updates are release documentation/evidence only.

## Model/evaluation evidence

The selection fingerprint reproduced exactly:
`367539b12146d100f0aa6a924b8f4dbf454cca2f1a59193455fc2a9a00f2c037`.
On the existing, already-known **247-example synthetic final holdout**, selected
`context_stat` reproduced precision **1.0000**, recall **0.9231**, F1 **0.9600**,
confusion matrix `[[234,0],[1,12]]`. The legacy policy on those same examples had
F1 **0.214876**. The selected model is a robust category-relative amount review
model with recurring context; the available Isolation Forest alternatives were not
renamed as the selected model. This is a reproducibility replay, not a fresh independent
holdout or evidence of real-world fraud accuracy.

Real installed `gemma3:4b` checks returned validated AI explanations in **15.16s** for
full evidence and **14.75s** for sparse history. A short timeout probe retained
deterministic fallback in **1.10s**. No model was downloaded. Timing reflects this
machine and concurrent work, not a guaranteed SLA. The recording separately triggers
real UI generation; its manifest identifies success only after validated AI output.

Nine Phase 8 completed experiments (seven native and two container/proxied-artifact
runs) were freshly read back as FINISHED with evaluation artifacts during Phase 9.
No new experiment is fabricated from those old IDs. Existing reports, benchmark
outputs and databases were preserved.

## Actual demo and screenshot assets

The final local browser recording lasts **167.907 seconds (2 minutes 48 seconds)**,
with **430 captured frames**, original event timing, no audio and an English subtitle
track. Full FFmpeg decoding exited successfully. Seven PNGs were inspected visually:
Overview, forecast, anomaly timeline/alerts, expanded anomaly comparison, emergency
scenario, actual Gemma output and synthetic model evaluation. They contain no personal
tabs, address bars, machine paths or real financial records. No image content or
financial value was edited. The source/helper manifests retain hashes and provenance.

The ordinary fictional demo has zero default alerts. For the anomaly scene, the
existing chronological benchmark generator produces 986 rows; the default rolling
engine scores 617 and flags 24. The chosen example is an actually flagged, known
injected transport transaction of **-27.44**, compared with a prior reference median
of **8.230** and amount/median ratio **3.33**. Those live counts are not the frozen
247-example holdout metrics. The recording explicitly restores the standard demo for
the 500 emergency scenario and real Gemma generation.

## Security and privacy review

An initial 202-text-file working-tree scan found no matches for checked credential
prefixes, private keys or high-confidence secret assignments. It found absolute
machine paths in generated logs. Those logs remain local and are excluded. The
explicit release-candidate scan also checks decodable text, known synthetic-demo
checksum and filenames. Pattern scanning cannot establish absence of every possible
secret or personal datum; it is not a penetration test or security certification.

The release excludes `.env` secrets, private configuration, virtual environments,
caches, local MLflow stores/databases, model weights, browser profiles, raw frame
caches, logs, pytest XML and historical screenshot archives. Only the approved demo
and known synthetic CSV outputs are allowlisted. New submission screenshots use
fictional inputs and are captured without address bars/personal tabs. Operational
listeners remain on loopback; no metrics port is published externally.

The initial audit found no local Git history. The owner-confirmed remote
`MoAftab-01/CashGuard-AI` was verified public with an empty branch list. Recheck before
any approved push; new remote work must not be overwritten. MIT was explicitly
confirmed by the owner. Model/dependency terms remain separate.

The owner subsequently authorized local Git initialization and commit preparation,
with an explicit stop before pushing. The initial release is prepared on local `main`
using only the reviewed release paths; its exact file list and commit receipt remain
under ignored `var/phase9/release/`. No existing financial or ML functionality is
changed by this step. Push and DEV publication still require separate approval.

## Publication readiness

The local source, license, README, architecture diagram, article draft, demo plans,
recording and screenshots are concrete review artifacts. A source allowlist and
SHA-256 archive manifest were generated. The DEV article was staged unpublished via
DevRelay and read back from the unpublished account listing. Its private editor
receipt is excluded from the public release. Archive and public-link status are
tracked by `FINAL_CHECKLIST.md` and the machine-readable Phase 9 reports. No repository
push, visibility change, deployment, DEV publication or authentic session upload occurred.

The owner confirmed project timing within the entry window and personal eligibility
checks on October 18, 2026. This attestation is not an organizer eligibility decision.
Submission still needs approved source upload, an accessible video URL, final
author-edited DEV preview and explicit publication approval.
No first-user story, payment, testimonial, deployed URL, hosted CI success or session
link has been invented. Only Best Use of Gemma is proposed.
