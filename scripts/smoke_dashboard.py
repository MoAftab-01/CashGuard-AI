"""Exercise the running local Streamlit protocol; this is not visual browser QA.

Uses the websockets dependency already in requirements.lock.txt and the verified
Streamlit 1.66 widget protocol. Only fictional demo inputs are submitted. No AI
inference or model download is requested: the fallback probe selects a missing model.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ClientState_pb2 import ClientState
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


async def smoke(port):
    results = {"browser_visual_qa": False, "transport": "Live local Streamlit WebSocket", "runs": []}
    async with websockets.connect(f"ws://127.0.0.1:{port}/_stcore/stream", subprotocols=["streamlit"],
                                   origin=f"http://127.0.0.1:{port}", open_timeout=5, max_size=10 * 1024 * 1024) as connection:
        widgets, core = {}, {}

        async def run(label, updates=None):
            state = ClientState()
            for name, value in {**core, **(updates or {})}.items():
                kind, identity = widgets[name]
                widget = state.widget_states.widgets.add()
                widget.id = identity
                if kind == "button":
                    widget.trigger_value = bool(value)
                elif kind == "slider":
                    widget.double_array_value.data.extend([float(value)])
                else:
                    widget.string_value = str(value)
            request = BackMsg()
            request.rerun_script.CopyFrom(state)
            await connection.send(request.SerializeToString())
            headings, text, metrics = [], [], {}
            for _ in range(1500):
                raw = await asyncio.wait_for(connection.recv(), timeout=45)
                message = ForwardMsg.FromString(raw)
                kind = message.WhichOneof("type")
                if kind == "delta" and message.delta.HasField("new_element"):
                    element = message.delta.new_element
                    if element.HasField("exception"):
                        raise RuntimeError(f"Live app exception during {label}: {element.exception.type}: {element.exception.message}")
                    for widget_kind in ("radio", "text_input", "selectbox", "button", "slider"):
                        if element.HasField(widget_kind):
                            widget = getattr(element, widget_kind)
                            widgets[widget.label] = (widget_kind, widget.id)
                    if element.HasField("heading"):
                        headings.append(element.heading.body)
                    for field in ("markdown", "alert"):
                        if element.HasField(field):
                            text.append(getattr(element, field).body)
                    if element.HasField("metric"):
                        metrics[element.metric.label] = element.metric.body
                if kind == "script_finished":
                    if message.script_finished != ForwardMsg.FINISHED_SUCCESSFULLY:
                        raise RuntimeError(f"Script did not finish successfully during {label}")
                    results["runs"].append(dict(label=label, headings=headings, metrics=metrics, exceptions=0))
                    print(f"PASS: {label}", flush=True)
                    return headings, text, metrics
            raise RuntimeError("Live app did not signal script completion")

        headings, _, _ = await run("Startup")
        if "CashGuard AI" not in headings:
            raise RuntimeError("Port is not serving the expected CashGuard dashboard")
        core.update({"Opening balance": "2500.00", "Navigation": "Overview"})
        _, _, metrics = await run("Overview metrics")
        assert metrics["Estimated cash balance"] == "USD 16,268.23"
        for page in ("Transactions", "Cash Flow Forecast", "Anomaly Detection", "Risk Analysis", "Scenario Simulator"):
            core["Navigation"] = page
            headings, _, _ = await run(page)
            assert page in headings
        _, _, metrics = await run("Scenario income stress", {"Income reduction (%)": 20})
        assert metrics["Closing balance change"] != "USD 0.00"
        core["Navigation"] = "Model Evaluation"
        await run("Evaluation page")
        await run("Forecast evaluation", {"Run forecast evaluation": True})
        await run("Candidate final evaluation", {"Run calibrated candidate comparison": True})
        core["Navigation"] = "Data quality"
        await run("Data quality")
        core["Navigation"] = "AI Insights"
        await run("AI Insights without generation")
        # Missing model causes metadata-only rejection before financial inference.
        missing = "cashguard-unavailable-local-smoke:latest"
        _, unavailable_text, _ = await run("Unavailable local model", {"Local model": missing})
        # Check metadata failure before clicking Generate, so an unexpected local
        # model alias collision cannot turn this probe into real inference.
        assert any("not installed" in line or "Cannot connect" in line for line in unavailable_text)
        _, text, _ = await run("Deterministic fallback", {"Local model": missing, "Generate AI Insights": True})
        assert any("not installed" in line or "Cannot connect" in line for line in text)
        results["inference_sent_to_model"] = False
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--output", type=Path, default=Path("reports/phase6/dashboard_smoke.json"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Use a valid local port")
    result = asyncio.run(smoke(args.port))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved live execution checks: {args.output}; visual appearance requires separate browser QA")


if __name__ == "__main__":
    main()
