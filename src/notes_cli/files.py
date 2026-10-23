"""UTF-8 files, strict safe YAML, advisory locks and durable atomic replacement."""

import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml


class NotesError(Exception):
    """An actionable error suitable for stderr."""


class StrictLoader(yaml.SafeLoader):
    pass


# Keep timestamps as strings, including YAML timestamps written by another editor.
StrictLoader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in values if tag != "tag:yaml.org,2002:timestamp"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise NotesError("chave YAML inválida ou duplicada")
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor("tag:yaml.org,2002:map", mapping)


def load_yaml(text):
    try:
        value = yaml.load(text, Loader=StrictLoader)
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        raise NotesError(f"YAML inválido: {exc}") from exc
    if not isinstance(value, dict):
        raise NotesError("esperado um objeto YAML")
    return value


def dump_yaml(value):
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def read_text(path):
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise NotesError(
            f"{path}: não foi possível ler: {exc}; verifique arquivo e permissões"
        ) from exc


def data_home():
    value = os.environ.get("XDG_DATA_HOME")
    if value:
        root = Path(value).expanduser()
        if not root.is_absolute():
            raise NotesError("XDG_DATA_HOME deve ser um caminho absoluto")
    else:
        root = Path.home() / ".local" / "share"
    return root / "notes"


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".notes-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
