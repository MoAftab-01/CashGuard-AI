"""Actual local browser QA: all preserved views, three viewports and two themes.

Use only the isolated local test browser. No external accounts or hosted inference.
"""

import argparse
import asyncio
import json
from pathlib import Path

from scripts.browser_qa import BrowserQA
from src.settings import loopback_url
from src.ui.navigation import VIEWS


CONTRAST = """(() => {
 const parse=s=>{const n=s.match(/[\\d.]+/g)?.map(Number);return n&&n.length>=3?[...n.slice(0,3),n[3]??1]:[0,0,0,0]};
 const blend=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3]));
 const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const targets=[['heading',document.querySelector('[data-testid=stMain] h1'),3],
 ['caption',document.querySelector('[data-testid=stMain] [data-testid=stCaptionContainer] p'),4.5],
 ['primary button',document.querySelector('[data-testid=stSidebar] button[kind=primary] p'),4.5]];
 return targets.filter(([,e])=>e&&e.getBoundingClientRect().width>0).map(([name,e,minimum])=>{
  const chain=[];for(let a=e;a;a=a.parentElement)chain.unshift(a);
  let bg=[255,255,255],opacity=1;for(const a of chain){bg=blend(parse(getComputedStyle(a).backgroundColor),bg);opacity*=Number(getComputedStyle(a).opacity)}
  const fg=parse(getComputedStyle(e).color);fg[3]*=opacity;
  const color=blend(fg,bg), l=[lum(color),lum(bg)].sort((a,b)=>a-b);
  return {name,foreground:color,background:bg,ratio:(l[1]+.05)/(l[0]+.05),minimum};
 });
})()"""


async def key(browser, name, code):
    for kind in ("keyDown", "keyUp"):
        extra = dict(code=name)
        if name == "Enter" and kind == "keyDown":
            extra.update(text="\r", unmodifiedText="\r")
        await browser.call("Input.dispatchKeyEvent", type=kind, key=name, windowsVirtualKeyCode=code, **extra)


async def inspect(args):
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(synthetic_only=True, pages={}, journeys=[], keyboard={}, inference_requested=False)
    async with BrowserQA(args.endpoint) as browser:
        for width, height in ((1440,1000),(834,1112),(390,844)):
            for dark in (False,True):
                device = "desktop" if width > 1100 else "tablet" if width > 700 else "mobile"
                mode = device + ("-dark" if dark else "-light")
                await browser.open(args.url,width=width,height=height,dark=dark)
                await browser.sidebar(True)
                assert not await browser.evaluate("!!document.querySelector('input[type=file]')")
                await browser.click("Start demo")
                for route in VIEWS:
                    await browser.navigate(route)
                    if route not in {"Model Evaluation", "Data quality"}:
                        await browser.evaluate("(() => {const e=[...document.querySelectorAll('[data-testid=stSidebar] details')].find(e=>e.querySelector('summary')?.innerText.includes('Advanced'));if(e?.open)e.querySelector('summary').click()})()")
                    if width < 1100:
                        await browser.sidebar(False)
                    name = mode + '-' + VIEWS[route][2]
                    layout = await browser.snapshot(args.output,name)
                    assert layout['mainScrollWidth'] <= layout['mainWidth']+2, name+': page overflow'
                    assert not layout['clippedMetricValues'], name+': clipped metric'
                    checks = [c for c in layout['chartChecks'] if c['title']]
                    assert all(c['titleInside'] and c['legendInside'] and not c['titleLegendOverlap'] for c in checks), name+': chart bounds'
                    layout['contrast'] = await browser.evaluate(CONTRAST)
                    assert all(c['ratio'] >= c['minimum'] for c in layout['contrast']), (name,layout['contrast'])
                    if route == "Overview":
                        metrics = await browser.metrics()
                        assert metrics['Estimated cash balance'] == 'USD 16,268.23'
                        assert metrics['Estimated 30-day balance'] == 'USD 17,859.81'
                        assert layout['charts'] == 1
                    if route == "Model Evaluation":
                        assert (await browser.metrics())['F1'] == '0.9600'
                    if route in {"Cash Flow Forecast","Scenario Simulator"}:
                        assert layout['charts'] > 0
                    report['pages'][name] = layout
                    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                    print('PASS: '+name,flush=True)
        await browser.open(args.url,width=1440,height=1000)
        await browser.sidebar(True)
        await browser.click('Start demo')
        # Actual Tab/Enter navigation and computed focus indication.
        await browser.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] button')].find(e=>e.innerText.trim()==='Home').focus()")
        await key(browser,'Tab',9)
        focused = await browser.evaluate("({label:document.activeElement.innerText,outline:getComputedStyle(document.activeElement).outlineStyle,width:getComputedStyle(document.activeElement).outlineWidth})")
        assert focused['label']=='Explore' and focused['outline']=='solid' and float(focused['width'].removesuffix('px'))>=2
        await key(browser,'Enter',13)
        await browser.wait("[...document.querySelectorAll('h1')].some(e=>e.innerText==='Transactions')")
        await browser.settle()
        assert await browser.evaluate("[...document.querySelectorAll('h1')].some(e=>e.innerText==='Transactions')")
        report['keyboard']=dict(tab_focus=focused,enter_navigation='Explore → Transactions',screen_reader_tested=False)
        await browser.input('Search description','NO_SUCH_FICTIONAL_TRANSACTION')
        assert 'No transactions match' in await browser.text()
        report['journeys'].append('Search empty state, with safe disabled download')
        await browser.navigate('Cash Flow Forecast')
        await browser.input('Minimum cash threshold','20000.00')
        assert 0 < int((await browser.metrics())['Days below threshold']) <= 30
        await browser.input('Minimum cash threshold','500.00')
        report['journeys'].append('Threshold changes update the API forecast')
        await browser.navigate('Scenario Simulator')
        await browser.click('Unexpected expense')
        assert (await browser.metrics())['Closing balance change']=='USD -500.00'
        await browser.click('Reduced income')
        assert (await browser.metrics())['Closing balance change'] not in {'USD 0.00','USD -500.00'}
        await browser.click('Reset plan')
        assert (await browser.metrics())['Closing balance change']=='USD 0.00'
        await browser.input('Emergency expense','nan')
        assert 'Check the scenario inputs' in await browser.text()
        await browser.snapshot(args.output,'scenario-invalid-input')
        await browser.click('Reset plan')
        assert (await browser.metrics())['Closing balance change']=='USD 0.00'
        report['journeys'].append('Presets, reset and malformed-input recovery without changing history')
        await browser.navigate('AI Insights')
        assert 'Calculated summary' in await browser.text()
        assert await browser.evaluate("[...document.querySelectorAll('button')].find(e=>e.innerText.trim()==='Generate AI Insights').disabled")
        await browser.click('How does my plan change things?')
        assert 'hypothetical outcome' in await browser.text()
        report['journeys'].append('Suggested question uses existing scenario evidence without inference')
        await browser.navigate('Overview')
        assert (await browser.metrics())['Estimated cash balance']=='USD 16,268.23'
        report['runtime_errors']=browser.errors
        assert not browser.errors
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(page_layouts=len(report['pages']),runtime_errors=len(report['runtime_errors']),journeys=report['journeys'])))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default='http://127.0.0.1:9224')
    parser.add_argument('--url',default='http://127.0.0.1:8510')
    parser.add_argument('--output',type=Path,default=Path('var/phase10a/browser'))
    args=parser.parse_args()
    args.endpoint,args.url=loopback_url(args.endpoint),loopback_url(args.url)
    asyncio.run(inspect(args))


if __name__=='__main__':
    main()
