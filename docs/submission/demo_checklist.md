# Demo capture and publication checklist

- [x] Use only bundled/explicitly labeled synthetic data.
- [x] Capture app content in an isolated browser profile, without personal tabs or address bars.
- [x] Enter opening cash explicitly and label reconstructed balances as estimates.
- [x] Use the existing labeled benchmark for a genuinely detected injection.
- [x] Restore the standard demo before the emergency scenario and Gemma scenes.
- [x] Observe real local generation and validated explanations; never paste a fake response.
- [x] Keep screenshots unedited; review them visually before sharing.
- [x] Verify the final 2:48 MP4 decodes completely and includes the English caption track.
- [ ] Owner reviews the final recording and adds optional human narration.
- [ ] Upload the actual MP4 to a video host, with public or unlisted access for judges.
- [ ] Open the video URL in a signed-out/private browser and verify playback/captions.
- [ ] Replace the DEV draft's video-publication note with that verified URL/embed.

## Exact manual alternative

1. Run `python -m streamlit run app.py` from the existing workspace. Start local
   Ollama with installed `gemma3:4b`; do not download a new model during recording.
2. Open only the localhost app in a clean browser window. Hide bookmarks and personal
   tabs. Disable notification popups. Use a 1440×1000 or similarly readable desktop view.
3. Windows: open Snipping Tool's video recorder and select only the application viewport;
   alternatively use a recorder already installed on your machine. macOS/Linux users
   can use an existing screen recorder with the same viewport-only boundary.
4. Follow `demo_script.md`. Select Synthetic demo → Start demo. For the anomaly scene,
   upload `assets/synthetic-anomaly-benchmark.csv`, keep the default review engine,
   and use the transaction identified in `capture-manifest.json`. Return to Synthetic
   demo → Start demo before the scenario. Enter emergency expense `500.00`.
5. Click Generate AI Insights and wait for actual validated output. If fallback occurs,
   explain the failure or retry; do not label fallback as Gemma success.
6. Stop after roughly 2–3 minutes. Review the entire recording for readability,
   unwanted paths, real generation, negative cash delta direction and dataset changes.
7. Upload only after review. Add the real video URL to the draft; never use localhost
   as the judges' demo URL. No external upload is performed by the capture script.

`scripts/capture_submission.py` can reproduce assets against a dedicated loopback
DevTools profile. It must never attach to a personal browser profile. Optional FFmpeg
is a capture tool, not an application dependency; raw frames remain under ignored `var/`.
