"""Persistent project identity and a coordinated local registry."""

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .files import NotesError, atomic_write, data_home, dump_yaml, load_yaml, lock, read_text


def validate_project(value):
    if set(value) != {"id", "name"}:
        raise NotesError("a configuração deve conter apenas id e name")
    try:
        if str(uuid.UUID(value["id"])) != value["id"]:
            raise ValueError("UUID não canônico")
    except (ValueError, TypeError, AttributeError) as exc:
        raise NotesError("id deve ser um UUID canônico") from exc
    if not isinstance(value["name"], str) or not value["name"].strip():
        raise NotesError("name deve ser um texto não vazio")
    return value


@dataclass(frozen=True)
class Scope:
    id: str
    name: str

    @property
    def directory(self):
        if self.id == "global":
            return data_home() / "global"
        return data_home() / "projects" / self.id

    @property
    def lock_path(self):
        return data_home() / ".locks" / f"{self.id}.lock"

    def describe(self):
        return {
            "kind": "global" if self.id == "global" else "project",
            "id": self.id,
            "name": self.name,
        }


GLOBAL = Scope("global", "global")


def registry():
    path = data_home() / "projects.json"
    if not path.exists():
        return {"schema_version": 1, "projects": {}}
    try:
        value = json.loads(read_text(path))
        if value["schema_version"] != 1 or not isinstance(value["projects"], dict):
            raise ValueError("formato desconhecido")
        for identifier, project in value["projects"].items():
            validate_project({"id": identifier, "name": project["name"]})
            if not isinstance(project["paths"], list) or not all(
                isinstance(p, str) for p in project["paths"]
            ):
                raise ValueError("paths inválido")
        return value
    except (ValueError, KeyError, TypeError, NotesError) as exc:
        raise NotesError(f"{path}: registro inválido: {exc}; restaure uma cópia válida") from exc


def register(project, root):
    with lock(data_home() / ".locks" / "registry.lock"):
        value = registry()
        previous = value["projects"].get(project["id"], {})
        paths = sorted(set(previous.get("paths", []) + [str(root)]))
        updated = {"name": project["name"], "paths": paths}
        if previous != updated:
            value["projects"][project["id"]] = updated
            atomic_write(
                data_home() / "projects.json",
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            )
    return Scope(project["id"], project["name"])


def discover(cwd):
    for directory in (cwd, *cwd.parents):
        config = directory / ".notes-project"
        if config.exists() or config.is_symlink():
            try:
                return validate_project(load_yaml(read_text(config))), directory
            except NotesError as exc:
                raise NotesError(f"{config}: {exc}; corrija a configuração") from exc
    return None


def candidate(cwd):
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return cwd
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else cwd


def initialize():
    cwd = Path.cwd().resolve()
    found = discover(cwd)
    if found:
        project, root = found
    else:
        root = candidate(cwd)
        # All CLI initializers of the same canonical root share this lock.
        key = hashlib.sha256(str(root).encode()).hexdigest()
        with lock(data_home() / ".locks" / f"init-{key}.lock"):
            found = discover(cwd)
            if found:
                project, root = found
            else:
                project = {"id": str(uuid.uuid4()), "name": root.name}
                atomic_write(root / ".notes-project", dump_yaml(project))
    return register(project, root), root


def resolve(global_scope=False, project=None):
    if global_scope:
        return GLOBAL
    if project:
        projects = registry()["projects"]
        if project in projects:
            return Scope(project, projects[project]["name"])
        matches = [(key, entry) for key, entry in projects.items() if entry["name"] == project]
        if len(matches) == 1:
            return Scope(matches[0][0], matches[0][1]["name"])
        if matches:
            choices = ", ".join(sorted(key for key, _ in matches))
            raise NotesError(f"projeto ambíguo {project!r}: {choices}; use --project <id>")
        raise NotesError(f"projeto desconhecido {project!r}; execute notes init na pasta dele")
    cwd = Path.cwd().resolve()
    found = discover(cwd)
    if found:
        return register(*found)
    root = candidate(cwd)
    raise NotesError(
        f"projeto não inicializado; raiz candidata: {root}; execute notes init "
        "nessa pasta ou use --global"
    )
