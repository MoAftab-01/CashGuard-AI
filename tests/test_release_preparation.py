import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.prepare_release import candidates, inspect, package


def write(root, name, text="reviewed fixture"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_public_allowlist_excludes_stores_credentials_weights_logs_and_unreviewed_data(tmp_path):
    allowed = {"README.md", "LICENSE", "src/metrics.py", "tests/test_metrics.py", ".env.example",
               ".github/workflows/ci.yml", "docs/submission/assets/main-dashboard.png", "compose.staging.yaml",
               "render.yaml", "deploy/serve.py", "deploy/nginx.conf.template", "deploy/public-demo.env.example"}
    denied = {".env", ".env.private", "var/mlflow/mlflow.db", ".aws/credentials", ".venv/tool.py",
              "src/__pycache__/secret.py", "data/private.csv", "private.csv", "reports/customer.csv",
              "reports/phase9/pytest.xml", "reports/phase9/api.log", "reports/phase7/screenshots/private.png",
              "docs/submission/assets/model.gguf", "model.safetensors", ".streamlit/secrets.toml"}
    denied |= {"deploy/private.env", "deploy/credentials.json", "deploy/private.py"}
    for name in allowed | denied:
        write(tmp_path, name)
    assert {p.relative_to(tmp_path).as_posix() for p in candidates(tmp_path)} == allowed


def test_scan_reports_only_locations_not_secret_values_or_machine_paths(tmp_path):
    token = "gh" + "p_" + "x" * 40
    machine = "C:" + chr(92) + "Users" + chr(92) + "private" + chr(92) + "records.csv"
    write(tmp_path, "README.md", token + "\n" + machine)
    review = inspect(tmp_path)
    assert not review["pattern_scan_passed"]
    assert {f["kind"] for f in review["findings"]} == {"credential_prefix", "absolute_windows_user_path"}
    encoded = json.dumps(review)
    assert token not in encoded and machine not in encoded
    with pytest.raises(ValueError):
        package(tmp_path, tmp_path / "out.zip", review)


def test_source_archive_is_reproducible_and_preserves_reviewed_bytes(tmp_path):
    write(tmp_path, "LICENSE", "Confirmed license fixture")
    write(tmp_path, "README.md", "Honest claims only")
    review = inspect(tmp_path)
    first = package(tmp_path, tmp_path / "one.zip", review)
    second = package(tmp_path, tmp_path / "two.zip", inspect(tmp_path))
    assert first["sha256"] == second["sha256"] and first["members"] == 2
    with zipfile.ZipFile(tmp_path / "one.zip") as archive:
        assert archive.read("CashGuard-AI/README.md") == b"Honest claims only"
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in archive.namelist())


def test_package_requires_license_and_fails_if_files_changed_after_review(tmp_path):
    write(tmp_path, "README.md")
    with pytest.raises(ValueError, match="license"):
        package(tmp_path, tmp_path / "out.zip", inspect(tmp_path))
    write(tmp_path, "LICENSE")
    review = inspect(tmp_path)
    write(tmp_path, "README.md", "Changed after review")
    with pytest.raises(ValueError, match="changed after review"):
        package(tmp_path, tmp_path / "out.zip", review)


def test_replaced_demo_cannot_be_packaged_as_approved_synthetic_data(tmp_path):
    write(tmp_path, "LICENSE")
    write(tmp_path, "data/synthetic_transactions.csv", "Unreviewed financial data")
    review = inspect(tmp_path)
    assert {f["kind"] for f in review["findings"]} == {"unrecognized_demo_data"}
    with pytest.raises(ValueError):
        package(tmp_path, tmp_path / "out.zip", review)


def test_pytest_temp_fixtures_work_in_a_fresh_checkout_without_cache(tmp_path):
    checkout = tmp_path / "fresh-checkout"
    config = Path(__file__).resolve().parents[1] / "pyproject.toml"
    write(checkout, "pyproject.toml", config.read_text(encoding="utf-8"))
    write(checkout, "tests/test_first_run.py", "def test_first_run(tmp_path):\n    assert tmp_path.is_dir()\n")
    assert not (checkout / ".pytest_cache").exists()
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               cwd=checkout, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed" in completed.stdout
