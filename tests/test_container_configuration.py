from pathlib import Path

import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def test_compose_services_keep_host_ports_local_and_optional_tracking():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert set(compose["services"]) == {"dashboard", "api", "mlflow"}
    for service in compose["services"].values():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"])
        assert service["cap_drop"] == ["ALL"]
    assert compose["services"]["mlflow"]["profiles"] == ["tracking"]
    assert not compose["services"]["api"].get("volumes")
    assert not compose["services"]["dashboard"].get("volumes")


def test_runtime_lock_is_pinned_and_excludes_optional_tracking_and_test_tools():
    text = (ROOT / "requirements-runtime.lock.txt").read_text()
    names = set()
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        item = Requirement(line)
        assert all(spec.operator == "==" for spec in item.specifier)
        names.add(item.name)
    assert {"fastapi", "streamlit", "scikit-learn", "prometheus-client"} <= names
    assert not names & {"mlflow", "pytest", "ruff", "httpx", "pywin32"}


def test_container_context_excludes_secrets_uploads_and_tracking_state():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert {".env", ".env.*", ".streamlit/secrets.toml", ".venv", "var", "reports", "data/*"} <= set(ignored)
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "USER cashguard" in dockerfile
    assert "ollama pull" not in dockerfile
    assert "COPY . ." not in dockerfile


def test_lock_regeneration_matches_installed_metadata():
    from scripts.lock_dependencies import RUNTIME, lock
    assert lock(RUNTIME) == (ROOT / "requirements-runtime.lock.txt").read_text()
