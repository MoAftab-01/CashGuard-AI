# CashGuard AI: approximately 2–3 minute demo script

Use the actual recording's scene timestamps in `assets/capture-manifest.json` for
voice-over alignment. The MP4 contains real browser capture and an English subtitle
track, with no audio. It is not a deployed app or a publicly hosted video yet.

| Scene | Suggested narration | Show |
|---|---|---|
| 1 · Problem · 0:00–0:10 | “For a freelancer, getting paid and having cash when a bill is due are different problems. CashGuard explores that gap locally.” | Actual first-run screen |
| 2 · Overview · ~0:10–0:30 | “I load fictional transactions and explicitly assume opening cash of 2,500. The app reconstructs an estimated balance and separates income, expenses and net flow. This is not a bank balance.” | Start demo, real KPI values |
| 3 · Forecast · ~0:30–0:55 | “The next thirty days combine supported recurring payments with a residual spending baseline. I can inspect the assumptions and choose a minimum cash threshold. This is a conditional projection, not a promise.” | Forecast chart, assumptions |
| 4 · Anomaly · ~0:55–1:25 | “For alert review, I load a separate labeled synthetic benchmark with deliberate amount changes. The default engine genuinely flags this example. Its explanation compares strictly earlier history. Unusual is not confirmed fraud.” | Upload reviewed benchmark, queue, selected comparison |
| 5 · Scenario · ~1:25–1:50 | “Back on the standard demo, I add a hypothetical 500 emergency expense. The projected minimum and closing cash fall by 500; recorded history stays fixed.” | Emergency input, baseline and scenario chart |
| 6 · Gemma · ~1:50–2:20 | “Now Gemma 3 runs locally through Ollama. It explains computed evidence rather than calculating the money. Raw descriptions and account IDs are excluded. Invalid or unavailable generation falls back to deterministic summaries.” | Real generation, validated AI explanations |
| 7 · Proof · ~2:20–2:40 | “The evaluation page exposes the synthetic benchmark and calibration protocol. The matched final-holdout F1 improved from about 0.215 for the legacy policy to 0.960 for the selected review model. That is synthetic evidence, not real-world fraud accuracy.” | Run calibrated comparison |
| 8 · Closing · ~2:40–2:55 | “The potential product is a private budgeting workspace for independent workers, supported by paid setup or support. That business model is unvalidated: I am not claiming customers or revenue. Open weights keep model choice and local processing under the user's control.” | Return to Overview |

Do not call the default selected detector Isolation Forest: it is the category-relative
robust amount model with recurring context. Calibrated and legacy Isolation Forest
remain available. Do not imply Gemma was fine-tuned or that the GitHub workflow ran.
Use “open-weight Gemma” rather than claiming its weights are covered by the MIT code license.
