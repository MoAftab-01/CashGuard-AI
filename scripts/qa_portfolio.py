"""Real isolated-browser QA for the synthetic-only local staging boundary.

Screenshots remain local under var. No inference, upload, or third-party account
mutation is performed. This is complementary to, not a substitute for, pytest.
"""

import argparse
import asyncio
import json
from pathlib import Path

from scripts.browser_qa import BrowserQA
from src.settings import loopback_url

PAGES = ("Overview", "Transactions", "Cash Flow Forecast", "Anomaly Detection", "Risk Analysis",
         "Scenario Simulator", "AI Insights", "Model Evaluation", "Data quality")


async def inspect(args):
    report = {"transport": "Actual isolated Chromium/Edge CDP", "synthetic_only": True,
              "pages": {}, "journeys": [], "inference_requested": False}
    args.output.mkdir(parents=True, exist_ok=True)
    async with BrowserQA(args.endpoint) as browser:
        for width, height, dark in ((1440,1000,False),(390,844,False),(1440,1000,True),(390,844,True)):
            mode = ("mobile" if width < 700 else "desktop") + ("-dark" if dark else "-light")
            await browser.open(args.url,width=width,height=height,dark=dark)
            await browser.sidebar(True)
            assert "Public synthetic demo" in await browser.evaluate("document.body.innerText")
            assert not await browser.evaluate("!!document.querySelector('input[type=file]')")
            await browser.click("Start demo")
            for page in PAGES:
                await browser.navigate(page)
                assert not await browser.evaluate("!!document.querySelector('[data-testid=stException]')"), page
                name = mode + '-' + page.lower().replace(' ','-')
                layout = await browser.snapshot(args.output,name)
                assert layout['mainScrollWidth'] <= layout['mainWidth'] + 2, name + ': horizontal page overflow'
                assert layout['clippedMetricValues']==0, name + ': clipped KPI'
                if page=='Overview':
                    metrics = await browser.metrics()
                    assert metrics['Estimated cash balance']=='USD 16,268.23'
                if page=='Model Evaluation':
                    assert (await browser.metrics())['F1']=='0.9600'
                if page in {'Cash Flow Forecast','Overview','Scenario Simulator'}:
                    assert layout['charts'] > 0, name + ': missing chart'
                report['pages'][name]=layout
                print('PASS: '+name,flush=True)
        await browser.open(args.url,width=1440,height=1000)
        await browser.sidebar(True)
        await browser.click('Start demo')
        await browser.navigate('Cash Flow Forecast')
        await browser.input('Minimum cash threshold','20000.00')
        assert int((await browser.metrics())['Days below threshold'])>0
        report['journeys'].append('Changed threshold recalculates API forecast')
        await browser.input('Minimum cash threshold','500.00')
        await browser.navigate('Scenario Simulator')
        await browser.input('Emergency expense','500.00')
        assert (await browser.metrics())['Closing balance change']=='USD -500.00'
        await browser.slider('Income reduction (%)',3)
        assert (await browser.metrics())['Closing balance change']!='USD -500.00'
        report['journeys'].append('Emergency and reduced income alter projected balances')
        await browser.navigate('Overview')
        assert (await browser.metrics())['Estimated cash balance']=='USD 16,268.23'
        report['journeys'].append('Navigation preserves historical metrics')
        report['runtime_errors']=browser.errors
        assert not browser.errors
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'page_layouts':len(report['pages']),'journeys':report['journeys'],'runtime_errors':len(report['runtime_errors'])}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default='http://127.0.0.1:9224')
    parser.add_argument('--url',default='http://127.0.0.1:8510')
    parser.add_argument('--output',type=Path,default=Path('var/portfolio-phase9/browser'))
    args=parser.parse_args()
    args.endpoint,args.url=loopback_url(args.endpoint),loopback_url(args.url)
    asyncio.run(inspect(args))


if __name__=='__main__':
    main()
