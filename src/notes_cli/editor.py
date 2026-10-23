"""Editor drafts never hold a scope lock; failed saves retain recoverable content."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from . import store
from .files import NotesError, read_text


def editor_command():
    setting = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not setting:
        raise NotesError(
            "configure VISUAL ou EDITOR (ex.: export EDITOR=nano); "
            "para criar sem editor, use notes add < arquivo.md; "
            "para editar, use notes edit <id> --body-file arquivo.md"
        )
    try:
        command = shlex.split(setting)
    except ValueError as exc:
        raise NotesError(f"VISUAL/EDITOR inválido: {exc}; corrija a configuração") from exc
    if not command:
        raise NotesError("VISUAL/EDITOR vazio; configure o comando de um editor")
    return command


def draft(initial):
    command = editor_command()
    fd, name = tempfile.mkstemp(prefix="notes-draft-", suffix=".md")
    path = Path(name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(initial.encode("utf-8"))
    try:
        result = subprocess.run([*command, str(path)], check=False)
        if result.returncode:
            raise NotesError(f"editor terminou com status {result.returncode}")
        return path, read_text(path)
    except (OSError, NotesError, KeyboardInterrupt) as exc:
        raise NotesError(f"{exc}; rascunho preservado: {path}") from exc


def create(scope, author, recipient):
    path, body = draft("")
    if not body.strip():
        path.unlink(missing_ok=True)
        return None
    try:
        note = store.add(scope, body, author, recipient)
    except (NotesError, OSError, UnicodeError, KeyboardInterrupt) as exc:
        raise NotesError(f"{exc}; rascunho preservado: {path}") from exc
    path.unlink(missing_ok=True)
    return note


def edit(scope, identifier, expected=None):
    initial = store.get(scope, identifier)
    if expected is not None and expected != initial.revision:
        raise NotesError("conflito: revisão alterada; leia novamente com read --json")
    path, raw = draft(initial.raw)
    try:
        proposed = store.parse(raw, path)
        note = store.edit(scope, identifier, expected=initial.revision, proposed=proposed)
    except (NotesError, OSError, UnicodeError, KeyboardInterrupt) as exc:
        raise NotesError(f"{exc}; rascunho preservado: {path}") from exc
    path.unlink(missing_ok=True)
    return note
