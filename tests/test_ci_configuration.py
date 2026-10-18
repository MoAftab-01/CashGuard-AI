from pathlib import Path

import yaml


def test_ci_is_least_privilege_offline_and_does_not_deploy():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"quality", "containers"}
    assert workflow["jobs"]["containers"]["needs"] == "quality"
    for job in workflow["jobs"].values():
        assert job["timeout-minutes"] <= 30
        checkout = job["steps"][0]
        assert checkout["with"]["persist-credentials"] is False
    for required in ("pip check", "ruff check", "compileall", "pytest", "--calibration-only",
                     "--track-mlflow", "monitor_models --synthetic", "compose --profile tracking build",
                     "scripts.check_services", "scripts.smoke_dashboard", "compose --profile tracking down"):
        assert required in text
    assert "ollama pull" not in text and "docker push" not in text
    assert "secrets." not in text and "deploy" not in workflow["jobs"]
