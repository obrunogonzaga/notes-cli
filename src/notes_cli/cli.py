"""Command-line interface. Domain failures never emit tracebacks or partial records."""

import argparse
import getpass
import sys
from pathlib import Path

from . import editor, output, store
from .files import NotesError, read_text
from .projects import initialize, resolve


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("deve ser um inteiro não negativo")
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
        ("edit", "Editar nota"),
        ("search", "Busca literal"),
        ("archive", "Arquivar nota"),
        ("context", "Contexto de projeto e global para agentes"),
    ):
        command = commands.add_parser(name, help=help_text)
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--global", dest="global_scope", action="store_true")
        selection.add_argument("--project", metavar="NOME-OU-ID")
        if name in ("list", "read", "search", "context"):
            command.add_argument("--json", action="store_true", help="Saída estruturada v1")
        if name == "add":
            command.add_argument("text", nargs="?", help="Corpo Markdown; omita para stdin/editor")
            command.add_argument("--author", default=getpass.getuser())
            command.add_argument("--to", choices=("bruno", "agents", "all"), default="all")
        if name in ("read", "archive", "edit"):
            command.add_argument("id", type=positive)
        if name == "edit":
            command.add_argument("--body-file", type=Path, help="Substituir apenas o corpo")
            command.add_argument("--if-revision", help="Token opaco obtido em read --json")
        if name in ("list", "search"):
            command.add_argument(
                "--archived", action="store_true", help="Consultar apenas notas arquivadas"
            )
        if name == "search":
            command.add_argument("query")
        if name == "context":
            command.add_argument("--to", choices=("bruno", "agents", "all"), default="agents")
            command.add_argument(
                "--limit",
                type=nonnegative,
                default=12000,
                help="Orçamento de caracteres das notas (padrão: 12000)",
            )
    return result


def run(args):
    if args.command == "init":
        scope, root = initialize()
        print(f"Projeto {scope.name}: {scope.id}\n{root / '.notes-project'}")
        return 0
    scope = resolve(args.global_scope, args.project)
    if args.command == "add":
        if args.text is not None:
            note = store.add(scope, args.text, args.author, args.to)
        elif not sys.stdin.isatty():
            body = sys.stdin.buffer.read().decode("utf-8")
            note = store.add(scope, body, args.author, args.to)
        else:
            note = editor.create(scope, args.author, args.to)
        if note is not None:
            output.receipt(scope, note)
    elif args.command == "edit":
        if args.body_file is not None:
            note = store.edit(
                scope, args.id, body=read_text(args.body_file), expected=args.if_revision
            )
        else:
            note = editor.edit(scope, args.id, args.if_revision)
        output.receipt(scope, note)
    elif args.command == "archive":
        output.receipt(scope, store.archive(scope, args.id))
    elif args.command == "read":
        output.read(scope, store.get(scope, args.id), args.json)
    elif args.command == "context":
        return output.context(scope, args.to, args.limit, args.json)
    else:
        notes, errors = store.scan(scope)
        notes = [
            note
            for note in notes
            if note.meta["status"] == ("archived" if args.archived else "active")
        ]
        if args.command == "search":
            notes = [
                note
                for note in notes
                if args.query.casefold() in (note.meta["title"] + "\n" + note.body).casefold()
            ]
        return output.listing(scope, notes, errors, args.json)
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
