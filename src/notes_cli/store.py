"""Validated Markdown records. Writers coordinate per scope; readers see whole files."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .files import NotesError, atomic_write, dump_yaml, load_yaml, lock, read_text

FIELDS = {
    "schema_version",
    "id",
    "title",
    "author",
    "to",
    "status",
    "created_at",
    "updated_at",
    "revision",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("data não está em UTC")
        return parsed
    except (ValueError, TypeError, AttributeError) as exc:
        raise NotesError(f"data UTC inválida: {value!r}") from exc


def validate_body(body):
    if not body.strip():
        raise NotesError("corpo vazio; forneça texto Markdown não vazio")


def validate(meta, body):
    if set(meta) != FIELDS:
        raise NotesError(f"campos de metadados inválidos; esperados: {', '.join(sorted(FIELDS))}")
    for field in ("schema_version", "id", "revision"):
        if type(meta[field]) is not int or meta[field] < 1:
            raise NotesError(f"{field} deve ser inteiro positivo")
    if meta["schema_version"] != 1:
        raise NotesError("schema_version não suportada")
    for field in ("title", "author"):
        if not isinstance(meta[field], str) or not meta[field].strip() or "\n" in meta[field]:
            raise NotesError(f"{field} deve ser texto não vazio em uma linha")
    if meta["to"] not in ("bruno", "agents", "all"):
        raise NotesError("to deve ser bruno, agents ou all")
    if meta["status"] not in ("active", "archived"):
        raise NotesError("status deve ser active ou archived")
    if timestamp(meta["updated_at"]) < timestamp(meta["created_at"]):
        raise NotesError("updated_at anterior a created_at")
    validate_body(body)


@dataclass
class Note:
    meta: dict
    body: str
    path: Path
    raw: str

    @property
    def revision(self):
        # Counter alone cannot detect edits performed outside the CLI.
        return f"{self.meta['revision']}-{hashlib.sha256(self.raw.encode('utf-8')).hexdigest()}"


def serialize(meta, body):
    return "---\n" + dump_yaml(meta) + "---\n\n" + body


def parse(raw, path):
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", raw, re.DOTALL)
    if not match:
        raise NotesError("front matter YAML ausente ou incompleto")
    body = raw[match.end() :]
    # Exactly one separator blank line belongs to the envelope, not the body.
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    meta = load_yaml(match.group(1))
    validate(meta, body)
    return Note(meta, body, path, raw)


def read_note(path):
    try:
        return parse(read_text(path), path)
    except NotesError as exc:
        raise NotesError(f"{path}: {exc}; corrija o arquivo Markdown") from exc


def scan(scope):
    notes, errors, seen = [], [], {}
    for path in sorted(scope.directory.glob("*.md")):
        try:
            note = read_note(path)
            identifier = note.meta["id"]
            if identifier in seen:
                raise NotesError(f"{path}: ID {identifier} duplicado com {seen[identifier]}")
            seen[identifier] = path
            notes.append(note)
        except NotesError as exc:
            errors.append(str(exc))
    notes.sort(key=lambda n: (-timestamp(n.meta["updated_at"]).timestamp(), n.meta["id"]))
    return notes, errors


def get(scope, identifier):
    notes, errors = scan(scope)
    matches = [note for note in notes if note.meta["id"] == identifier]
    # Ambiguous storage must never silently pick one file to overwrite.
    if any(f"ID {identifier} duplicado" in error for error in errors):
        raise NotesError("; ".join(errors))
    if matches:
        return matches[0]
    raise NotesError(
        f"nota {identifier} não encontrada em {scope.id}"
        + ("; " + "; ".join(errors) if errors else "")
    )


def save(path, meta, body):
    validate(meta, body)
    raw = serialize(meta, body)
    atomic_write(path, raw)
    return Note(meta, body, path, raw)


def add(scope, body, author, recipient):
    validate_body(body)
    with lock(scope.lock_path):
        notes, _ = scan(scope)
        used = [note.meta["id"] for note in notes]
        # Reserve filenames even if their YAML is invalid.
        for path in scope.directory.glob("*.md"):
            match = re.match(r"(\d+)(?:-|\.)", path.name)
            if match:
                used.append(int(match.group(1)))
        sequence = scope.directory / ".sequence"
        high = 0
        if sequence.exists():
            try:
                high = int(read_text(sequence))
                if high < 0:
                    raise ValueError()
            except ValueError as exc:
                raise NotesError(f"{sequence}: sequência inválida; restaure o contador") from exc
        identifier = max([high, *used]) + 1
        created = now()
        meta = {
            "schema_version": 1,
            "id": identifier,
            "title": next(line.strip() for line in body.splitlines() if line.strip()),
            "author": author,
            "to": recipient,
            "status": "active",
            "created_at": created,
            "updated_at": created,
            "revision": 1,
        }
        validate(meta, body)
        atomic_write(sequence, str(identifier) + "\n")
        return save(scope.directory / f"{identifier:03d}.md", meta, body)


def archive(scope, identifier):
    with lock(scope.lock_path):
        note = get(scope, identifier)
        if note.meta["status"] == "archived":
            return note
        meta = dict(
            note.meta, status="archived", updated_at=now(), revision=note.meta["revision"] + 1
        )
        return save(note.path, meta, note.body)
