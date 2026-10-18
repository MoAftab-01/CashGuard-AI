---
title: "CashGuard AI: I Built a Private Financial Early-Warning Assistant for Freelancers Using Gemma"
published: false
tags: devchallenge, hf26challenge, opensource, ai
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

<!-- RELEASE GATE: Do not publish until the code is uploaded, a real public/unlisted
video link is inserted, eligibility is confirmed and the author reviews this draft. -->

## What I Built

A freelancer can have a profitable month and still struggle to pay a bill on Tuesday.
Payment timing matters. So does an unexpected expense that arrives before the next
client payment.

I built **CashGuard AI**, a local financial early-warning workspace for freelancers
and small businesses. Import a transaction CSV, enter an opening-cash assumption,
and explore three practical questions: What happened to my cash? What might the next
month look like? What changes if an expense rises or a payment is delayed?

The dashboard connects transaction validation, estimated balances, a thirty-day cash
projection, explainable unusual-transaction review and scenario simulation. Gemma 3
turns computed evidence into readable explanations on the user's own machine.

The business hypothesis is deliberately small: an open core with paid local setup,
CSV preparation and support for independent workers who want help understanding cash
timing without uploading their books to a hosted chatbot. That is a hypothesis to test,
not a claim of customers, revenue or willingness to pay.

CashGuard is a budgeting research tool. It is not a bank, financial advisor, verified
bank-balance service or fraud detection service.

## Demo

**Video publication pending.** A real browser recording is prepared as
`docs/submission/assets/cashguard-demo.mp4`, with an English caption track and no
audio. A deployed app or publicly accessible video URL must replace this paragraph
before publication; localhost is not a judge-accessible demo.

The recording uses fictional data throughout. It starts with the standard demo,
then loads a separate labeled synthetic benchmark to show a genuinely flagged
injected transaction. It returns to the standard demo for a hypothetical emergency
expense and actual local Gemma generation. The data switch is explicit: the ordinary
demo does not magically acquire alerts to make the video look better.

Fresh screenshots accompany the recording: Overview, the forecast, the anomaly
explanation, the emergency scenario, Gemma insights and model evaluation. Upload the
reviewed images in DEV's editor and insert their actual returned URLs before publishing.

## Code

Intended repository: [MoAftab-01/CashGuard-AI](https://github.com/MoAftab-01/CashGuard-AI).
It was verified as public but empty during preparation. **The reviewed release still
needs approval and upload; do not publish this draft while the code is unavailable.**

The application code is MIT licensed. The README includes local installation,
synthetic CSV schema, dashboard guidance, FastAPI, Docker, Ollama, tests and limitations.
Gemma weights are not bundled and retain Google's separate model terms.

## How I Built It

I kept numerical calculations in Python and made the model an explanation layer.
Money uses Decimal or integer cents. A CSV import must pass validation and duplicate
review before financial summaries become available. Forecast assumptions are shown
beside the projection, and reconstructed cash is labeled as estimated.

The anomaly work taught a useful lesson: a model name is not a quality guarantee.
On the **same 247-example synthetic final holdout**, the legacy Isolation Forest
policy had F1 **0.2149**. A category-relative robust amount model with recurring-payment
context, chosen on separate calibration data, reached F1 **0.9600**, precision
**1.0000** and recall **0.9231**. It missed one of thirteen injected changes. Zero false
positives among 234 background examples is an observation, not a promise of zero
real-world false positives. Both Isolation Forest options remain available.

Gemma runs as `gemma3:4b` through loopback-only Ollama. Clicking Generate AI Insights
builds minimized aggregate evidence, requests structured explanations, checks the
response and renders amounts from trusted calculations. Raw descriptions, merchants,
account identifiers and transaction IDs are excluded. Qualitative explanations can
still be wrong; structural checks do not prove financial understanding. Missing
models, timeouts and rejected responses retain deterministic summaries.

The release audit reran the full test suite, API checks, all nine dashboard pages,
the chronological synthetic evaluation and real Gemma inference. Fresh local model
checks produced validated explanations in roughly **15 seconds** on this machine;
timing depends on hardware and model state. A short timeout probe exercised fallback.
The final Windows release suite passed **458 tests with no failures or skips**,
including privacy/packaging checks and regressions for the cash-decrease indicator
and first-run test execution. The clean-source check caught a pytest temporary-folder
assumption that the existing workspace hid; that release configuration is now fixed.
The corrected extracted source then passed the same **458-test suite**.
Two upstream deprecation warnings remain. These checks were executed again rather
than inferred from a previous phase.

FastAPI reuses the existing engines. Optional local MLflow stores synthetic evaluation
aggregates and charts. Docker supplies non-root local services. The GitHub Actions
workflow is written, but **no hosted CI success is claimed**. The dashboard currently
uses direct local analytics; a tested API client exists, while full page migration is
explicitly deferred.

Two community release lessons informed this audit: [test the clean checkout, not just
the long-lived workspace](https://dev.to/stavleak-hackathons/the-commit-is-correct-why-does-the-hackathon-demo-fail-on-a-clean-checkout-5273),
and [make engineering claims traceable to stable evidence](https://dev.to/rajpriyan_s/i-built-the-platform-that-judges-hackathons-in-72-hours-the-hardest-bugs-were-about-evidence-not-ph8).
The release includes a reviewed source allowlist and recorded verification rather
than treating a polished screenshot as proof of correctness.

## Why Does Open Innovation Matter?

For this project, local model execution changes the privacy and operating model.
The explanation step does not require a paid hosted-model API or sending financial
evidence to an external inference service. After dependencies and weights are installed,
the intended workflow can run locally. The computer, local model server, reports and
aggregates still need ordinary access controls; “local” is not a security certification.

Open weights also make the model choice less permanent. The interface can target a
compatible installed local model, and deterministic analytics continue working without
generation. Gemma 3 is the model actually demonstrated here; compatibility with every
other model is not claimed. It has not been fine-tuned for this project.

The MIT application code makes the calculations, assumptions, evaluation and failure
behavior inspectable. Gemma is **open-weight**, with its own terms—not MIT-licensed
model weights or a claim that every component has identical licensing. Hardware,
electricity and support still cost money; I am not calling inference economically free.

## My Agent Session

<!-- OPTIONAL: No authentic session link has been issued. Remove this entire section
before publishing unless a real, reviewed DevRelay session is uploaded and accessible.
See agent_session_instructions.md. Do not invent a link or reconstruct a transcript. -->

No agent-session link is claimed in this preparation draft.

## Prize Categories

**Best Use of Gemma.** Gemma 3 provides the local, user-triggered explanation workflow
around actual cash-flow, risk, anomaly and scenario evidence. The demo includes real
inference and validated output, not a mocked conversation or a renamed API call.
This is the only partner category claimed, subject to the organizer's eligibility review.

*Draft prepared with AI assistance from the development session. The project owner
must verify the facts and meaningfully review/edit the article before publication;
set DEV's AI Disclosure accurately for the final authorship.*
