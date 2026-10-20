"""Real local Gemma and fictional-CSV browser journeys, never hosted inference."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from scripts.browser_qa import BrowserQA
from src.data_processing import validate_csv
from src.llm_service import OllamaService, OllamaSettings
from src.settings import loopback_url


async def inspect(args):
    args.output.mkdir(parents=True,exist_ok=True)
    report=dict(synthetic_only=True,hosted_inference=False,journeys=[])
    async with BrowserQA(args.endpoint) as b:
        await b.open(args.url)
        await b.sidebar(True)
        await b.click('Start demo')
        await b.navigate('AI Insights')
        with OllamaService(OllamaSettings.from_environment()) as service:
            status=service.check_availability()
        report['local_model_status']=dict(ready=status.ready,code=status.code,model=status.model)
        if status.ready:
            await b.input('Local model',status.model)
            started=perf_counter()
            await b.evaluate("[...document.querySelectorAll('button')].find(e=>e.innerText.trim()==='Generate AI Insights').click()")
            await asyncio.sleep(.25)
            await b.screenshot(args.output/'local-gemma-loading.png')
            await b.wait("document.querySelector('[data-testid=stMain]').innerText.includes('AI-generated explanations')",timeout=120)
            await b.settle()
            report['gemma']=dict(source='ai',model=status.model,browser_roundtrip_seconds=perf_counter()-started)
            (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            await b.snapshot(args.output,'local-gemma-answer')
            await b.expand('Full explanations and calculated evidence')
            assert 'Financial health summary' in await b.text()
            report['journeys'].append('Real local Gemma answer and expandable validated evidence')
        else:
            report['gemma']=dict(source='not_executed',reason=status.code)
        await b.input('Local model','cashguard-phase10a-unavailable:latest')
        assert 'not installed' in await b.text() or 'Cannot connect' in await b.text()
        await b.click('Generate AI Insights')
        assert 'No model-generated answer' in await b.text()
        await b.snapshot(args.output,'missing-model-fallback')
        report['journeys'].append('Unavailable-model fallback clearly retains calculations')
        valid=args.output/'fictional-valid.csv'
        valid.write_text('date,description,amount,category\n2026-01-01,Fictional receipt,100,Income\n2026-01-02,'+'Fictional long description '*18+',-25,Other\n',encoding='utf-8')
        assert not validate_csv(valid).has_errors
        invalid=args.output/'fictional-invalid.csv'
        invalid.write_text('date,description,amount,category\n2026-01-01,Bad row,not-money,Other\n',encoding='utf-8')
        await b.sidebar(True)
        await b.click('Upload CSV')
        await b.upload(valid)
        await b.input('Opening balance','10.00')
        await b.navigate('Overview')
        assert (await b.metrics())['Estimated cash balance']=='USD 85.00'
        await b.navigate('Transactions')
        layout=await b.snapshot(args.output,'long-description-table')
        assert layout['mainScrollWidth']<=layout['mainWidth']+2
        await b.upload(invalid)
        assert 'blocked' in (await b.text()).lower()
        assert not await b.metrics()
        await b.snapshot(args.output,'invalid-csv')
        await b.upload(valid)
        await b.navigate('Overview')
        assert (await b.metrics())['Estimated cash balance']=='USD 85.00'
        report['journeys'].append('Valid CSV, long content, invalid CSV blocks totals, corrected CSV recovers')
        report['runtime_errors']=b.errors
        assert not b.errors
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default='http://127.0.0.1:9225')
    parser.add_argument('--url',default='http://127.0.0.1:8511')
    parser.add_argument('--output',type=Path,default=Path('var/phase10a/local-browser'))
    args=parser.parse_args()
    args.url,args.endpoint=loopback_url(args.url),loopback_url(args.endpoint)
    asyncio.run(inspect(args))


if __name__=='__main__':
    main()
