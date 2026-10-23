#!/usr/bin/env python3
"""Reproduce the Bruno/agent workflow using an installed CLI and isolated local data."""

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def pilot(executable):
    transcript = []
    with tempfile.TemporaryDirectory(prefix="notes-pilot-") as temporary:
        root = Path(temporary)
        project = root / "checkout"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs/auth.md").write_text("# Autenticação\nManter sessões existentes.\n")
        work = project / "src"
        work.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        env = dict(os.environ, HOME=str(root / "home"), XDG_DATA_HOME=str(root / "data"))
        env.pop("PYTHONPATH", None)

        def notes(actor, *args, input=None, success=True):
            result = subprocess.run(
                [executable, *args],
                cwd=work,
                env=env,
                input=input,
                capture_output=True,
                text=True,
                timeout=20,
                start_new_session=True,
            )
            transcript.append(
                {
                    "actor": actor,
                    "args": [str(arg).replace(str(root), "<sandbox>") for arg in args],
                    "exit_code": result.returncode,
                    "stdout": result.stdout.replace(str(root), "<sandbox>"),
                    "stderr": result.stderr.replace(str(root), "<sandbox>"),
                }
            )
            if (result.returncode == 0) != success:
                raise RuntimeError(f"Unexpected result for {args}: {result.stderr}")
            return result.stdout

        version = notes("verification", "--version").strip()
        notes("bruno", "init")
        notes(
            "bruno",
            "add",
            "--to",
            "agents",
            "--author",
            "bruno",
            input="# Contexto do login\n\nLeia docs/auth.md. Preservar sessões existentes.\n",
        )
        notes("bruno", "add", "Preferir respostas em português", "--global", "--to", "agents")
        context = json.loads(notes("agent", "context", "--json"))
        assert len(context["notes"]) == 2
        assert {n["scope"]["kind"] for n in context["notes"]} == {"global", "project"}
        notes(
            "agent",
            "add",
            "Escolher o provedor de e-mail antes dos envios.",
            "--to",
            "bruno",
            "--author",
            "codex",
        )
        # A separate OS process/session represents the next human terminal session.
        inbox = json.loads(notes("bruno-new-session", "context", "--to", "bruno", "--json"))
        assert len(inbox["notes"]) == 1
        assert inbox["notes"][0]["author"] == "codex" and inbox["notes"][0]["id"] == 2
        before = json.loads(notes("bruno-new-session", "read", "2", "--json"))["note"]
        body = root / "decision.md"
        body.write_text("Decisão: usar o provedor escolhido no piloto.\n")
        notes(
            "bruno-new-session",
            "edit",
            "2",
            "--body-file",
            str(body),
            "--if-revision",
            before["revision"],
        )
        notes(
            "stale-agent",
            "edit",
            "2",
            "--body-file",
            str(body),
            "--if-revision",
            before["revision"],
            success=False,
        )
        found = json.loads(notes("agent", "search", "DECISÃO", "--json"))
        assert len(found["notes"]) == 1 and found["notes"][0]["revision_number"] == 2
        notes("bruno-new-session", "archive", "2")
        notes("bruno-new-session", "archive", "2")
        assert not json.loads(notes("bruno-new-session", "context", "--to", "bruno", "--json"))[
            "notes"
        ]
        archived = json.loads(notes("bruno-new-session", "list", "--archived", "--json"))["notes"]
        assert len(archived) == 1 and archived[0]["revision_number"] == 3
        assert (
            json.loads(notes("bruno-new-session", "read", "2", "--json"))["note"]["body"]
            == body.read_text()
        )
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cli_version": version,
            "mode": "automated",
            "human_participation": False,
            "result": "passed",
            "commands": len(transcript),
            "transcript": transcript,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", default="notes", help="Caminho do executável instalado")
    parser.add_argument("--output", type=Path, help="Salvar evidências JSON")
    args = parser.parse_args()
    executable = str(Path(args.notes).resolve()) if "/" in args.notes else args.notes
    result = pilot(executable)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
