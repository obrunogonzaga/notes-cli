"""Command-line interface. Domain failures never emit tracebacks or partial records."""

import argparse
import getpass
import sys

from . import store
from .files import NotesError
from .projects import initialize, resolve


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo")
    return number


def parser():
    result = argparse.ArgumentParser(prog="notes", description="Notas Markdown locais")
    result.add_argument("--version", action="version", version="notes 0.1.0")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Inicializar ou reconhecer o projeto atual")
    for name, help_text in (
        ("add", "Criar nota"),
        ("list", "Listar notas"),
        ("read", "Ler nota"),
        ("search", "Busca literal"),
        ("archive", "Arquivar nota"),
    ):
        command = commands.add_parser(name, help=help_text)
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--global", dest="global_scope", action="store_true")
        selection.add_argument("--project", metavar="NOME-OU-ID")
        if name == "add":
            command.add_argument("text", help="Corpo Markdown")
            command.add_argument("--author", default=getpass.getuser())
            command.add_argument("--to", choices=("bruno", "agents", "all"), default="all")
        if name in ("read", "archive"):
            command.add_argument("id", type=positive)
        if name in ("list", "search"):
            command.add_argument(
                "--archived", action="store_true", help="Consultar apenas notas arquivadas"
            )
        if name == "search":
            command.add_argument("query")
    return result


def label(scope, note):
    return f"[{scope.name} / {scope.id} #{note.meta['id']}]"


def receipt(scope, note):
    print(f"{label(scope, note)} {note.meta['title']}\n{note.path}")


def run(args):
    if args.command == "init":
        scope, root = initialize()
        print(f"Projeto {scope.name}: {scope.id}\n{root / '.notes-project'}")
        return 0
    scope = resolve(args.global_scope, args.project)
    if args.command == "add":
        receipt(scope, store.add(scope, args.text, args.author, args.to))
    elif args.command == "archive":
        receipt(scope, store.archive(scope, args.id))
    elif args.command == "read":
        note = store.get(scope, args.id)
        print(label(scope, note))
        meta = dict(note.meta)
        for key in ("created_at", "updated_at"):
            meta[key] = store.timestamp(meta[key]).astimezone().isoformat()
        print(store.serialize(meta, note.body), end="" if note.body.endswith("\n") else "\n")
    else:
        notes, errors = store.scan(scope)
        for note in notes:
            if note.meta["status"] != ("archived" if args.archived else "active"):
                continue
            if (
                args.command == "search"
                and args.query.casefold() not in (note.meta["title"] + "\n" + note.body).casefold()
            ):
                continue
            updated = store.timestamp(note.meta["updated_at"]).astimezone().isoformat()
            print(f"{label(scope, note)} {note.meta['title']} | to={note.meta['to']} | {updated}")
        for error in errors:
            print(f"notes: {error}", file=sys.stderr)
        return 1 if errors else 0
    return 0


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except (NotesError, OSError, UnicodeError) as exc:
        print(f"notes: {exc}; verifique os caminhos e permissões quando aplicável", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("notes: operação interrompida", file=sys.stderr)
        return 130
