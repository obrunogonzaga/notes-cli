import json
import os
import subprocess
import sys
import tarfile
import venv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def run(*args, cwd, env):
    process = subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return process


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("distribution")
    env = dict(os.environ, HOME=str(root / "home"), XDG_DATA_HOME=str(root / "data"))
    env.pop("PYTHONPATH", None)
    dist = root / "dist"
    run(sys.executable, "-m", "build", "--outdir", dist, REPO, cwd=root, env=env)
    wheel = next(dist.glob("*.whl"))
    source = next(dist.glob("*.tar.gz"))
    with tarfile.open(source) as archive:
        names = archive.getnames()
    assert any(name.endswith("/PRD.md") for name in names)
    assert any(name.endswith("/tests/conftest.py") for name in names)
    production = root / "production"
    venv.EnvBuilder(with_pip=True).create(production)
    python = production / "bin/python"
    run(python, "-m", "pip", "install", wheel, cwd=root, env=env)
    imported = run(python, "-c", "import notes_cli; print(notes_cli.__file__)", cwd=root, env=env)
    assert str(production) in imported.stdout and str(REPO / "src") not in imported.stdout
    yield root, env, production / "bin/notes", source


def test_clean_wheel_install_and_console_script(installed):
    root, env, notes, _ = installed
    assert run(notes, "--version", cwd=root, env=env).stdout == "notes 0.1.0\n"
    assert "context" in run(notes, "--help", cwd=root, env=env).stdout
    run(notes, "init", cwd=root, env=env)
    run(notes, "add", "Pacote instalado", "--author", "codex", cwd=root, env=env)
    note = json.loads(run(notes, "read", "1", "--json", cwd=root, env=env).stdout)["note"]
    assert note["body"] == "Pacote instalado"
    assert note["scope"]["kind"] == "project"


def test_clean_source_distribution_install(installed):
    root, env, _, source = installed
    production = root / "source-install"
    venv.EnvBuilder(with_pip=True).create(production)
    run(production / "bin/python", "-m", "pip", "install", source, cwd=root, env=env)
    notes = production / "bin/notes"
    run(notes, "add", "Do pacote fonte", "--global", cwd=root, env=env)
    assert "Do pacote fonte" in run(notes, "list", "--global", cwd=root, env=env).stdout


def test_automated_bruno_agent_pilot(installed):
    root, env, notes, _ = installed
    output = root / "pilot.json"
    run(
        sys.executable,
        REPO / "scripts/pilot.py",
        "--notes",
        notes,
        "--output",
        output,
        cwd=root,
        env=env,
    )
    report = json.loads(output.read_text())
    assert report["result"] == "passed" and report["human_participation"] is False
    assert report["commands"] >= 15
    assert any(step["actor"] == "bruno-new-session" for step in report["transcript"])
    assert sum(step["exit_code"] != 0 for step in report["transcript"]) == 1
