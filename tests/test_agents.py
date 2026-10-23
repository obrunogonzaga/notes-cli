import json
import os
import pty
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import command, data, tty_command

from notes_cli import store


def json_note(project, env, *flags):
    return json.loads(command(project, env, "read", "1", "--json", *flags).stdout)["note"]


def make_editor(tmp_path, program):
    script = tmp_path / "controlled editor.py"
    script.write_text(
        "from pathlib import Path\nimport os, sys, time\np = Path(sys.argv[-1])\n" + program
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


@pytest.mark.parametrize("mode", ["pipe", "file", "heredoc", "argument"])
def test_long_input(sandbox, tmp_path, mode):
    project, env = sandbox
    body = "---\nid: 999\nauthor: impostor\n---\n\n# Autenticação\r\n\n" + "Olá **mundo**!\n" * 200
    source = tmp_path / "body.md"
    source.write_bytes(body.encode())
    if mode == "argument":
        command(project, env, "add", body, "--global", input="IGNORAR")
    elif mode == "pipe":
        command(project, env, "add", "--global", input=body)
    else:
        executable = f"{shlex.quote(sys.executable)} -m notes_cli add --global"
        # Heredoc normalizes no content; preserve CRLF in the literal source.
        shell = (
            executable + " < " + shlex.quote(str(source))
            if mode == "file"
            else executable + " <<'NOTES_EOF'\n" + body + "NOTES_EOF\n"
        )
        result = subprocess.run(
            ["bash", "-c", shell], cwd=project, env=env, capture_output=True, text=True, timeout=20
        )
        assert result.returncode == 0, result.stderr
    note = json_note(project, env, "--global")
    assert note["body"] == body and note["id"] == 1
    assert note["author"] != "impostor" and note["title"] == "---"


@pytest.mark.parametrize("visual", [False, True])
def test_tty_editor_precedence(sandbox, tmp_path, visual):
    project, env = sandbox
    editor = make_editor(
        tmp_path,
        "assert os.isatty(0)\nassert p.read_bytes() == b''\n"
        "p.write_text('# Do editor\\n\\nOlá!\\n', encoding='utf-8')\n",
    )
    configured = dict(env, EDITOR=editor)
    if visual:
        configured.update(VISUAL=editor, EDITOR="does-not-exist")
    tty_command(project, configured, "add", "--global", "--to", "agents")
    note = json_note(project, env, "--global")
    assert note["body"] == "# Do editor\n\nOlá!\n" and note["to"] == "agents"


def test_editor_cancel_failure_and_missing(sandbox, tmp_path):
    project, env = sandbox
    failed = tty_command(project, env, "add", "--global", ok=False)
    assert "VISUAL" in failed.stderr and "< arquivo.md" in failed.stderr
    empty = make_editor(tmp_path, "p.write_text(' \\n')\n")
    assert not tty_command(project, dict(env, EDITOR=empty), "add", "--global").stdout
    assert not list((data(env) / "global").glob("*.md"))
    broken = make_editor(tmp_path, "p.write_text('recuperável')\nsys.exit(7)\n")
    failed = tty_command(project, dict(env, EDITOR=broken), "add", "--global", ok=False)
    draft = Path(failed.stderr.split("rascunho preservado: ")[1].split(";")[0].strip())
    assert draft.read_text() == "recuperável"
    draft.unlink()
    command(project, env, "add", " \n", "--global", ok=False)
    command(project, env, "add", "--global", input="", ok=False)
    command(project, env, "add", "criada", "--global")
    assert json_note(project, env, "--global")["id"] == 1
    assert not (data(env) / "global" / "002.md").exists()


@pytest.mark.parametrize("flags", [[], ["--global"]])
def test_body_file_conditional_revision(sandbox, tmp_path, flags):
    project, env = sandbox
    command(project, env, "init")
    command(project, env, "add", "original", *flags)
    before = json_note(project, env, *flags)
    source = tmp_path / "body.md"
    body = "\n# Corpo editado\n\nOlá!\n"
    source.write_text(body)
    command(
        project,
        env,
        "edit",
        "1",
        "--body-file",
        str(source),
        "--if-revision",
        before["revision"],
        *flags,
    )
    after = json_note(project, env, *flags)
    assert after["body"] == body and after["revision_number"] == 2
    for key in ("id", "created_at", "title", "author", "to", "status"):
        assert before[key] == after[key]
    assert after["revision"] != before["revision"]
    source.write_text("não sobrescrever")
    command(
        project,
        env,
        "edit",
        "1",
        "--body-file",
        str(source),
        "--if-revision",
        before["revision"],
        *flags,
        ok=False,
    )
    assert json_note(project, env, *flags) == after
    path = Path(after["path"])
    path.write_text(path.read_text() + "externo")
    externally_changed = path.read_bytes()
    failed = command(
        project,
        env,
        "edit",
        "1",
        "--body-file",
        str(source),
        "--if-revision",
        after["revision"],
        *flags,
        ok=False,
    )
    assert "conflito" in failed.stderr and path.read_bytes() == externally_changed
    command(project, env, "edit", "1", "--body-file", str(source), *flags)
    assert json_note(project, env, *flags)["body"] == "não sobrescrever"
    source.write_text(" ")
    before = path.read_bytes()
    command(project, env, "edit", "1", "--body-file", str(source), *flags, ok=False)
    assert path.read_bytes() == before


def test_concurrent_conditional_updates(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    token = json_note(project, env, "--global")["revision"]
    sources = [tmp_path / f"body-{i}.md" for i in range(6)]
    for i, source in enumerate(sources):
        source.write_text(f"versão {i}")

    def replace(source):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "notes_cli",
                "edit",
                "1",
                "--global",
                "--body-file",
                str(source),
                "--if-revision",
                token,
            ],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(replace, sources))
    assert sum(r.returncode == 0 for r in results) == 1
    assert all("conflito" in r.stderr for r in results if r.returncode)
    assert json_note(project, env, "--global")["revision_number"] == 2


def test_interactive_edit_metadata_and_invalid_preservation(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    before = json_note(project, env, "--global")
    valid = make_editor(
        tmp_path,
        "p.write_text(p.read_text().replace('title: original', "
        "'title: Novo título').replace('\\n\\noriginal', '\\n\\nEditada'))\n",
    )
    tty_command(project, dict(env, EDITOR=valid), "edit", "1", "--global")
    after = json_note(project, env, "--global")
    assert after["title"] == "Novo título" and after["body"] == "Editada"
    assert before["created_at"] == after["created_at"] and after["revision_number"] == 2
    for program in (
        "p.write_text(p.read_text().replace('id: 1', 'id: 99'))\n",
        "p.write_text(p.read_text().replace('to: all', 'to: nobody'))\n",
    ):
        invalid = make_editor(tmp_path, program)
        failed = tty_command(project, dict(env, EDITOR=invalid), "edit", "1", "--global", ok=False)
        assert json_note(project, env, "--global") == after
        draft = Path(failed.stderr.split("rascunho preservado: ")[1].split(";")[0].strip())
        assert draft.exists()
        draft.unlink()


def wait_for(path, process):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline, "editor did not signal readiness"
        time.sleep(0.02)


@pytest.mark.parametrize("operation", ["add", "edit"])
def test_editor_does_not_lock_and_detects_conflict(sandbox, tmp_path, operation):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    ready, release = tmp_path / "ready", tmp_path / "release"
    program = (
        f"Path({str(ready)!r}).touch()\n"
        f"while not Path({str(release)!r}).exists(): time.sleep(0.02)\n"
        + (
            "p.write_text('proposta')\n"
            if operation == "add"
            else "p.write_text(p.read_text().replace('\\n\\noriginal', '\\n\\nproposta'))\n"
        )
    )
    editor = make_editor(tmp_path, program)
    arguments = ["add"] if operation == "add" else ["edit", "1"]
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, "-m", "notes_cli", *arguments, "--global"],
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
        command(project, env, "add", "enquanto editor aberto", "--global")
        if operation == "edit":
            body = tmp_path / "other.md"
            body.write_text("alteração concorrente")
            command(project, env, "edit", "1", "--body-file", str(body), "--global")
        release.touch()
        stdout, stderr = process.communicate(timeout=15)
        if operation == "edit":
            assert process.returncode != 0 and "conflito" in stderr
            assert json_note(project, env, "--global")["body"] == "alteração concorrente"
            draft = Path(stderr.split("rascunho preservado: ")[1].split(";")[0].strip())
            assert "proposta" in draft.read_text()
            draft.unlink()
        else:
            assert process.returncode == 0, stderr
            assert "#3" in stdout
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
            process.communicate()
        os.close(master)


def test_json_and_partial_errors(sandbox):
    project, env = sandbox
    command(project, env, "add", "Olá", "--global")
    for operation in (["list"], ["read", "1"], ["search", "olá"], ["context"]):
        payload = json.loads(command(project, env, *operation, "--global", "--json").stdout)
        assert payload["schema_version"] == 1
        note = payload["note"] if "note" in payload else payload["notes"][0]
        assert note["scope"]["kind"] == "global" and note["revision_number"] == 1
        assert note["revision"].startswith("1-")
    broken = data(env) / "global" / "broken.md"
    broken.write_text("inválido")
    for operation in (["list"], ["search", "olá"], ["context"]):
        result = command(project, env, *operation, "--global", "--json", ok=False)
        payload = json.loads(result.stdout)
        assert len(payload["notes"]) == 1 and str(broken) in payload["errors"][0]
        assert str(broken) in result.stderr


def test_context_filters_limits_and_scopes(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "init")
    for flags in ([], ["--global"]):
        for target in ("bruno", "agents", "all"):
            command(project, env, "add", f"para {target}", "--to", target, *flags)
    other = tmp_path / "other"
    other.mkdir()
    command(other, env, "init")
    command(other, env, "add", "NÃO INCLUIR")

    def context(*args):
        return json.loads(command(project, env, "context", "--json", *args).stdout)

    default = context()
    assert len(default["notes"]) == 4
    assert {n["scope"]["kind"] for n in default["notes"]} == {"project", "global"}
    assert all(n["to"] in ("agents", "all") for n in default["notes"])
    assert len(context("--to", "bruno")["notes"]) == 4
    assert len(context("--to", "all")["notes"]) == 2
    assert len(context("--global")["notes"]) == 2
    limited = context("--limit", "0")
    assert limited["notes"] == [] and len(limited["omitted"]) == 4
    assert all("notes read" in n["read_command"] for n in limited["omitted"])
    assert limited["used_characters"] == 0
    text = command(project, env, "context", "--limit", "0").stdout
    assert "Omitida" in text and "--project" in text and "--global" in text
    assert len(context("--limit", str(default["used_characters"]))["notes"]) == 4
    limited = context("--limit", str(default["used_characters"] - 1))
    assert len(limited["notes"]) < 4 and limited["used_characters"] <= limited["limit"]
    command(project, env, "archive", "3")
    assert len(context()["notes"]) == 3
    command(project, env, "context", "--limit", "-1", ok=False)


def test_noop_edit_preserves_revision(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    before = json_note(project, env, "--global")
    source = tmp_path / "body.md"
    source.write_text("original")
    command(project, env, "edit", "1", "--global", "--body-file", str(source))
    assert before == json_note(project, env, "--global")
    unchanged = make_editor(tmp_path, "pass\n")
    tty_command(project, dict(env, EDITOR=unchanged), "edit", "1", "--global")
    assert before == json_note(project, env, "--global")


def test_non_utf8_body_is_rejected(sandbox, tmp_path):
    project, env = sandbox
    command(project, env, "add", "original", "--global")
    invalid = tmp_path / "bad.md"
    invalid.write_bytes(b"\xff")
    command(project, env, "edit", "1", "--body-file", str(invalid), "--global", ok=False)
    assert json_note(project, env, "--global")["body"] == "original"
    assert store.read_note(Path(json_note(project, env, "--global")["path"])).body == "original"
