-- Esquema inicial de M1, docs/D1-SCHEMA.md. Não editar após aplicar.
CREATE TABLE identities (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  disabled_at TEXT
);

CREATE TABLE credentials (
  id TEXT PRIMARY KEY NOT NULL,
  identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
  verifier_sha256 TEXT NOT NULL UNIQUE CHECK(length(verifier_sha256) = 64),
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX credentials_identity ON credentials(identity_id);

CREATE TABLE scopes (
  id TEXT PRIMARY KEY NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('global', 'project')),
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT REFERENCES identities(id) ON DELETE RESTRICT,
  next_note_id INTEGER NOT NULL DEFAULT 1
    CHECK(next_note_id BETWEEN 1 AND 9007199254740992),
  CHECK((kind = 'global' AND id = 'global' AND name = 'global' AND created_by IS NULL)
     OR (kind = 'project' AND id <> 'global' AND created_by IS NOT NULL))
);
CREATE INDEX projects_name ON scopes(kind, name, id);

CREATE TABLE notes (
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE RESTRICT,
  id INTEGER NOT NULL CHECK(id BETWEEN 1 AND 9007199254740991),
  title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 256),
  body TEXT NOT NULL CHECK(length(CAST(body AS BLOB)) BETWEEN 1 AND 65536),
  title_fold TEXT NOT NULL,
  body_fold TEXT NOT NULL,
  to_recipient TEXT NOT NULL CHECK(to_recipient IN ('bruno', 'agents', 'all')),
  status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL CHECK(updated_at >= created_at),
  created_by TEXT NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
  updated_by TEXT NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
  revision_token TEXT NOT NULL UNIQUE,
  revision_number INTEGER NOT NULL DEFAULT 1
    CHECK(revision_number BETWEEN 1 AND 9007199254740991),
  PRIMARY KEY(scope_id, id)
);
CREATE INDEX notes_order ON notes(scope_id, status, updated_at DESC, id ASC);
CREATE INDEX notes_recipient ON notes(scope_id, status, to_recipient, updated_at DESC, id ASC);

-- Alocação só aceita o próximo ID e avança o contador no mesmo commit.
CREATE TRIGGER notes_check_next_id BEFORE INSERT ON notes
WHEN NEW.id <> (SELECT next_note_id FROM scopes WHERE id = NEW.scope_id)
BEGIN
  SELECT RAISE(ABORT, 'invalid_note_sequence');
END;
CREATE TRIGGER notes_advance_next_id AFTER INSERT ON notes
BEGIN
  UPDATE scopes SET next_note_id = next_note_id + 1 WHERE id = NEW.scope_id;
END;

CREATE TABLE idempotency_receipts (
  identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
  key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
  scope_id TEXT NOT NULL,
  note_id INTEGER NOT NULL,
  initial_revision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(identity_id, key),
  FOREIGN KEY(scope_id, note_id) REFERENCES notes(scope_id, id) ON DELETE RESTRICT
);

CREATE TABLE imported_notes (
  source_id TEXT NOT NULL,
  source_scope_id TEXT NOT NULL,
  source_note_id INTEGER NOT NULL CHECK(source_note_id BETWEEN 1 AND 9007199254740991),
  source_scope_name TEXT NOT NULL,
  source_schema_version INTEGER NOT NULL CHECK(source_schema_version = 1),
  source_author TEXT NOT NULL,
  source_created_at TEXT NOT NULL,
  source_updated_at TEXT NOT NULL,
  source_revision_number INTEGER NOT NULL
    CHECK(source_revision_number BETWEEN 1 AND 9007199254740991),
  raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
  payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
  scope_id TEXT NOT NULL,
  note_id INTEGER NOT NULL,
  imported_at TEXT NOT NULL,
  imported_by TEXT NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
  PRIMARY KEY(source_id, source_scope_id, source_note_id),
  UNIQUE(scope_id, note_id),
  CHECK(source_scope_id = scope_id),
  FOREIGN KEY(scope_id, note_id) REFERENCES notes(scope_id, id) ON DELETE RESTRICT
);
