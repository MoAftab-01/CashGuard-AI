"""Run bounded, non-root UI/API children behind one restricted public ingress.

No user data is written to disk. The temporary directory holds only nginx runtime
configuration. Any child failure terminates the instance instead of leaving a
partially working public service. MLflow is never started.
"""

import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


def render_config(template, directory, port, scheme):
    if type(port) is not int or not 1024 <= port <= 65535 or port in {8000, 8501}:
        raise ValueError("Choose a valid public port distinct from internal service ports")
    if scheme not in {"http", "https"} or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(directory)):
        raise ValueError("Invalid ingress configuration")
    return template.replace("@RUNTIME@", str(directory)).replace("@PORT@", str(port)).replace("@SCHEME@", scheme)


def wait_ready(url, children, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(child.poll() is not None for child in children):
            raise RuntimeError("A service exited during startup")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.25)
    raise RuntimeError("Service startup timed out")


def main():
    from src.settings import Settings
    settings = Settings.from_environment()
    if not settings.public_demo or settings.execution_mode != "api":
        raise ValueError("Portfolio ingress requires synthetic-only API mode")
    public_port = int(os.getenv("PORT", "8080"))
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("CASHGUARD_PUBLIC_HOST", "localhost")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", hostname):
        raise ValueError("Invalid public hostname")
    scheme = "https" if os.getenv("CASHGUARD_PUBLIC_HTTPS", "false").lower() == "true" else "http"
    # Internal services must never bind publicly, regardless of inherited defaults.
    environment = dict(os.environ, CASHGUARD_API_HOST="127.0.0.1", CASHGUARD_API_PORT="8000",
                       CASHGUARD_CONTAINER_BIND="false", CASHGUARD_ALLOWED_HOSTS="127.0.0.1,localhost,[::1]",
                       CASHGUARD_API_URL="http://127.0.0.1:8000", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       STREAMLIT_SERVER_COOKIE_SECRET=secrets.token_urlsafe(32))
    children = []
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with tempfile.TemporaryDirectory(prefix="cashguard-ingress-", dir="/tmp") as directory:
            template = (Path(__file__).parent / "nginx.conf.template").read_text()
            config = Path(directory) / "nginx.conf"
            config.write_text(render_config(template, directory, public_port, scheme))
            subprocess.run(["nginx", "-t", "-c", str(config), "-p", directory], check=True)
            children.append(subprocess.Popen([sys.executable, "-m", "api"], env=environment))
            children.append(subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true",
                "--server.fileWatcherType=none", "--server.maxUploadSize=1", "--server.maxMessageSize=2",
                "--server.enableCORS=true", "--server.enableXsrfProtection=true",
                "--browser.serverAddress=" + hostname], env=environment))
            wait_ready("http://127.0.0.1:8000/ready", children)
            wait_ready("http://127.0.0.1:8501/_stcore/health", children)
            children.append(subprocess.Popen(["nginx", "-c", str(config), "-p", directory,
                                               "-g", "daemon off;"], env=environment))
            while not stopping and all(child.poll() is None for child in children):
                time.sleep(.25)
            if not stopping:
                raise RuntimeError("A portfolio service stopped unexpectedly")
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.SubprocessError):
        print("Portfolio startup failed. Check validated configuration and service health; no secrets are printed.", file=sys.stderr)
        raise SystemExit(1) from None
