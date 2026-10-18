# Demo shot list

All screenshots are actual page captures. No chart, amount or model response is drawn
into them. The capture manifest records hashes, source datasets and actual values.

| Asset | Content | Provenance |
|---|---|---|
| `assets/main-dashboard.png` | Overview metrics and risk/outlook cards | Bundled fictional history; explicit opening cash 2,500 |
| `assets/cash-flow-forecast.png` | History plus 30-day projection | Same unchanged fictional history |
| `assets/anomaly-alerts.png` | Genuinely flagged review queue | Separate existing labeled benchmark, default calibrated amount review |
| `assets/anomaly-explanation.png` | Selected injected transaction and prior-history comparison | Same benchmark; label and actual flag verified separately |
| `assets/scenario-simulator.png` | 500 emergency expense, cash difference and comparison chart | Original demo plus explicitly entered hypothetical expense |
| `assets/gemma-insights.png` | Real locally generated, validated explanations | Installed Gemma 3 on the demo/scenario evidence |
| `assets/model-evaluation.png` | Actual calibrated comparison results | Existing synthetic evaluation protocol |
| `assets/cashguard-demo.mp4` | Real-time browser demonstration | Actual CDP screencast; no audio; English subtitle track |
| `assets/cashguard-demo-captions.srt` | Matching scene captions | Editorial explanations, not generated financial values |

The synthetic benchmark CSV is included for exact reproduction. It is generated from
the existing train/calibration/final partitions without changing amounts. The regular
demo has zero default alerts; do not imply it contains the separately shown injections.
The benchmark's live review results differ from the frozen final-holdout evaluation
because the live engine uses rolling history; distinguish those two measurements.

Optional MLflow screenshots were not required for the core demonstration. The actual
Model Evaluation page supplies the technical proof without revealing a local database
path or experiment-store filesystem layout.
