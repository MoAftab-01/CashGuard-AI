"""Capture real localhost UI assets and optional CDP screencast; never edit amounts.

Requires an isolated Chromium/Edge profile exposing a loopback DevTools endpoint.
The optional FFmpeg encoder is a local capture tool, not an application dependency.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from time import monotonic

import pandas as pd

from config import SAMPLE_DATA_PATH, TRANSACTION_COLUMNS
from scripts.browser_qa import BrowserQA
from src.anomaly_experiments import anomaly_partition
from src.dashboard_service import dashboard_anomalies


class RecordingBrowser(BrowserQA):
    def __init__(self, endpoint, directory):
        super().__init__(endpoint)
        self.directory, self.frames, self.scenes = directory, [], []
        self.recording, self.started = False, None

    async def call(self, method, **params):
        self.sequence += 1
        identity = self.sequence
        await self.socket.send(json.dumps(dict(id=identity, method=method, params=params)))
        while True:
            reply = json.loads(await asyncio.wait_for(self.socket.recv(), timeout=45))
            if reply.get("method") == "Page.screencastFrame":
                event = reply["params"]
                if self.recording:
                    path = self.directory / f"frame-{len(self.frames):06d}.jpg"
                    path.write_bytes(base64.b64decode(event["data"]))
                    self.frames.append((path.name, monotonic() - self.started))
                self.sequence += 1
                await self.socket.send(json.dumps(dict(id=self.sequence, method="Page.screencastFrameAck",
                                                      params={"sessionId": event["sessionId"]})))
            if reply.get("method") == "Runtime.exceptionThrown":
                self.errors.append(reply["params"])
            if reply.get("id") == identity:
                if "error" in reply:
                    raise RuntimeError(f"Capture protocol failed: {method}")
                return reply.get("result", {})

    async def start_recording(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.started, self.recording = monotonic(), True
        await self.call("Page.startScreencast", format="jpeg", quality=85,
                        maxWidth=1440, maxHeight=1000, everyNthFrame=1)

    async def pause(self, seconds):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            await self.evaluate("document.readyState")
            await asyncio.sleep(.2)

    def scene(self, name, caption):
        self.scenes.append({"scene": name, "start_seconds": monotonic() - self.started if self.started else 0,
                            "caption": caption})
        print("SCENE: " + name, flush=True)


def prepare_benchmark(output):
    partitions = [anomaly_partition(name) for name in ("train", "calibration", "final")]
    data = pd.concat([part.data for part in partitions], ignore_index=True)
    labels = pd.concat([part.labels for part in partitions], ignore_index=True).set_index("transaction_id")
    path = output / "synthetic-anomaly-benchmark.csv"
    data[list(TRANSACTION_COLUMNS)].to_csv(path, index=False, lineterminator="\n")
    result = dashboard_anomalies(data)
    flagged = result.data.loc[result.data.is_anomaly.fillna(False)]
    injected = flagged.loc[flagged.transaction_id.map(labels.is_injected) & (flagged.amount_cents < 0)]
    if injected.empty:
        raise RuntimeError("No injected synthetic transaction was genuinely flagged; do not fake an alert")
    row = injected.iloc[0]
    return path, {"origin": "Existing phase6 chronological synthetic generator; no amount modifications",
                  "rows": len(data), "engine": "Calibrated amount review", "scored": result.scored_count,
                  "flagged": result.anomaly_count, "selected_label_is_injected": True,
                  "selected_transaction": str(row.date) + " | " + row.description,
                  "selected_amount_cents": int(row.amount_cents), "selected_explanation": row.explanation,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def encode(browser, executable, output):
    finish = monotonic() - browser.started
    frames = browser.frames
    if len(frames) < 10 or finish < 120:
        raise RuntimeError("Recording is incomplete; do not present it as a full demo")
    concat = ["ffconcat version 1.0"]
    for index, (filename, instant) in enumerate(frames):
        following = frames[index + 1][1] if index + 1 < len(frames) else finish
        concat += [f"file '{filename}'", f"duration {max(.001, following - instant):.6f}"]
    concat += [f"file '{frames[-1][0]}'"]
    listing = browser.directory / "frames.txt"
    listing.write_text("\n".join(concat), encoding="utf-8")
    def stamp(seconds):
        millis = round(seconds * 1000)
        return f"{millis//3600000:02d}:{millis//60000%60:02d}:{millis//1000%60:02d},{millis%1000:03d}"
    subtitles = []
    for index, scene in enumerate(browser.scenes):
        end = browser.scenes[index + 1]["start_seconds"] if index + 1 < len(browser.scenes) else finish
        subtitles += [str(index + 1), f"{stamp(scene['start_seconds'])} --> {stamp(end)}", scene["caption"], ""]
    subtitle_path = output / "cashguard-demo-captions.srt"
    subtitle_path.write_text("\n".join(subtitles), encoding="utf-8")
    video = output / "cashguard-demo.mp4"
    subprocess.run([executable, "-y", "-loglevel", "error", "-safe", "0", "-f", "concat", "-i", str(listing),
                    "-i", str(subtitle_path), "-map", "0:v", "-map", "1:s", "-vf", "fps=12,format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=eng", "-disposition:s:0", "default", "-map_metadata", "-1",
                    "-movflags", "+faststart", str(video)], check=True)
    return {"file": video.name, "seconds": finish, "frames": len(frames), "audio": False,
            "caption_track": True, "source": "Actual browser CDP screencast; original event timing, no generated UI",
            "sha256": hashlib.sha256(video.read_bytes()).hexdigest()}


async def capture(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    benchmark, benchmark_evidence = prepare_benchmark(output)
    evidence = {"transport": "Actual isolated Edge/Chromium browser via CDP", "synthetic_data_only": True,
                "regular_demo_sha256": hashlib.sha256(SAMPLE_DATA_PATH.read_bytes()).hexdigest(),
                "benchmark": benchmark_evidence, "screenshots": []}
    async with RecordingBrowser(args.endpoint, args.frames) as browser:
        await browser.open(width=1440, height=1000)
        await browser.sidebar(True)
        await browser.click("Clear session data")
        if args.ffmpeg:
            await browser.start_recording()
        async def pause(seconds):
            if args.ffmpeg:
                await browser.pause(seconds)
        async def shot(name, origin, scroll=0):
            await browser.evaluate(f"document.querySelector('[data-testid=stMain]').scrollTop={int(scroll)}")
            await browser.evaluate("document.querySelector('[data-testid=stSidebarContent]')?.scrollTo(0,0)")
            await browser.call("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=5)
            await browser.pause(.3)
            text = await browser.text()
            if any(marker in text for marker in (":\\Users\\", ":\\placement_personal\\", "Traceback")):
                raise RuntimeError("Private path or traceback present; screenshot blocked")
            path = output / (name + ".png")
            await browser.screenshot(path)
            evidence["screenshots"].append({"file": path.name, "data_origin": origin,
                                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        browser.scene("Problem", "A freelancer can have income on paper and still run short before the next payment. CashGuard explores that gap locally.")
        await pause(10)
        await browser.click("Start demo")
        browser.scene("Overview", "Fictional demo data. Opening cash is an explicit assumption; reconstructed balances are estimates, not bank balances.")
        evidence["overview"] = await browser.metrics()
        assert evidence["overview"]["Estimated cash balance"] == "USD 16,268.23"
        await shot("main-dashboard", "Bundled synthetic_transactions.csv; explicit opening cash 2500.00")
        await pause(12)
        await browser.navigate("Cash Flow Forecast")
        browser.scene("Forecast", "The existing engine projects recurring events and residual cash flow over 30 days. These are conditional estimates, not guarantees.")
        evidence["forecast"] = await browser.metrics()
        await shot("cash-flow-forecast", "Bundled synthetic demo")
        await pause(13)
        await browser.click("Forecast assumptions and supporting patterns")
        await browser.evaluate("document.querySelector('[data-testid=stMain]').scrollTop=550")
        await pause(7)
        await browser.sidebar(True)
        await browser.click("Upload CSV")
        await browser.upload(benchmark)
        await browser.navigate("Anomaly Detection")
        browser.scene("Anomaly review", "This separate labeled synthetic benchmark contains deliberate amount changes. The default engine genuinely flags this example; unusual does not mean fraud.")
        assert int((await browser.metrics())["Flagged unusual"]) > 0
        await shot("anomaly-alerts", "Existing chronological synthetic benchmark; selected default engine")
        await pause(7)
        await browser.click("Compare a reviewed transaction with its training history")
        await browser.select("Transaction to compare", benchmark_evidence["selected_transaction"])
        # Streamlit recreates a collapsed expander after this selectbox rerun.
        await browser.click("Compare a reviewed transaction with its training history")
        assert "Reference:" in await browser.text()
        await browser.evaluate("(() => {const e=[...document.querySelectorAll('summary')].find(e=>e.innerText.includes('Compare a reviewed'));e?.scrollIntoView({block:'start'})})()")
        await browser.pause(.5)
        await shot("anomaly-explanation", "Known injected and genuinely flagged synthetic transaction",
                   scroll=await browser.evaluate("document.querySelector('[data-testid=stMain]').scrollTop"))
        await pause(12)
        await browser.sidebar(True)
        await browser.click("Synthetic demo")
        await browser.click("Start demo")
        await browser.navigate("Scenario Simulator")
        browser.scene("Scenario", "Back to the standard demo. A hypothetical emergency expense changes the same event ledger; it does not change recorded history.")
        await browser.input("Emergency expense", "500.00")
        evidence["scenario"] = await browser.metrics()
        assert evidence["scenario"]["Closing balance change"] == "USD -500.00"
        assert "-500.00 USD" in await browser.text(), "Server has not loaded the corrected negative delta formatting"
        await shot("scenario-simulator", "Bundled synthetic demo plus explicitly entered hypothetical 500.00 emergency", scroll=450)
        await pause(18)
        await browser.navigate("AI Insights")
        browser.scene("Local Gemma", "Gemma 3 runs through local Ollama on computed evidence. It explains the analytics; Python still calculates every financial amount.")
        await browser.input("Local model", "gemma3:4b")
        await browser.evaluate("[...document.querySelectorAll('button')].find(e=>e.innerText==='Generate AI Insights').click()")
        await browser.wait("!!document.querySelector('[data-testid=stSpinner]')", timeout=10)
        await browser.settle()
        assert "AI-generated explanations" in await browser.text(), "Real inference did not produce validated output"
        evidence["gemma"] = {"source": "ai", "model": "gemma3:4b", "mocked": False}
        await shot("gemma-insights", "Actual local inference on bundled synthetic evidence and emergency scenario", scroll=250)
        await pause(10)
        await browser.navigate("Model Evaluation")
        browser.scene("Technical proof", "Calibration is separate from the synthetic final holdout. Benchmarks support reproducibility, not claims of real-world accuracy. Hosted CI is not yet verified.")
        await browser.click("Run calibrated candidate comparison")
        assert "Selected on calibration: context_stat" in await browser.text()
        await browser.evaluate("(() => {const e=[...document.querySelectorAll('p')].find(e=>e.innerText.includes('Selected on calibration:'));e?.scrollIntoView({block:'start'})})()")
        await browser.pause(.5)
        await shot("model-evaluation", "Existing independently labeled synthetic evaluation",
                   scroll=await browser.evaluate("document.querySelector('[data-testid=stMain]').scrollTop"))
        await pause(12)
        await browser.navigate("Overview")
        browser.scene("Closing", "A local early-warning workspace for cash-flow questions. No bank connection, financial-advice service, fraud confirmation, customers or revenue are claimed.")
        await pause(10)
        evidence["runtime_errors"] = browser.errors
        if args.ffmpeg:
            await browser.call("Page.stopScreencast")
            browser.recording = False
            evidence["video"] = encode(browser, args.ffmpeg, output)
            evidence["scenes"] = browser.scenes
    (output / "capture-manifest.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"screenshots": len(evidence['screenshots']), "video": evidence.get("video")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:9223")
    parser.add_argument("--output", type=Path, default=Path("docs/submission/assets"))
    parser.add_argument("--frames", type=Path, default=Path("var/phase9/capture-frames"))
    parser.add_argument("--ffmpeg", help="Optional local FFmpeg executable; enables real-time screencast recording")
    args = parser.parse_args()
    # Keep the debugging connection local; never attach to a personal browser.
    from src.settings import loopback_url
    args.endpoint = loopback_url(args.endpoint)
    asyncio.run(capture(args))


if __name__ == "__main__":
    main()
