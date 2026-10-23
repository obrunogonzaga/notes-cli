"""Versioned JSON and deterministic, whole-note context budgets."""

import json
import shlex
import sys

from . import store
from .projects import GLOBAL


def label(scope, note):
    return f"[{scope.name} / {scope.id} #{note.meta['id']}]"


def record(scope, note):
    return dict(
        note.meta,
        revision=note.revision,
        revision_number=note.meta["revision"],
        body=note.body,
        path=str(note.path),
        scope=scope.describe(),
    )


def emit_json(**payload):
    print(json.dumps({"schema_version": 1, **payload}, ensure_ascii=False))


def errors(messages):
    for message in messages:
        print(f"notes: {message}", file=sys.stderr)
    return 1 if messages else 0


def receipt(scope, note):
    print(f"{label(scope, note)} {note.meta['title']}\n{note.path}")


def read(scope, note, as_json):
    if as_json:
        emit_json(note=record(scope, note))
    else:
        print(label(scope, note))
        meta = dict(note.meta)
        for key in ("created_at", "updated_at"):
            meta[key] = store.timestamp(meta[key]).astimezone().isoformat()
        print(store.serialize(meta, note.body), end="" if note.body.endswith("\n") else "\n")


def listing(scope, notes, messages, as_json):
    if as_json:
        emit_json(notes=[record(scope, n) for n in notes], errors=messages)
    else:
        for note in notes:
            updated = store.timestamp(note.meta["updated_at"]).astimezone().isoformat()
            print(f"{label(scope, note)} {note.meta['title']} | to={note.meta['to']} | {updated}")
    return errors(messages)


def context_block(scope, note):
    return f"{label(scope, note)} {note.meta['title']}\n{note.body}\n\n"


def read_command(scope, note):
    selection = "--global" if scope.id == "global" else f"--project {shlex.quote(scope.id)}"
    return f"notes read {note.meta['id']} {selection}"


def context(scope, recipient, limit, as_json):
    entries, messages = [], []
    for source in [GLOBAL] if scope.id == "global" else [scope, GLOBAL]:
        notes, failures = store.scan(source)
        messages.extend(failures)
        entries.extend(
            (source, n)
            for n in notes
            if n.meta["status"] == "active" and n.meta["to"] in (recipient, "all")
        )
    entries.sort(
        key=lambda pair: (
            -store.timestamp(pair[1].meta["updated_at"]).timestamp(),
            pair[1].meta["id"],
            pair[0].id,
        )
    )
    selected, omitted, used = [], [], 0
    for source, note in entries:
        block = context_block(source, note)
        if used + len(block) <= limit:
            selected.append((source, note, block))
            used += len(block)
        else:
            omitted.append(
                {
                    "scope": source.describe(),
                    "id": note.meta["id"],
                    "read_command": read_command(source, note),
                }
            )
    if as_json:
        emit_json(
            notes=[record(source, note) for source, note, _ in selected],
            omitted=omitted,
            limit=limit,
            used_characters=used,
            errors=messages,
        )
    else:
        for _, _, block in selected:
            print(block, end="")
        for entry in omitted:
            print(
                f"Omitida {entry['scope']['id']} #{entry['id']} pelo limite; "
                f"leia com: {entry['read_command']}"
            )
    return errors(messages)
