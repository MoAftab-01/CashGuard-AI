"""Measure a fresh, local-only synthetic demo container; never provision hosting.

The Docker daemon must already be available. Resource caps include all application
processes, not the browser. Evidence and credentials stay under ignored var/.
"""

import argparse
import asyncio
import json
import subprocess
import threading
import time
from pathlib import Path

import requests
import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ClientState_pb2 import ClientState
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


def docker(*args, timeout=60):
    result = subprocess.run(["docker", *args],capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        # Never echo command arguments or daemon output that could include env.
        raise RuntimeError("Local Docker operation failed; inspect the named QA container locally.")
    return result.stdout.strip()


class Session:
    def __init__(self, port):
        self.port, self.widgets, self.values = port, {}, {}

    async def connect(self):
        self.connection = await websockets.connect(f"ws://127.0.0.1:{self.port}/_stcore/stream",
            subprotocols=["streamlit"],origin=f"http://127.0.0.1:{self.port}",
            open_timeout=15,max_size=16*1024*1024)
        return await self.run()

    async def run(self, updates=None):
        self.values.update(updates or {})
        state=ClientState()
        for label,value in self.values.items():
            kind,identity=self.widgets[label]
            widget=state.widget_states.widgets.add(); widget.id=identity
            if kind=="button":
                widget.trigger_value=bool(value)
            else:
                widget.string_value=str(value)
        request=BackMsg(); request.rerun_script.CopyFrom(state)
        started=time.perf_counter()
        await self.connection.send(request.SerializeToString())
        metrics,alerts={},[]
        async with asyncio.timeout(120):
            while True:
                raw=await self.connection.recv()
                message=ForwardMsg.FromString(raw)
                kind=message.WhichOneof("type")
                if kind=="new_session" and message.new_session.initialize.session_id:
                    self.session_id=message.new_session.initialize.session_id
                if kind=="delta" and message.delta.HasField("new_element"):
                    e=message.delta.new_element
                    if e.HasField("exception"):
                        raise RuntimeError("Application exception in synthetic load test")
                    for widget_kind in ("radio","button","text_input","selectbox"):
                        if e.HasField(widget_kind):
                            w=getattr(e,widget_kind); self.widgets[w.label]=(widget_kind,w.id)
                    if e.HasField("metric"):
                        metrics[e.metric.label]=e.metric.body
                    if e.HasField("alert"):
                        alerts.append(e.alert.body)
                if kind=="script_finished":
                    if message.script_finished!=ForwardMsg.FINISHED_SUCCESSFULLY:
                        raise RuntimeError("Incomplete synthetic session run")
                    # Buttons trigger once; do not accidentally replay Start demo.
                    self.values={k:v for k,v in self.values.items() if self.widgets[k][0]!="button"}
                    return {"seconds":round(time.perf_counter()-started,3),"metrics":metrics,"alerts":alerts}


async def workload(port):
    first=Session(port)
    others=[]
    try:
        initial=await first.connect()
        single=await first.run({"Start demo":True})
        assert single["metrics"].get("Estimated cash balance")=="USD 16,268.23"
        for _ in range(4):
            s=Session(port); others.append(s)
            await s.connect()
            await s.run({"Start demo":True})
        sessions=[first,*others]
        # Five active WebSockets and a simultaneous burst of distinct inputs.
        started=time.perf_counter()
        responses=await asyncio.gather(*(s.run({"Opening balance":f"{5000+i}.00"})
            for i,s in enumerate(sessions)),return_exceptions=True)
        burst=[]
        for i,response in enumerate(responses):
            if isinstance(response,BaseException):
                burst.append({"session":i,"error":type(response).__name__})
            else:
                response["session"]=i
                response["correct_balance"]=response["metrics"].get("Estimated cash balance")==f"USD {18768.23+i:,.2f}"
                burst.append(response)
        wall=round(time.perf_counter()-started,3)
        # Check each retained input again, including after all other sessions ran.
        retained=[]
        for i,s in enumerate(sessions):
            response=await s.run()
            retained.append({"session":i,"seconds":response["seconds"],
                "correct_balance":response["metrics"].get("Estimated cash balance")==f"USD {18768.23+i:,.2f}"})
        return {"initial_session":initial,"single_session":single,"five_session_burst":burst,
            "burst_wall_seconds":wall,"retained_inputs":retained,
            "distinct_streamlit_sessions":len({s.session_id for s in sessions})}
    finally:
        for s in [first,*others]:
            if hasattr(s,"connection"):
                await s.connection.close()


def profile(args):
    if not args.name.startswith("cashguard-phase10b-profile-"):
        raise ValueError("Use a dedicated Phase 10B profiling container name")
    report={"image":args.image,"cpu_limit":args.cpus,"memory_limit_mib":args.memory,
        "swap_disabled":True,"local_only":True,"inference_provider":"deterministic",
        "method":"Docker stats sampling; cgroup peak includes cache and small measurement process. WebSocket execution latency excludes browser paint and registry pull."}
    report["image_bytes_uncompressed"]=int(docker("image","inspect",args.image,"--format","{{.Size}}"))
    report["image_id"]=docker("image","inspect",args.image,"--format","{{.Id}}")
    command=["run","-d","--name",args.name,"--read-only","--cap-drop","ALL",
        "--security-opt","no-new-privileges","--pids-limit","128",
        "--memory",f"{args.memory}m","--memory-swap",f"{args.memory}m","--cpus",str(args.cpus),
        "--tmpfs","/tmp:size=128m,mode=1777","--tmpfs","/home/cashguard:size=32m,uid=10001,gid=10001",
        "--env-file",str(args.env_file),"-e","CASHGUARD_DEPLOYMENT_PROFILE=staging",
        "-p",f"127.0.0.1:{args.port}:8080",report["image_id"]]
    samples=[]
    stream=None
    started=time.perf_counter()
    try:
        docker(*command)
        stream=subprocess.Popen(["docker","stats",args.name,"--format","{{json .}}"],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        def collect():
            for line in stream.stdout:
                try:
                    value=json.loads(line[line.index('{'):]); value['elapsed_seconds']=round(time.perf_counter()-started,3)
                    samples.append(value)
                except (ValueError,KeyError):
                    pass
        thread=threading.Thread(target=collect,daemon=True);thread.start()
        http=requests.Session();http.trust_env=False
        deadline=time.perf_counter()+150
        while time.perf_counter()<deadline:
            try:
                if http.get(f"http://127.0.0.1:{args.port}/ready",timeout=2).status_code==200:
                    break
            except requests.RequestException:
                pass
            if docker("inspect",args.name,"--format","{{.State.Running}}")!="true":
                raise RuntimeError("Container exited before readiness")
            time.sleep(.5)
        else:
            raise TimeoutError("No readiness within 150 seconds")
        report["startup_to_ready_seconds"]=round(time.perf_counter()-started,3)
        # Sample a settled idle period before any financial analytics request.
        time.sleep(10)
        report["idle_samples"]=samples[-3:]
        report["workload"]=asyncio.run(workload(args.port))
        time.sleep(3)
        report["cgroup"]=json.loads(docker("exec",args.name,"python","-c",
            "import pathlib,json; p=pathlib.Path('/sys/fs/cgroup'); "
            "names=('memory.current','memory.peak','memory.events','cpu.stat') if (p/'cgroup.controllers').exists() "
            "else ('memory/memory.usage_in_bytes','memory/memory.max_usage_in_bytes','memory/memory.oom_control','memory/memory.failcnt','cpu/cpu.stat'); "
            "print(json.dumps({n:(p/n).read_text().strip() for n in names if (p/n).exists()}))"))
        state=json.loads(docker("inspect",args.name,"--format","{{json .State}}"))
        report["container_state"]={k:state.get(k) for k in ("Running","OOMKilled","ExitCode")}
    except Exception as exc:
        report["error"]=type(exc).__name__+": "+str(exc)
        try:
            state=json.loads(docker("inspect",args.name,"--format","{{json .State}}"))
            report["container_state"]={k:state.get(k) for k in ("Running","OOMKilled","ExitCode")}
        except RuntimeError:
            pass
    finally:
        if stream:
            stream.terminate();stream.wait(timeout=10)
        report["samples"]=samples
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
        docker("stop",args.name)
    print(json.dumps({k:v for k,v in report.items() if k not in {"samples","workload","idle_samples"}},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name",required=True)
    p.add_argument("--image",default="cashguard-portfolio:phase10b")
    p.add_argument("--memory",type=int,default=512)
    p.add_argument("--cpus",type=float,default=.1)
    p.add_argument("--port",type=int,default=8513)
    p.add_argument("--env-file",type=Path,default=Path("var/portfolio-phase9/staging.env"))
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if not 256<=args.memory<=1536 or not .1<=args.cpus<=1 or not 8513<=args.port<=8519:
        p.error("Use bounded local QA resources and a dedicated localhost port")
    profile(args)


if __name__=="__main__":
    main()
