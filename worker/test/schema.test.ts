import { env, exports } from 'cloudflare:workers';
import { applyD1Migrations } from 'cloudflare:test';
import { beforeEach, expect, it } from 'vitest';

const db = env.DB;
const now = '2026-10-23T12:00:00.000Z';
const identity = '30000000-0000-4000-8000-000000000001';
const project = '80000000-0000-4000-8000-000000000001';
const hash = 'a'.repeat(64);
const sql = (query: string, ...values: (string | number | null)[]) => db.prepare(query).bind(...values);
const count = (table: string) => db.prepare(`SELECT count(*) FROM ${table}`).first<number>('count(*)');
const next = (scope = 'global') => sql('SELECT next_note_id FROM scopes WHERE id = ?', scope).first<number>('next_note_id');

async function note(overrides: Record<string, string | number> = {}) {
  const fields = {
    scope_id: 'global', id: 1, title: 'Escolhemos Go', body: 'Escolhemos Go\r\n😀\n',
    title_fold: 'escolhemos go', body_fold: 'escolhemos go\r\n😀\n', to_recipient: 'all',
    status: 'active', created_at: now, updated_at: now, created_by: identity,
    updated_by: identity, revision_token: `r_${crypto.randomUUID()}`, revision_number: 1,
    ...overrides,
  };
  return sql(`INSERT INTO notes (${Object.keys(fields).join(',')}) VALUES (${Object.keys(fields).map(() => '?').join(',')})`, ...Object.values(fields));
}
function receipt(key = 'key', noteId = 1, scope = 'global', who = identity) {
  return sql('INSERT INTO idempotency_receipts VALUES (?, ?, ?, ?, ?, ?, ?)', who, key, hash, scope, noteId, 'r_initial', now);
}
function origin(source = 'source', sourceId = 12, noteId = 1, sourceScope = 'global', scope = 'global') {
  return sql('INSERT INTO imported_notes VALUES (?, ?, ?, ?, 1, ?, ?, ?, 3, ?, ?, ?, ?, ?, ?)',
    source, sourceScope, sourceId, 'historical scope', 'local author', now, now, hash, hash, scope, noteId, now, identity);
}

beforeEach(async () => {
  // O plugin isola por arquivo; reiniciar o banco explicitamente entre casos.
  for (const table of ['imported_notes', 'idempotency_receipts', 'notes', 'scopes', 'credentials', 'identities', 'd1_migrations']) {
    await db.prepare(`DROP TABLE IF EXISTS ${table}`).run();
  }
  await applyD1Migrations(db, env.TEST_MIGRATIONS);
  await sql('INSERT INTO identities VALUES (?, ?, ?, NULL)', identity, 'fixture', now).run();
});

it('applies a fresh schema and reapplies without resetting global or existing data', async () => {
  await (await note()).run();
  await applyD1Migrations(db, env.TEST_MIGRATIONS);
  expect(await count('d1_migrations')).toBe(env.TEST_MIGRATIONS.length);
  expect(await count('scopes')).toBe(1);
  expect(await next()).toBe(2);
  expect(await db.prepare("SELECT kind, name, created_at, created_by FROM scopes WHERE id = 'global'").first()).toEqual({
    kind: 'global', name: 'global', created_at: '2026-10-23T00:00:00.000Z', created_by: null,
  });
  expect(await db.prepare('PRAGMA foreign_keys').first<number>('foreign_keys')).toBe(1);
  expect((await db.prepare('PRAGMA foreign_key_check').all()).results).toEqual([]);
});

it('installs both sequence triggers, all explicit indexes and all FK links', async () => {
  const objects = (await db.prepare("SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'index') AND name NOT LIKE 'sqlite_%' ORDER BY name").all()).results;
  for (const [type, name] of [
    ['trigger', 'notes_check_next_id'], ['trigger', 'notes_advance_next_id'],
    ['index', 'credentials_identity'], ['index', 'projects_name'],
    ['index', 'notes_order'], ['index', 'notes_recipient'],
  ]) expect(objects).toContainEqual({ type, name });
  for (const [table, expected] of [['credentials', 1], ['scopes', 1], ['notes', 3], ['idempotency_receipts', 3], ['imported_notes', 3]] as const) {
    const { results } = await db.prepare(`PRAGMA foreign_key_list(${table})`).all();
    expect(results).toHaveLength(expected);
    expect(results.every((fk) => fk.on_delete === 'RESTRICT')).toBe(true);
  }
  const { results } = await db.prepare('PRAGMA index_xinfo(notes_order)').all();
  expect(results.filter((r) => r.key === 1).map((r) => [r.name, r.desc])).toEqual([
    ['scope_id', 0], ['status', 0], ['updated_at', 1], ['id', 0],
  ]);
});

it('requires identities and stores unique credential verifiers, with revocation retained', async () => {
  await expect(sql('INSERT INTO credentials VALUES (?, ?, ?, ?, NULL)', 'cred', 'missing', hash, now).run()).rejects.toThrow(/FOREIGN KEY/);
  await sql('INSERT INTO credentials VALUES (?, ?, ?, ?, NULL)', 'cred', identity, hash, now).run();
  await expect(sql('INSERT INTO credentials VALUES (?, ?, ?, ?, NULL)', 'other', identity, hash, now).run()).rejects.toThrow(/UNIQUE/);
  await expect(sql('INSERT INTO credentials VALUES (?, ?, ?, ?, NULL)', 'other', identity, 'short', now).run()).rejects.toThrow(/CHECK/);
  await expect(sql('INSERT INTO identities VALUES (?, ?, ?, NULL)', 'other', 'fixture', now).run()).rejects.toThrow(/UNIQUE/);
  await sql('UPDATE credentials SET revoked_at = ? WHERE id = ?', now, 'cred').run();
  await sql('UPDATE identities SET disabled_at = ? WHERE id = ?', now, identity).run();
  expect(await count('credentials')).toBe(1);
  await expect(sql('DELETE FROM identities WHERE id = ?', identity).run()).rejects.toThrow(/FOREIGN KEY/);
});

it('keeps projects distinct by UUID with duplicate names and independent note sequences', async () => {
  await expect(sql("INSERT INTO scopes VALUES (?, 'project', 'same', ?, NULL, 1)", project, now).run()).rejects.toThrow(/CHECK/);
  for (const id of [project, 'other-project']) {
    await sql("INSERT INTO scopes VALUES (?, 'project', 'same', ?, ?, 1)", id, now, identity).run();
    await (await note({ scope_id: id })).run();
    expect(await next(id)).toBe(2);
  }
  await expect(sql("UPDATE scopes SET name = 'renamed' WHERE id = 'global'").run()).rejects.toThrow(/CHECK/);
  expect(await next()).toBe(1);
  await expect(sql('DELETE FROM scopes WHERE id = ?', project).run()).rejects.toThrow(/FOREIGN KEY/);
});

it('rejects skipped/reused IDs and allocates successive IDs in a batch', async () => {
  await expect((await note({ id: 2 })).run()).rejects.toThrow(/invalid_note_sequence/);
  await db.batch([await note(), await note({ id: 2 })]);
  expect(await next()).toBe(3);
  await expect((await note()).run()).rejects.toThrow(/invalid_note_sequence/);
  await expect((await note({ scope_id: 'missing' })).run()).rejects.toThrow(/FOREIGN KEY/);
  expect(await count('notes')).toBe(2);
});

it('enforces note enums, byte/title limits, timestamps, authors and revision bounds', async () => {
  const invalid: Record<string, string | number>[] = [
    { body: '' }, { body: '😀'.repeat(16385) }, { title: '' }, { title: 'a'.repeat(257) },
    { to_recipient: 'unknown' }, { status: 'deleted' }, { updated_at: '2025-01-01T00:00:00.000Z' },
    { revision_number: 0 }, { revision_number: 9007199254740992 },
  ];
  for (const changes of invalid) await expect((await note(changes)).run()).rejects.toThrow(/CHECK/);
  await expect((await note({ updated_by: 'missing' })).run()).rejects.toThrow(/FOREIGN KEY/);
  await (await note({ title: '😀'.repeat(256), body: '😀'.repeat(16384) })).run();
  await expect((await note({ id: 2, revision_token: (await sql('SELECT revision_token FROM notes WHERE id = 1').first<string>('revision_token'))! })).run()).rejects.toThrow(/UNIQUE/);
  expect(await next()).toBe(2);
});

it('accepts the last safe ID and leaves only the exhaustion sentinel', async () => {
  await db.prepare("UPDATE scopes SET next_note_id = 9007199254740991 WHERE id = 'global'").run();
  await (await note({ id: 9007199254740991 })).run();
  expect(await next()).toBe(9007199254740992);
  await expect((await note({ id: 9007199254740992 })).run()).rejects.toThrow(/CHECK/);
});

it('keys permanent receipts by identity, not credential or scope, and requires a note', async () => {
  await (await note()).run();
  await receipt().run();
  await expect(receipt().run()).rejects.toThrow(/UNIQUE/);
  await sql("INSERT INTO scopes VALUES (?, 'project', 'fixture', ?, ?, 1)", project, now, identity).run();
  await (await note({ scope_id: project })).run();
  await expect(receipt('key', 1, project).run()).rejects.toThrow(/UNIQUE/);
  await expect(receipt('orphan', 2).run()).rejects.toThrow(/FOREIGN KEY/);
  await sql('INSERT INTO identities VALUES (?, ?, ?, NULL)', 'other', 'other', now).run();
  await receipt('key', 1, 'global', 'other').run();
  await expect(sql("UPDATE idempotency_receipts SET request_sha256 = 'short'").run()).rejects.toThrow(/CHECK/);
  await expect(db.prepare('DELETE FROM notes').run()).rejects.toThrow(/FOREIGN KEY/);
});

it('rolls back a note and trigger counter if the receipt fails later in the batch', async () => {
  await (await note()).run();
  await receipt().run();
  await expect(db.batch([await note({ id: 2 }), receipt()])).rejects.toThrow(/UNIQUE/);
  expect(await next()).toBe(2);
  expect(await count('notes')).toBe(1);
  expect(await count('idempotency_receipts')).toBe(1);
});

it('keeps origin unique, scope-bound and linked after remote edits or identity disablement', async () => {
  await db.batch([await note(), await note({ id: 2 })]);
  await origin().run();
  await expect(origin('source', 12, 2).run()).rejects.toThrow(/UNIQUE/);
  await expect(origin('another-source', 12, 1).run()).rejects.toThrow(/UNIQUE/);
  await expect(origin('another-source', 12, 2, 'other-scope').run()).rejects.toThrow(/CHECK/);
  await expect(origin('orphan', 1, 3).run()).rejects.toThrow(/FOREIGN KEY/);
  const original = await db.prepare('SELECT * FROM imported_notes').first();
  for (const mutation of [
    'source_schema_version = 2', 'source_note_id = 0', 'source_revision_number = 0',
    "raw_sha256 = 'short'", "payload_sha256 = 'short'",
  ]) await expect(db.prepare(`UPDATE imported_notes SET ${mutation}`).run()).rejects.toThrow(/CHECK/);
  await sql("UPDATE notes SET body = 'edited remotely', status = 'archived', revision_number = 2, revision_token = 'r_new' WHERE id = 1").run();
  await sql('UPDATE identities SET disabled_at = ?', now).run();
  expect(await db.prepare('SELECT * FROM imported_notes').first()).toEqual(original);
  await expect(sql('DELETE FROM notes WHERE id = 1').run()).rejects.toThrow(/FOREIGN KEY/);
});

it('rolls back a new project, note and counter when origin registration fails', async () => {
  await (await note()).run();
  await origin().run();
  await expect(db.batch([
    sql("INSERT INTO scopes VALUES (?, 'project', 'new', ?, ?, 1)", project, now, identity),
    await note({ scope_id: project }),
    // Existing source key: the entire batch must roll back.
    origin(),
  ])).rejects.toThrow(/UNIQUE/);
  expect(await sql('SELECT id FROM scopes WHERE id = ?', project).first()).toBeNull();
  expect(await count('notes')).toBe(1);
  expect(await next()).toBe(2);
  expect(await count('imported_notes')).toBe(1);
});

it('serves a minimal readiness probe and leaves business routes unavailable', async () => {
  const response = await exports.default.fetch('http://localhost/healthz');
  expect(response.status).toBe(200);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  const body = await response.json<Record<string, unknown>>();
  expect(body).toEqual({ api: 'notes-remote', schema_version: 1, request_id: response.headers.get('X-Request-ID'), status: 'ready' });
  const unsupported = await exports.default.fetch('http://localhost/healthz', { method: 'POST' });
  expect(unsupported.status).toBe(405);
  expect(unsupported.headers.get('Allow')).toBe('GET');
  await unsupported.text();
  const unknown = await exports.default.fetch('http://localhost/v1/scopes/global/notes');
  expect(unknown.status).toBe(404);
  await unknown.text();
});

it('reports missing seed or schema as 503 without SQL, content or stack', async () => {
  await db.prepare("DELETE FROM scopes WHERE id = 'global'").run();
  for (const dropSchema of [false, true]) {
    if (dropSchema) await db.prepare('DROP TABLE scopes').run();
    const response = await exports.default.fetch('http://localhost/healthz');
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      api: 'notes-remote', schema_version: 1, request_id: response.headers.get('X-Request-ID'),
      error: { code: 'service_unavailable', message: 'Serviço indisponível.', retryable: true },
    });
  }
});
