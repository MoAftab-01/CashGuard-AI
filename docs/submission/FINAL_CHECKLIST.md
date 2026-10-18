# Final submission checklist

Status meanings: **verified** = actually inspected/executed; **incomplete** = prepared
but still needs work; **blocked** = requires owner action or explicit approval.

| Requirement | Status | Evidence / remaining action |
|---|---|---|
| Exact GitHub repository URL | Verified | `https://github.com/MoAftab-01/CashGuard-AI`; owner confirmed and metadata read back |
| Public source code accessible | Blocked | Repository is already public but has no branches; reviewed code push awaits approval |
| License | Verified | Owner selected MIT; root LICENSE added; model/dependency terms remain separate |
| README and local instructions | Verified | Existing dashboard/API/Docker/Ollama/schema/testing guidance retained and release links added |
| Synthetic demo data | Verified | Bundled demo checksum matches; separate anomaly benchmark reproduced from existing generator |
| Automated release checks | Verified | Baseline 451 passed; final workspace suite 458 passed, 0 failed, 0 skipped; lint/compile/dependency/API/dashboard/Docker checks executed |
| Clean extracted source | Verified | Corrected release candidate: 458 passed, 0 failed, 0 skipped in 90.05 seconds; application/config/test bytes match final package inputs |
| Screenshots | Verified | Seven actual PNG captures visually reviewed; corrected downward/red cash delta, expanded anomaly comparison and real evaluation results |
| Local demo recording | Verified | Actual browser recording: 167.907 seconds, 430 captured frames, no audio, English caption track; full decode passed |
| Judge-accessible video/deployed link | Blocked | Owner must approve/upload the real video and verify signed-out playback; no deployment is planned |
| DEV submission template | Verified draft | `DEV_SUBMISSION.md` uses the specified front matter, statement and section order |
| Required tags | Verified draft | `devchallenge`, `hf26challenge`, plus `opensource`, `ai` |
| Best Use of Gemma | Technical fit verified | Real Gemma 3 local integration/inference; organizer and personal eligibility remain separate |
| Accurate metrics | Verified | Frozen matched final-holdout F1 0.9600, precision 1.0000, recall 0.9231; explicitly synthetic |
| No detected secrets in public candidates | Verified within scan scope | Explicit public allowlist scan passed; logs with machine paths excluded; pattern scanning is not an absolute guarantee |
| Git history review | Verified scope | No pre-existing local history; local initial commit preparation authorized; intended remote has no branches; recheck immediately before push |
| Correct deadline | Verified | October 18, 11:59 PM PDT / October 19, 06:59 UTC / October 19, 12:29 PM IST |
| Personal/project eligibility | Owner confirmed | Owner confirmed project start inside the entry window and personal eligibility checks on October 18, 2026; this is owner attestation, not an organizer decision |
| First-user/payment claim | Omitted | No genuine first user, testimonial, payment or revenue verified |
| Agent session | Optional, incomplete | Supported DevRelay workflow exists; no saved sessions/link; remove section unless authentic reviewed export is uploaded |
| Hosted GitHub CI result | Incomplete | Workflow exists; no hosted run has executed; no passing badge claimed |
| Unpublished DEV draft saved | Verified | Staged through DevRelay and read back from the account's unpublished draft list; private editor receipt retained locally |
| Final DEV preview | Blocked | Insert actual public media/code links, remove optional/pending notes, author-edit and preview |
| Explicit publication approval | Blocked | Required for the final code push and the exact final DEV article |
| Published DEV article URL | Incomplete | No article published; only a verified public article URL establishes submission success |

Follow `MANUAL_PUBLICATION.md`. Submission is **not complete** while the code and video
are inaccessible to judges or the DEV article remains unpublished.
