import json
import os
import pty
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import command, data
from test_agents import json_note, make_editor, wait_for
from test_core import identity

from notes_cli import store


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora restrições de permissão Unix")
def test_unreadable_scope_is_error_and_context_preserves_global(sandbox):
    project, env = sandbox
    command(project, env, "init")
    command(project, env, "add", "projeto")
    command(project, env, "add", "global válida", "--global")
    directory = data(env) / "projects" / identity(project)
    directory.chmod(0)
    try:
        result = command(project, env, "list", "--json", ok=False)
        assert str(directory) in result.stderr and "permiss" in result.stderr
        result = command(project, env, "context", "--json", ok=False)
        payload = json.loads(result.stdout)
        assert len(payload["notes"]) == 1 and payload["notes"][0]["body"] == "global válida"
        assert str(directory) in payload["errors"][0]
        command(project, env, "add", "não criar", ok=False)
    finally:
        directory.chmod(0o700)
    assert len(list(directory.glob("*.md"))) == 1


def test_real_clone_and_worktree_share_identity(sandbox, tmp_path):
    project, env = sandbox

    def git(*args, cwd=project):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    command(project, env, "init")
    command(project, env, "add", "compartilhada")
    original_id = identity(project)
    git("add", ".notes-project")
    git("commit", "-qm", "project identity")
    clone, worktree = tmp_path / "clone", tmp_path / "worktree"
    git("clone", "-q", str(project), str(clone))
    git("worktree", "add", "-q", "--detach", str(worktree))
    for folder in (clone, worktree):
        assert identity(folder) == original_id
        assert json_note(folder, env)["body"] == "compartilhada"
    command(worktree, env, "add", "retorno pelo worktree", "--author", "codex", "--to", "bruno")
    assert "retorno pelo worktree" in command(clone, env, "context", "--to", "bruno").stdout
    (clone / ".notes-project").write_text(
        (clone / ".notes-project").read_text().replace("name: app", "name: renomeado")
    )
    command(clone, env, "init")
    assert identity(clone) == original_id
    assert json_note(project, env, "--project", "renomeado")["id"] == 1
    registry = json.loads((data(env) / "projects.json").read_text())
    assert len(registry["projects"][original_id]["paths"]) == 3
    nested = worktree / "nested"
    nested.mkdir()
    command(nested, env, "init")
    assert not (nested / ".notes-project").exists()


def test_readers_never_observe_partial_cli_writes(sandbox, tmp_path):
    project, env = sandbox
    bodies = ["A\n" + "á" * 80000, "B\n" + "β" * 80000]
    command(project, env, "add", "initial", "--global")
    files = []
    for i, body in enumerate(bodies):
        path = tmp_path / f"body-{i}.md"
        path.write_text(body)
        files.append(path)
    # One long-lived external process repeatedly invokes actual CLI entry points.
    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import subprocess, sys
for i in range(18):
    subprocess.run([sys.executable, "-m", "notes_cli", "edit", "1", "--global",
                    "--body-file", sys.argv[1 + i % 2]], check=True, stdout=subprocess.DEVNULL)
""",
            *(str(p) for p in files),
        ],
        cwd=project,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    reads = 0
    try:
        while writer.poll() is None:
            note = json_note(project, env, "--global")
            assert note["body"] in ["initial", *bodies]
            assert note["revision_number"] >= 1
            reads += 1
        stdout, stderr = writer.communicate(timeout=10)
        assert writer.returncode == 0, (stdout, stderr)
        assert reads > 2
        assert json_note(project, env, "--global")["revision_number"] == 19
    finally:
        if writer.poll() is None:
            writer.kill()
            writer.communicate()


def test_interactive_edit_detects_external_file_change(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    path = Path(json_note(project, env, "--global")["path"])
    ready, release = tmp_path / "ready", tmp_path / "release"
    editor = make_editor(
        tmp_path,
        f"Path({str(ready)!r}).touch()\n"
        f"while not Path({str(release)!r}).exists(): time.sleep(0.02)\n"
        "p.write_text(p.read_text() + '\\nproposta')\n",
    )
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, "-m", "notes_cli", "edit", "1", "--global"],
        cwd=project,
        env=dict(env, EDITOR=editor),
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    try:
        wait_for(ready, process)
        path.write_text(path.read_text() + "externa")
        expected = path.read_bytes()
        release.touch()
        _, stderr = process.communicate(timeout=15)
        assert process.returncode != 0 and "conflito" in stderr
        assert path.read_bytes() == expected
        draft = Path(stderr.split("rascunho preservado: ")[1].split(";")[0].strip())
        assert "proposta" in draft.read_text()
        draft.unlink()
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
            process.communicate()
        os.close(master)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora restrições de permissão Unix")
def test_file_and_write_permissions_preserve_notes(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "preservar", "--global")
    command(project, env, "add", "ainda legível", "--global")
    path = data(env) / "global" / "001.md"
    expected = path.read_bytes()
    path.chmod(0)
    try:
        result = command(project, env, "list", "--global", "--json", ok=False)
        assert "ainda legível" in result.stdout and str(path) in result.stderr
        assert "Traceback" not in result.stderr
    finally:
        path.chmod(0o600)
    directory = path.parent
    directory.chmod(0o500)
    source = tmp_path / "body.md"
    source.write_text("não salvar")
    try:
        failed = command(
            project, env, "edit", "1", "--global", "--body-file", str(source), ok=False
        )
        assert "permiss" in failed.stderr and "Traceback" not in failed.stderr
        assert path.read_bytes() == expected
        command(project, env, "add", "não criar", "--global", ok=False)
        assert not (directory / "003.md").exists()
    finally:
        directory.chmod(0o700)


def test_global_xdg_fallback(sandbox):
    project, env = sandbox
    env.pop("XDG_DATA_HOME")
    command(project, env, "add", "fallback", "--global")
    assert (Path(env["HOME"]) / ".local/share/notes/global/001.md").exists()


def test_unregistered_project_config_auto_registers(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "init")
    identifier = identity(project)
    replacement = tmp_path / "new-data"
    env = dict(env, XDG_DATA_HOME=str(replacement))
    assert not (replacement / "notes/projects.json").exists()
    command(project, env, "list")
    command(tmp_path, env, "add", "descoberto", "--project", identifier)
    assert json_note(project, env)["body"] == "descoberto"


def test_malformed_metadata_errors_without_traceback(sandbox):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    path = data(env) / "global" / "001.md"
    original = path.read_text()
    for old, new in (
        ("revision: 1", "revision: true"),
        ("title: original", "title: []"),
        ("status: active", "status: []"),
        ("to: all", "to: {}"),
        ("schema_version: 1", "schema_version: 99"),
    ):
        path.write_text(original.replace(old, new))
        failed = command(project, env, "read", "1", "--global", ok=False)
        assert str(path) in failed.stderr and "Traceback" not in failed.stderr
    path.write_text(original)
    assert store.read_note(path).body == "original"


def test_concurrent_project_adds(sandbox):
    project, env = sandbox
    command(project, env, "init")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: command(project, env, "add", f"projeto {i}"), range(16)))
    notes = json.loads(command(project, env, "list", "--json").stdout)["notes"]
    assert sorted(note["id"] for note in notes) == list(range(1, 17))
    assert len({note["body"] for note in notes}) == 16
