"""Local axe/keyboard/reflow checks; not a WCAG conformance certification.

Supply a pinned, integrity-verified axe-core browser script in ignored var/.
Only use an isolated QA browser and the synthetic-only localhost demo.
"""

import argparse
import asyncio
import json
from pathlib import Path

from scripts.browser_qa import BrowserQA
from scripts.qa_phase10a import CONTRAST, key
from src.settings import loopback_url
from src.ui.navigation import VIEWS


async def scan(browser, axe):
    await browser.evaluate(axe)
    return await browser.evaluate("""(async()=>{
      const r=await axe.run(document,{runOnly:{type:'tag',values:[
        'wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice']}});
      return {version:axe.version,passes:r.passes.length,
        violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,
          nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),
        incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.length}))};
    })()""")


async def inspect(args):
    if args.extras_only:
        return await inspect_expanded_states(args)
    args.output.mkdir(parents=True, exist_ok=True)
    axe = args.axe.read_text(encoding="utf-8")
    report = {"pages": {}, "synthetic_only": True, "screen_reader_tested": False}
    async with BrowserQA(args.endpoint) as b:
        for width, height in ((1440,1000),(390,844)):
            for dark in (False, True):
                await b.open(args.url,width=width,height=height,dark=dark)
                await b.sidebar(True)
                await b.click("Start demo")
                for route in VIEWS:
                    await b.navigate(route)
                    name=f"{width}-{'dark' if dark else 'light'}-{VIEWS[route][2]}"
                    result=await scan(b,axe)
                    layout=await b.snapshot(args.output,name)
                    result.update(contrast=await b.evaluate(CONTRAST),layout=layout)
                    report["pages"][name]=result
                    (args.output/"results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
                    print(f"{name}: {len(result['violations'])} axe violations",flush=True)
        await b.open(args.url,width=1440,height=1000)
        await b.sidebar(True)
        await b.click("Start demo")
        await b.expand("Chart data:")
        report["expanded_chart"]=await scan(b,axe)
        tree=await b.call("Accessibility.getFullAXTree")
        nodes=tree.get("nodes",[])
        report["chart_accessibility_tree"]={
            "tables":sum(n.get("role",{}).get("value")=="table" for n in nodes),
            "chart_names":[n.get("name",{}).get("value","") for n in nodes
                           if "Expand Chart data" in n.get("name",{}).get("value","")],
            "headings":[{"name":n.get("name",{}).get("value"),"properties":n.get("properties")}
                        for n in nodes if n.get("role",{}).get("value")=="heading"]}
        await b.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] button')].find(e=>e.innerText.trim()==='Home').focus()")
        await key(b,"Tab",9)
        report["keyboard_focus"]=await b.evaluate("({name:document.activeElement.innerText,width:getComputedStyle(document.activeElement).outlineWidth,style:getComputedStyle(document.activeElement).outlineStyle})")
        await key(b,"Enter",13)
        await b.settle()
        assert "Transactions" in await b.text()
        await b.input("Search description","NO_MATCH_FICTIONAL")
        assert "No transactions match" in await b.text()
        report["empty_state"]=await scan(b,axe)
        await b.navigate("Scenario Simulator")
        await b.input("Emergency expense","nan")
        assert "Check the scenario inputs" in await b.text()
        report["invalid_form"]=await scan(b,axe)
        report["alert_roles"]=await b.evaluate("[...document.querySelectorAll('[role=alert]')].map(e=>e.innerText)")
        await b.click("Reset plan")
        # 320 CSS-px viewport is the reflow equivalent of a 1280px window at 400%.
        # This is an emulation, not a claim of testing native browser UI zoom.
        report["reflow"]={}
        for width in (720,320):
            await b.open(args.url,width=width,height=900)
            await b.sidebar(True)
            await b.click("Start demo")
            await b.navigate("Scenario Simulator")
            await b.sidebar(False)
            report["reflow"][str(width)]=await b.snapshot(args.output,f"reflow-{width}")
        await b.call("Emulation.setEmulatedMedia",features=[dict(name="prefers-reduced-motion",value="reduce")])
        report["reduced_motion"]=await b.evaluate("({requested:matchMedia('(prefers-reduced-motion: reduce)').matches,transition:getComputedStyle(document.querySelector('[data-testid=stMain] button')).transitionDuration})")
        report["runtime_errors"]=b.errors
    (args.output/"results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    assert not report["runtime_errors"]
    assert all(not r["violations"] for r in report["pages"].values()), "Review actual axe findings in results.json"
    assert all(not report[state]["violations"] for state in ("expanded_chart","empty_state","invalid_form")), "Review expanded/error state findings"


async def inspect_expanded_states(args):
    """Hidden panels need their own scans; viewport reflow is not native UI zoom."""
    args.output.mkdir(parents=True,exist_ok=True)
    report={"states":{},"native_browser_zoom_tested":False,"screen_reader_tested":False}
    axe=args.axe.read_text(encoding="utf-8")
    async with BrowserQA(args.endpoint) as b:
        for dark in (False,True):
            mode="dark" if dark else "light"
            await b.open(args.url,dark=dark)
            await b.click("Start demo")
            await b.sidebar(True)
            await b.expand("Cash settings")
            report["states"][mode+"-cash-settings"]=await scan(b,axe)
            for route,panel in (("Overview","Chart data:"),("Transactions","Readable transaction table"),
                                ("Anomaly Detection","Readable unusual-activity table"),
                                ("Scenario Simulator","Customize this plan")):
                await b.navigate(route)
                await b.expand(panel)
                report["states"][mode+"-"+VIEWS[route][2]]=await scan(b,axe)
            await b.input("Emergency expense","nan")
            report["states"][mode+"-invalid-plan"]=await scan(b,axe)
            await b.click("Reset plan")
        await b.open(args.url,width=390,height=844)
        await b.click("Start demo")
        await b.sidebar(False)
        found=await b.evaluate("""(()=>{const e=document.querySelector('[data-testid=stExpandSidebarButton] button, button[data-testid=stExpandSidebarButton]'); if(!e)return false;e.focus();return true})()""")
        assert found
        await key(b,"Enter",13)
        await b.wait("document.querySelector('[data-testid=stSidebar]')?.getAttribute('data-collapsed')==='false'")
        report["mobile_sidebar_keyboard_opened"]=True
        await b.open(args.url,width=1440,height=1000)
        await b.click("Start demo")
        await b.sidebar(False)
        await b.evaluate("document.documentElement.style.fontSize='200%'")
        report["root_font_200_percent"]=await b.snapshot(args.output,"root-font-200")
        assert report["root_font_200_percent"]["clippedMetricValues"]==0
        assert report["root_font_200_percent"]["mainScrollWidth"]<=report["root_font_200_percent"]["mainWidth"]+2
        positions=await b.evaluate("[...document.querySelectorAll('[data-testid=stMetric]')].map(e=>({top:e.getBoundingClientRect().top,width:e.getBoundingClientRect().width}))")
        assert len(positions)==4 and positions[2]["top"]>positions[0]["top"], "Enlarged metrics should reflow into fewer columns"
        report["enlarged_metric_positions"]=positions
        await b.evaluate("document.documentElement.style.fontSize=''")
        report["runtime_errors"]=b.errors
    (args.output/"expanded-results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    assert all(not state["violations"] for state in report["states"].values())
    assert not report["runtime_errors"]
    print(json.dumps({"expanded_states":len(report["states"]),"violations":0,"mobile_keyboard":True}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint",default="http://127.0.0.1:9224")
    p.add_argument("--url",default="http://127.0.0.1:8512")
    p.add_argument("--axe",type=Path,default=Path("var/phase10b/vendor/axe.min.js"))
    p.add_argument("--output",type=Path,default=Path("var/phase10b/accessibility"))
    p.add_argument("--extras-only",action="store_true",help="Audit expanded forms/tables, mobile keyboard and root-font scaling")
    args=p.parse_args()
    args.url,args.endpoint=loopback_url(args.url),loopback_url(args.endpoint)
    asyncio.run(inspect(args))


if __name__=="__main__":
    main()
