"""Local headless-browser QA via existing DevTools/WebSocket dependencies.

Attach only to an isolated browser profile launched for localhost testing. This
helper adds no application dependency and never uses a personal browser profile.
"""

import argparse
import asyncio
import base64
import json
from pathlib import Path
from time import monotonic

import requests
import websockets


class BrowserQA:
    def __init__(self, endpoint="http://127.0.0.1:9222"):
        self.endpoint = endpoint
        self.sequence = 0
        self.errors = []

    async def __aenter__(self):
        session = requests.Session()
        session.trust_env = False
        pages = session.get(f"{self.endpoint}/json/list", timeout=5).json()
        session.close()
        page = next(page for page in pages if page["type"] == "page")
        self.socket = await websockets.connect(page["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024)
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        return self

    async def __aexit__(self, *_):
        await self.socket.close()

    async def call(self, method, **params):
        self.sequence += 1
        sequence = self.sequence
        await self.socket.send(json.dumps(dict(id=sequence, method=method, params=params)))
        while True:
            result = json.loads(await asyncio.wait_for(self.socket.recv(), timeout=45))
            if result.get("method") == "Runtime.exceptionThrown":
                self.errors.append(result["params"])
            if result.get("id") == sequence:
                if "error" in result:
                    raise RuntimeError(f"{method}: {result['error']}")
                return result.get("result", {})

    async def evaluate(self, expression):
        result = await self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return result.get("result", {}).get("value")

    async def wait(self, expression, timeout=30):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if await self.evaluate(expression):
                return
            await asyncio.sleep(.15)
        raise TimeoutError(f"Browser condition did not become true: {expression}")

    async def settle(self):
        await self.wait("!document.querySelector('[data-testid=\"stStatusWidget\"]') && !document.querySelector('[data-testid=\"stSpinner\"]')")
        await asyncio.sleep(.4)
        await self.wait("document.querySelector('[data-testid=\"stApp\"]')?.getAttribute('data-test-script-state') !== 'running'")
        await self.wait("!document.querySelector('[data-testid=\"stSkeleton\"]')", timeout=30)
        await self.wait("!document.querySelector('[data-stale=true]')")
        # A completed Python rerun can precede React removing stale lower-page nodes.
        await self.evaluate("""new Promise(resolve=>{let timer; const root=document.querySelector('[data-testid=stMain]');const observer=new MutationObserver(reset);function done(){observer.disconnect();resolve(true)}function reset(){clearTimeout(timer);timer=setTimeout(done,800)}observer.observe(root,{childList:true,subtree:true,characterData:true});reset()})""")
        exception = await self.evaluate("document.querySelector('[data-testid=\"stException\"]')?.innerText || ''")
        if exception:
            raise RuntimeError(exception)

    async def open(self, url="http://127.0.0.1:8501", width=1440, height=1000, dark=False):
        await self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
        await self.call("Emulation.setEmulatedMedia", features=[dict(name="prefers-color-scheme", value="dark" if dark else "light")])
        await self.call("Page.navigate", url=url)
        await asyncio.sleep(.5)
        await self.wait("document.readyState === 'complete' && ([...document.querySelectorAll('[data-testid=\"stTextInput\"] label')].some(e=>e.innerText.trim()==='Opening balance') || [...document.querySelectorAll('[data-testid=stSidebar] button')].some(e=>e.innerText.trim()==='Start demo'))")
        await self.settle()

    async def sidebar(self, opened=True):
        collapsed = await self.evaluate("document.querySelector('[data-testid=\"stSidebar\"]')?.getAttribute('data-collapsed') === 'true'")
        if collapsed == opened:
            selector = '[data-testid="stExpandSidebarButton"]' if opened else 'button[aria-label="Collapse sidebar"]'
            found = await self.evaluate("(() => {const e=document.querySelector(" + json.dumps(selector) + ");if(!e)return false;e.click();return true})()")
            if not found:
                raise RuntimeError("Sidebar toggle was not found")
            await asyncio.sleep(.3)

    async def expand(self, label):
        await self.evaluate("(() => {const e=[...document.querySelectorAll('details')].find(e=>e.querySelector('summary')?.innerText.includes(" + json.dumps(label) + "));if(e&&!e.open)e.querySelector('summary').click()})()")
        await asyncio.sleep(.2)
        await self.settle()

    async def input(self, label, value):
        # Real input events pass through React's controlled input handlers.
        panels = {"Opening balance": "Cash settings", "Minimum cash threshold": "Cash settings",
                  "Emergency expense": "Customize this plan", "Payment delay (days)": "Customize this plan",
                  "Local model": "Model settings", "Model": "Model settings"}
        if label in panels:
            await self.sidebar(label in {"Opening balance", "Minimum cash threshold"})
            await self.expand(panels[label])
        in_sidebar = await self.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] label')].some(e=>e.innerText.trim()===" + json.dumps(label) + ")")
        await self.sidebar(in_sidebar)
        found = await self.evaluate("""(() => {const e=[...document.querySelectorAll('[data-testid="stTextInput"], [data-testid="stNumberInput"]')].find(e=>e.querySelector('label')?.innerText.trim()===""" + json.dumps(label) + """);if(!e)return false; const i=e.querySelector('input');i.scrollIntoView({block:'center'});i.focus();i.select();return true})()""")
        if not found:
            raise RuntimeError(f"Input not found: {label}")
        await self.call("Input.insertText", text=str(value))
        await self.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await self.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await asyncio.sleep(.25)
        await self.settle()

    async def click(self, label):
        expression = """(() => {const label=""" + json.dumps(label) + """;const e=[...document.querySelectorAll('button,label,summary')].find(e=>e.innerText.trim()===label || e.querySelector('p')?.innerText.trim()===label);if(!e)return false;e.scrollIntoView({block:'center'});e.click();return true})()"""
        if not await self.evaluate(expression):
            raise RuntimeError(f"Control not found: {label}")
        await asyncio.sleep(.35)
        await self.settle()

    async def navigate(self, page):
        await self.sidebar(True)
        from src.ui.navigation import VIEWS
        modern = await self.evaluate("[...document.querySelectorAll('button')].some(e=>e.innerText.trim()==='AI Assistant')")
        title = VIEWS[page][1] if modern else page
        if modern:
            await self.evaluate("(() => {const e=[...document.querySelectorAll('[data-testid=stSidebar] details')].find(e=>e.querySelector('summary')?.innerText.includes('Advanced'));if(e&&!e.open)e.querySelector('summary').click()})()")
            await self.evaluate("(() => {const e=[...document.querySelectorAll('[data-testid=stSidebar] [role=radiogroup] label')].find(e=>e.innerText.trim()===" + json.dumps(title) + ");if(!e)throw Error('Missing view');e.click()})()")
        else:
            await self.click(page)
        await self.wait("[...document.querySelectorAll('h1')].some(e=>e.innerText===" + json.dumps(title) + ")")
        await self.settle()
        if await self.evaluate("window.innerWidth < 700"):
            await self.sidebar(False)

    async def screenshot(self, path):
        image = await self.call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(image["data"]))

    async def select(self, label, value):
        if label == "Anomaly review engine":
            await self.sidebar(True)
            await self.expand("Review method")
        elif label in {"Direction"}:
            await self.expand("More filters")
        in_sidebar = await self.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] label')].some(e=>e.innerText.trim()===" + json.dumps(label) + ")")
        await self.sidebar(in_sidebar)
        point = await self.evaluate("""(() => {const e=[...document.querySelectorAll('[data-testid=stSelectbox]')].find(e=>e.querySelector('label')?.innerText.trim()===""" + json.dumps(label) + """);if(!e)throw Error('Missing select'); const i=e.querySelector('button[aria-haspopup=listbox]');i.scrollIntoView({block:'center'});const r=i.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
        await self.mouse(point)
        await self.wait("!!document.querySelector('[role=option]')")
        point = await self.evaluate("""(() => {const e=[...document.querySelectorAll('[role=option]')].find(e=>e.innerText.trim()===""" + json.dumps(value) + """);if(!e)throw Error('Missing option');e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()""")
        await self.mouse(point)
        await asyncio.sleep(.3)
        await self.settle()

    async def mouse(self, point):
        await self.call("Input.dispatchMouseEvent", type="mouseMoved", **point)
        await self.call("Input.dispatchMouseEvent", type="mousePressed", button="left", clickCount=1, **point)
        await self.call("Input.dispatchMouseEvent", type="mouseReleased", button="left", clickCount=1, **point)

    async def slider(self, label, steps):
        await self.sidebar(False)
        await self.expand("Customize this plan")
        await self.evaluate("""(() => {const e=[...document.querySelectorAll('[data-testid=stSlider]')].find(e=>e.querySelector('label')?.innerText.trim()===""" + json.dumps(label) + """);const i=e.querySelector('input[type=range]');e.scrollIntoView({block:'center'});i.focus()})()""")
        for key, code in [("Home", 36)] + [("ArrowRight", 39)] * steps:
            await self.call("Input.dispatchKeyEvent", type="keyDown", key=key, windowsVirtualKeyCode=code)
            await self.call("Input.dispatchKeyEvent", type="keyUp", key=key, windowsVirtualKeyCode=code)
        await asyncio.sleep(.4)
        await self.settle()

    async def upload(self, path):
        await self.sidebar(True)
        root = await self.call("DOM.getDocument")
        node = await self.call("DOM.querySelector", nodeId=root["root"]["nodeId"], selector="input[type=file]")
        await self.call("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[str(Path(path).resolve())])
        await asyncio.sleep(.5)
        await self.settle()

    async def metrics(self):
        return await self.evaluate("Object.fromEntries([...document.querySelectorAll('[data-testid=stMetric]')].map(e=>[e.querySelector('[data-testid=stMetricLabel]').innerText,e.querySelector('[data-testid=stMetricValue]').innerText]))")

    async def text(self):
        return await self.evaluate("document.querySelector('[data-testid=stMain]').innerText")

    async def snapshot(self, directory, name):
        """Capture internally scrolling Streamlit content, not just document height."""
        await self.evaluate("document.querySelector('[data-testid=stMain]').scrollTop=0")
        await self.evaluate("document.querySelector('[data-testid=stSidebarContent]')?.scrollTo(0,0)")
        await asyncio.sleep(.2)
        layout = await self.evaluate("""(() => {const m=document.querySelector('[data-testid=stMain]');return {width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,mainWidth:m.clientWidth,mainScrollWidth:m.scrollWidth,mainHeight:m.scrollHeight,background:getComputedStyle(document.querySelector('[data-testid=stApp]')).backgroundColor,charts:document.querySelectorAll('.js-plotly-plot').length,metrics:[...document.querySelectorAll('[data-testid=stMetric]')].map(e=>({label:e.querySelector('[data-testid=stMetricLabel]').innerText,value:e.querySelector('[data-testid=stMetricValue]').innerText})),clippedMetricValues:[...document.querySelectorAll('[data-testid=stMetricValue] > div')].filter(e=>e.scrollWidth>e.clientWidth+2).length}})()""")
        layout["chartChecks"] = await self.evaluate("""[...document.querySelectorAll('.js-plotly-plot')].map(e=>{const r=e.getBoundingClientRect(),t=e.querySelector('.gtitle')?.getBoundingClientRect(),l=e.querySelector('.legend')?.getBoundingClientRect();return {title:e._fullLayout.title.text,titleInside:!t||(t.left>=r.left-2&&t.top>=r.top-2&&t.right<=r.right+2&&t.bottom<=r.bottom+2),legendInside:!l||(l.left>=r.left-2&&l.top>=r.top-2&&l.right<=r.right+2&&l.bottom<=r.bottom+2),titleLegendOverlap:!!(t&&l&&t.left<l.right&&l.left<t.right&&t.top<l.bottom&&l.top<t.bottom)}})""")
        layout["screenshots"] = []
        height = layout["height"]
        offsets = list(range(0, layout["mainHeight"], max(height - 120, 1)))
        for index, offset in enumerate(offsets):
            await self.evaluate(f"document.querySelector('[data-testid=stMain]').scrollTop={offset}")
            await asyncio.sleep(.15)
            path = Path(directory) / f"{name}-{index}.png"
            await self.screenshot(path)
            layout["screenshots"].append(str(path))
        return layout


async def matrix(args):
    from app import PAGES
    manifest = {}
    async with BrowserQA() as browser:
        for width, height, dark in ((1440, 1000, False), (390, 844, False), (1440, 1000, True), (390, 844, True)):
            mode = f"{'mobile' if width < 600 else 'desktop'}-{'dark' if dark else 'light'}"
            await browser.open(width=width, height=height, dark=dark)
            await browser.sidebar(True)
            await browser.click("Start demo")
            for page in PAGES:
                await browser.navigate(page)
                assert await browser.evaluate("document.querySelector('[data-testid=stMain]').scrollTop") == 0, f"Navigation did not open {page} at the top"
                name = f"{mode}-{page.lower().replace(' ', '-')}"
                layout = await browser.snapshot(args.directory, name)
                manifest[name] = layout
                layout["navigation_starts_at_top"] = True
                print(json.dumps(dict(page=page, mode=mode, charts=layout['charts'], overflow=layout['mainScrollWidth'] > layout['mainWidth']+2, clips=layout['clippedMetricValues'])), flush=True)
        manifest["runtime_errors"] = browser.errors
    Path(args.directory, "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


async def journeys(args):
    """Explicit local-only UI interactions, including real Gemma on fictional data."""
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    fixture_dir = directory.parent / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    valid = fixture_dir / "valid.csv"
    invalid = fixture_dir / "invalid.csv"
    valid.write_text("date,description,amount,category,transaction_id\n2026-01-01,Fictional income,100.00,Income,QA-1\n2026-01-02,Fictional expense,-25.00,Other,QA-2\n", encoding="utf-8")
    invalid.write_text(valid.read_text() + "2026-01-03,Malformed amount,not-money,Other,QA-3\n", encoding="utf-8")
    report = {"transport": "Actual Edge browser DOM/CDP", "fictional_data_only": True, "checks": []}

    def record(name, **evidence):
        report["checks"].append(dict(journey=name, passed=True, **evidence))
        (directory.parent / "browser_journeys.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"PASS: {name}", flush=True)

    async with BrowserQA() as browser:
        await browser.open()
        await browser.sidebar(True)
        await browser.click("Clear session data")
        assert "Get started with your cash-flow workspace" in await browser.text()
        assert not await browser.metrics()
        await browser.snapshot(directory, "journey-onboarding")
        record("First-run onboarding", metrics_absent=True)
        await browser.click("Start demo")
        baseline = await browser.metrics()
        assert baseline["Estimated cash balance"] == "USD 16,268.23"
        record("Load synthetic dataset and review metrics", metrics=baseline)
        await browser.navigate("Transactions")
        await browser.input("Search description", "no-such-transaction-qa")
        assert "No transactions match these filters" in await browser.text()
        await browser.snapshot(directory, "journey-empty-filter")
        await browser.input("Search description", "salary")
        await browser.select("Direction", "Income")
        await browser.navigate("Overview")
        assert await browser.metrics() == baseline
        await browser.navigate("Transactions")
        assert await browser.evaluate("document.querySelector('input[aria-label=\"Search description\"]').value") == "salary"
        record("Transaction filters and cross-page consistency", overview_unchanged=True, search_retained="salary")
        await browser.navigate("Cash Flow Forecast")
        forecast = await browser.metrics()
        assert forecast["Estimated balance at cutoff"] == baseline["Estimated cash balance"]
        await browser.click("Forecast assumptions and supporting patterns")
        assert "recurring" in (await browser.text()).lower()
        await browser.snapshot(directory, "journey-forecast-assumptions")
        record("Generate 30-day cash-flow forecast", metrics=forecast)
        await browser.input("Minimum cash threshold", "999999.00")
        changed = await browser.metrics()
        assert changed["Days below threshold"] == "30"
        assert changed["Projected closing balance"] == forecast["Projected closing balance"]
        await browser.snapshot(directory, "journey-shortfalls")
        await browser.input("Minimum cash threshold", "500.00")
        record("Change minimum cash threshold", breach_days=30, forecast_cash_unchanged=True)
        await browser.navigate("Scenario Simulator")
        await browser.input("Emergency expense", "500.00")
        emergency = await browser.metrics()
        assert emergency["Closing balance change"] == "USD -500.00"
        record("Simulate emergency expense", metrics=emergency)
        await browser.slider("Income reduction (%)", 4)
        stressed = await browser.metrics()
        assert stressed["Closing balance change"] not in {"USD 0.00", "USD -500.00"}
        await browser.snapshot(directory, "journey-income-stress")
        record("Simulate reduced income", metrics=stressed)
        await browser.navigate("Anomaly Detection")
        assert (await browser.metrics())["Flagged unusual"] == "0"
        assert "Zero alerts does not mean zero financial risk" in await browser.text()
        await browser.select("Review status", "All scored")
        await browser.click("Compare a reviewed transaction with its training history")
        assert "Reference:" in await browser.text()
        await browser.snapshot(directory, "journey-anomaly-comparison")
        await browser.select("Anomaly review engine", "Legacy Isolation Forest")
        await browser.select("Review status", "Flagged unusual")
        assert int((await browser.metrics())["Flagged unusual"]) > 0
        await browser.snapshot(directory, "journey-legacy-alerts")
        legacy = await browser.metrics()
        await browser.select("Anomaly review engine", "Calibrated amount review")
        record("Inspect anomaly alerts and historical explanations", legacy_metrics=legacy, default_zero_alert_warning=True)
        await browser.navigate("AI Insights")
        assert "selected model is available" in await browser.text()
        await browser.evaluate("[...document.querySelectorAll('button')].find(e=>e.innerText==='Generate AI Insights').click()")
        await browser.wait("!!document.querySelector('[data-testid=stSpinner]')", timeout=10)
        await browser.screenshot(directory / "journey-gemma-loading.png")
        await browser.settle()
        assert "AI-generated explanations" in await browser.text(), await browser.text()
        await browser.snapshot(directory, "journey-gemma-generated")
        record("Generate real local Gemma insights", source="ai", model="gemma3:4b", loading_indicator_observed=True)
        await browser.input("Local model", "cashguard-unavailable-local-phase7:latest")
        assert "not installed" in await browser.text()
        await browser.click("Generate AI Insights")
        assert "Deterministic fallback" in await browser.text()
        await browser.snapshot(directory, "journey-model-fallback")
        await browser.input("Local model", "gemma3:4b")
        record("Unavailable-model fallback", source="deterministic", calculated_summaries_retained=True)
        await browser.navigate("Model Evaluation")
        await browser.click("Run forecast evaluation")
        await browser.click("Run synthetic anomaly evaluation")
        await browser.click("Run calibrated candidate comparison")
        assert "Selected on calibration: context_stat" in await browser.text()
        chart_count = await browser.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        assert chart_count == 5
        await browser.snapshot(directory, "journey-evaluation-results")
        record("Inspect all model evaluation results", charts=chart_count)
        await browser.navigate("Overview")
        assert await browser.metrics() == baseline
        await browser.sidebar(True)
        await browser.click("Upload CSV")
        assert "Download CSV template" in await browser.text()
        await browser.upload(valid)
        await browser.input("Opening balance", "10.00")
        assert (await browser.metrics())["Estimated cash balance"] == "USD 85.00"
        await browser.snapshot(directory, "journey-valid-upload")
        record("Upload valid CSV", estimated_cash="USD 85.00", explicit_opening="10.00")
        await browser.upload(invalid)
        assert "Import has errors" in await browser.text()
        assert not await browser.metrics()
        await browser.snapshot(directory, "journey-invalid-upload")
        record("Upload invalid CSV and inspect feedback", metrics_absent=True, invalid_field="amount")
        await browser.upload(valid)
        assert (await browser.metrics())["Estimated cash balance"] == "USD 85.00"
        await browser.click("Synthetic demo")
        await browser.click("Start demo")
        assert await browser.metrics() == baseline
        report["runtime_errors"] = browser.errors
        record("Recover from invalid upload and return to consistent demo", metrics=baseline)


async def inspect(args):
    async with BrowserQA() as browser:
        await browser.open(width=args.width, height=1000)
        if args.opening:
            await browser.input("Opening balance", args.opening)
        if args.page != "Overview":
            await browser.navigate(args.page)
        await browser.screenshot(args.output)
        print(json.dumps(await browser.evaluate("""({title:document.title, width:innerWidth, charts:document.querySelectorAll('.js-plotly-plot').length, exceptions:document.querySelectorAll('[data-testid=stException]').length})"""), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--opening", default=None)
    parser.add_argument("--page", default="Overview")
    parser.add_argument("--output", default="reports/phase7/screenshots/inspection.png")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--journeys", action="store_true", help="Explicitly run UI journeys, including real Gemma on fictional inputs")
    parser.add_argument("--directory", default="reports/phase7/screenshots")
    args = parser.parse_args()
    asyncio.run(journeys(args) if args.journeys else matrix(args) if args.matrix else inspect(args))


if __name__ == "__main__":
    main()
