import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml
from conftest import command, data

from notes_cli import store
from notes_cli.files import NotesError


def identity(project):
    return yaml.safe_load((project / ".notes-project").read_text())["id"]


def test_git_root_and_reinitialize(sandbox):
    project, env = sandbox
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    sub = project / "src"
    sub.mkdir()
    failed = command(sub, env, "list", ok=False)
    assert str(project) in failed.stderr and "notes init" in failed.stderr
    assert not (project / ".notes-project").exists()
    command(sub, env, "init")
    before = identity(project)
    command(sub, env, "init")
    assert identity(project) == before
    assert not (sub / ".notes-project").exists()


def test_non_git_and_metadata(sandbox):
    project, env = sandbox
    command(project, env, "init")
    sub = project / "sub"
    sub.mkdir()
    body = "\n# Decisão de autenticação\n\nUsar **e-mail**.\n"
    added = command(sub, env, "add", body, "--to", "agents", "--author", "codex")
    path = data(env) / "projects" / identity(project) / "001.md"
    assert str(path) in added.stdout
    note = store.read_note(path)
    assert note.body == body
    assert note.meta["title"] == "# Decisão de autenticação"
    assert note.meta["author"] == "codex" and note.meta["to"] == "agents"
    assert note.meta["revision"] == 1
    assert note.meta["created_at"] == note.meta["updated_at"]
    assert note.meta["created_at"].endswith("Z")
    assert "e-mail" in command(sub, env, "read", "1").stdout
    assert "#1" in command(sub, env, "search", "AUTENTICAÇÃO").stdout
    assert not command(sub, env, "search", ".*").stdout
    assert "#1" in command(sub, env, "list").stdout


@pytest.mark.parametrize("global_flags", [[], ["--global"]])
def test_archive_idempotent_and_ids(sandbox, global_flags):
    project, env = sandbox
    command(project, env, "init")
    command(project, env, "add", "primeira", *global_flags)
    command(project, env, "archive", "1", *global_flags)
    path = (
        data(env) / "global" if global_flags else data(env) / "projects" / identity(project)
    ) / "001.md"
    before = path.read_bytes()
    command(project, env, "archive", "1", *global_flags)
    assert path.read_bytes() == before
    assert not command(project, env, "list", *global_flags).stdout
    assert "primeira" in command(project, env, "list", "--archived", *global_flags).stdout
    assert "primeira" in command(project, env, "read", "1", *global_flags).stdout
    command(project, env, "add", "segunda", *global_flags)
    assert "#2" in command(project, env, "list", *global_flags).stdout


def test_scope_resolution_duplicate_names_and_move(sandbox, tmp_path):
    first, env = sandbox
    second = tmp_path / "other" / "app"
    second.mkdir(parents=True)
    command(first, env, "init")
    command(second, env, "init")
    first_id = identity(first)
    command(first, env, "add", "isolada")
    assert not command(second, env, "list").stdout
    assert "ambíguo" in command(second, env, "list", "--project", "app", ok=False).stderr
    assert "isolada" in command(second, env, "list", "--project", first_id).stdout
    moved = tmp_path / "moved"
    first.rename(moved)
    assert "isolada" in command(moved, env, "list").stdout
    assert (
        len(json.loads((data(env) / "projects.json").read_text())["projects"][first_id]["paths"])
        == 2
    )
    moved.rename(tmp_path / "again")
    assert "isolada" in command(second, env, "list", "--project", first_id).stdout


def test_invalid_config_never_falls_back(sandbox):
    project, env = sandbox
    command(project, env, "init")
    nested = project / "nested"
    nested.mkdir()
    config = nested / ".notes-project"
    config.write_text("id: bad\nname: app\n")
    failed = command(nested, env, "list", ok=False)
    assert str(config) in failed.stderr
    assert command(nested, env, "list", "--global").returncode == 0
    assert (
        "not allowed"
        in command(nested, env, "list", "--global", "--project", "app", ok=False).stderr
    )


def test_global_without_project_and_validation(sandbox):
    project, env = sandbox
    command(project, env, "add", "Preferência global", "--global")
    assert "global" in command(project, env, "read", "1", "--global").stdout
    command(project, env, "list", ok=False)
    command(project, env, "add", " \n", "--global", ok=False)
    assert not (data(env) / "global" / "002.md").exists()
    command(project, env, "read", "0", "--global", ok=False)
    command(project, env, "read", "100", "--global", ok=False)


def test_invalid_files_partial_results_and_duplicate_ids(sandbox):
    project, env = sandbox
    command(project, env, "add", "válida", "--global")
    bad = data(env) / "global" / "002.md"
    bad.write_text("inválida")
    result = command(project, env, "list", "--global", ok=False)
    assert "válida" in result.stdout and str(bad) in result.stderr
    command(project, env, "add", "terceira", "--global")
    assert (bad.parent / "003.md").exists()
    bad.write_text((bad.parent / "001.md").read_text())
    assert "duplicado" in command(project, env, "archive", "1", "--global", ok=False).stderr


def test_concurrent_adds_and_registry(sandbox, tmp_path):
    project, env = sandbox

    def create(i):
        return command(project, env, "add", f"nota {i}", "--global")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(20)))
    notes = [store.read_note(p) for p in (data(env) / "global").glob("*.md")]
    assert sorted(n.meta["id"] for n in notes) == list(range(1, 21))
    assert len({n.body for n in notes}) == 20
    folders = [tmp_path / f"p{i}" for i in range(10)]
    for folder in folders:
        folder.mkdir()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda folder: command(folder, env, "init"), folders))
    entries = json.loads((data(env) / "projects.json").read_text())["projects"]
    assert len(entries) == 10
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: command(project, env, "init"), range(8)))
    assert len(json.loads((data(env) / "projects.json").read_text())["projects"]) == 11


def test_strict_yaml_and_external_revision(sandbox):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    path = data(env) / "global" / "001.md"
    before = store.read_note(path)
    path.write_text(path.read_text().replace("original", "externo"))
    after = store.read_note(path)
    assert before.revision != after.revision
    assert before.meta["revision"] == after.meta["revision"]
    path.write_text(path.read_text().replace("id: 1", "id: 1\nid: 2"))
    with pytest.raises(NotesError, match="duplicada"):
        store.read_note(path)


def test_deterministic_order(sandbox):
    project, env = sandbox
    for body in ("first", "second", "third"):
        command(project, env, "add", body, "--global")
    listing = command(project, env, "list", "--global").stdout
    assert listing.index("#3") < listing.index("#2") < listing.index("#1")
    for path in (data(env) / "global").glob("*.md"):
        note = store.read_note(path)
        note.meta["updated_at"] = "2099-01-01T00:00:00Z"
        path.write_text(store.serialize(note.meta, note.body))
    listing = command(project, env, "list", "--global").stdout
    assert listing.index("#1") < listing.index("#2") < listing.index("#3")


def test_bad_registry_and_data_home(sandbox):
    project, env = sandbox
    command(project, env, "init")
    (data(env) / "projects.json").write_text("[]")
    command(project, env, "list", "--project", "app", ok=False)
    result = command(project, dict(env, XDG_DATA_HOME="relative"), "list", "--global", ok=False)
    assert "absoluto" in result.stderr


def test_explicit_argument_does_not_read_stdin(sandbox):
    project, env = sandbox
    # Keep stdin open: the process must finish without trying to read until EOF.
    process = subprocess.Popen(
        [sys.executable, "-m", "notes_cli", "add", "argumento", "--global"],
        cwd=project,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.wait(timeout=5) == 0
    finally:
        process.kill() if process.poll() is None else None
        process.communicate()
