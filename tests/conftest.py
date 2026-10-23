import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def sandbox(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path / "data"), HOME=str(tmp_path / "home"))
    env.pop("VISUAL", None)
    env.pop("EDITOR", None)
    return project, env


def command(cwd, env, *args, input=None, ok=True):
    result = subprocess.run(
        [sys.executable, "-m", "notes_cli", *args],
        cwd=cwd,
        env=env,
        input=input,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result


def data(env):
    return Path(env["XDG_DATA_HOME"]) / "notes"


def tty_command(cwd, env, *args, ok=True):
    import pty

    master, slave = pty.openpty()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "notes_cli", *args],
            cwd=cwd,
            env=env,
            stdin=slave,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        os.close(slave)
        os.close(master)
    if ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result
