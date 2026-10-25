import { env, exports } from 'cloudflare:workers';
import { applyD1Migrations } from 'cloudflare:test';
import { beforeEach, expect, it } from 'vitest';
import { activeCredentialGuard, activeCredentialStatement, authenticate, authenticatedAuthor } from '../src/auth';
import type { AuthenticatedIdentity } from '../src/auth';
import { generateToken, parseToken, tokenVerifier } from '../src/token';

const db = env.DB;
const now = '2026-10-23T12:00:00.000Z';
const aliceId = '30000000-0000-4000-8000-000000000001';
const bobId = '30000000-0000-4000-8000-000000000002';
let alice: ReturnType<typeof generateToken>;
let bob: ReturnType<typeof generateToken>;
const request = (token?: string, body?: object) => new Request('http://localhost/v1', {
  method: body ? 'POST' : 'GET',
  headers: token ? { Authorization: `Bearer ${token}` } : {},
  ...(body && { body: JSON.stringify(body) }),
});
const sql = (query: string, ...params: (string | number)[]) => db.prepare(query).bind(...params);
async function issue(identityId: string) {
  const result = generateToken(identityId);
  await sql('INSERT INTO credentials VALUES (?, ?, ?, ?, NULL)', result.credentialId, identityId, await tokenVerifier(result.token), now).run();
  return result;
}
async function principal(token: string) {
  const auth = await authenticate(request(token), db);
  expect(auth).not.toBeNull();
  return auth!;
}

beforeEach(async () => {
  for (const table of ['imported_notes', 'idempotency_receipts', 'notes', 'scopes', 'credentials', 'identities', 'd1_migrations']) {
    await db.prepare(`DROP TABLE IF EXISTS ${table}`).run();
  }
  await applyD1Migrations(db, env.TEST_MIGRATIONS);
  await db.batch([
    sql('INSERT INTO identities VALUES (?, ?, ?, NULL)', aliceId, 'fixture-alice', now),
    sql('INSERT INTO identities VALUES (?, ?, ?, NULL)', bobId, 'fixture-bob', now),
  ]);
  alice = await issue(aliceId);
  bob = await issue(bobId);
});

it('generates canonical nt1 tokens with v4 IDs, 256 random bits and full-token SHA-256 only in D1', async () => {
  const parts = alice.token.split('.');
  expect(parseToken(alice.token)).toEqual({ identityId: aliceId, credentialId: alice.credentialId });
  expect(parts[3]).toHaveLength(43);
  expect(atob(parts[3]!.replaceAll('-', '+').replaceAll('_', '/'))).toHaveLength(32);
  expect(generateToken(aliceId).token).not.toBe(alice.token);
  const verifier = await tokenVerifier(alice.token);
  const { createHash } = await import('node:crypto');
  expect(verifier).toBe(createHash('sha256').update(alice.token, 'ascii').digest('hex'));
  const stored = await sql('SELECT * FROM credentials WHERE id = ?', alice.credentialId).first();
  expect(stored).toEqual({ id: alice.credentialId, identity_id: aliceId, verifier_sha256: verifier, created_at: now, revoked_at: null });
  expect(JSON.stringify(stored)).not.toContain(parts[3]);
});

it('rejects malformed, noncanonical, forged and unknown tokens or Authorization schemes', async () => {
  const parts = alice.token.split('.');
  for (const token of [
    '', 'bad', alice.token.replace('nt1.', 'nt2.'), `${alice.token}=`,
    alice.token.replace(aliceId, aliceId.replace('-4000-', '-1000-')),
    alice.token.replace(aliceId, aliceId.replace('-8000-', '-7000-')),
    alice.token.replace(alice.credentialId, alice.credentialId.toUpperCase()),
    [...parts.slice(0, 3), `${parts[3]!.slice(0, 42)}B`].join('.'),
    alice.token.replace(aliceId, bobId), alice.token.replace(alice.credentialId, bob.credentialId),
    generateToken(aliceId).token, `${parts.slice(0, 3).join('.')}.${'A'.repeat(43)}`,
  ]) expect(await authenticate(request(token), db)).toBeNull();
  expect(parseToken(`${alice.token}\nextra`)).toBeNull();
  for (const header of ['Basic secret', `Bearer ${alice.token}, Bearer ${bob.token}`, `Bearer  ${alice.token}`, `Bearer\t${alice.token}`]) {
    expect(await authenticate(new Request('http://localhost/v1', { headers: { Authorization: header } }), db)).toBeNull();
  }
  expect(await authenticate(request(), db)).toBeNull();
  expect(await authenticate(new Request('http://localhost/v1', { headers: { Authorization: `bearer ${alice.token}` } }), db)).not.toBeNull();
});

it('derives distinct immutable authors from authenticated identities despite client author/to fields', async () => {
  const first = await authenticate(request(alice.token, { author: 'fixture-bob', created_by: { id: bobId }, updated_by: bobId, to: 'agents' }), db);
  const second = await authenticate(request(bob.token, { author: 'fixture-alice', to: 'bruno' }), db);
  expect(authenticatedAuthor(first!)).toEqual({ id: aliceId, name: 'fixture-alice' });
  expect(authenticatedAuthor(second!)).toEqual({ id: bobId, name: 'fixture-bob' });
  expect(Object.isFrozen(first)).toBe(true);
  expect(Object.isFrozen(first!.identity)).toBe(true);
  expect(Object.keys(first!)).toEqual(['identity', 'credentialId']);
});

it('protects all /v1 routes and methods before resource, payload, query or method inspection', async () => {
  const routes = ['/v1', '/v1/', '/v1/projects', `/v1/projects/${aliceId}`, '/v1/scopes/global/notes',
    '/v1/scopes/missing/notes/1', '/v1/scopes/global/notes/1/archive', '/v1/scopes/global/search?q=secret',
    '/v1/context?scope=missing', '/v1/imports', '/v1/imports/preview', '/v1/does-not-exist'];
  for (const path of routes) for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']) {
    const response = await exports.default.fetch(`http://localhost${path}`, { method, headers: {
      Accept: 'text/plain', 'Content-Type': 'text/plain', 'X-Author': 'fixture-bob',
    } });
    expect(response.status).toBe(401);
    expect(response.headers.get('WWW-Authenticate')).toBe('Bearer');
    expect(response.headers.get('Allow')).toBeNull();
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    if (method !== 'HEAD') expect(await response.json()).toEqual({
      api: 'notes-remote', schema_version: 1, request_id: response.headers.get('X-Request-ID'),
      error: { code: 'unauthorized', message: 'Credencial ausente ou inválida.', retryable: false },
    });
    else await response.text();
  }
  const valid = await exports.default.fetch('http://localhost/v1/does-not-exist', { headers: { Authorization: `Bearer ${alice.token}` } });
  expect(valid.status).toBe(404);
  await valid.text();
  const otherVersion = await exports.default.fetch('http://localhost/v2');
  expect(otherVersion.status).toBe(404);
  await otherVersion.text();
});

it('revalidates revoked/disabled credentials per request and retry; rotation keeps the identity', async () => {
  const rotated = await issue(aliceId);
  expect((await principal(rotated.token)).identity).toEqual((await principal(alice.token)).identity);
  await sql('UPDATE credentials SET revoked_at = ? WHERE id = ?', now, alice.credentialId).run();
  for (const method of ['GET', 'POST', 'GET', 'POST']) {
    const denied = await exports.default.fetch('http://localhost/v1/scopes/global/notes', {
      method, headers: { Authorization: `Bearer ${alice.token}`, 'Idempotency-Key': crypto.randomUUID() },
    });
    expect(denied.status).toBe(401);
    await denied.text();
  }
  await principal(rotated.token);
  await principal(bob.token);
  await sql('UPDATE identities SET disabled_at = ? WHERE id = ?', now, aliceId).run();
  expect(await authenticate(request(rotated.token), db)).toBeNull();
  await principal(bob.token);
});

it('uses the same 401 for absent, invalid, revoked, disabled and mismatched identities', async () => {
  const revoked = await issue(aliceId);
  const disabled = await issue(bobId);
  await sql('UPDATE credentials SET revoked_at = ? WHERE id = ?', now, revoked.credentialId).run();
  await sql('UPDATE identities SET disabled_at = ? WHERE id = ?', now, bobId).run();
  const forged = alice.token.replace(aliceId, bobId);
  // Mesmo um verificador igual não autoriza usar o UUID de outra identidade.
  await sql('UPDATE credentials SET verifier_sha256 = ? WHERE id = ?', await tokenVerifier(forged), alice.credentialId).run();
  expect(await authenticate(request(forged), db)).toBeNull();
  for (const token of [undefined, 'invalid', generateToken(aliceId).token, revoked.token, disabled.token, forged]) {
    for (const path of ['/v1/projects', '/v1/scopes/global/notes/1', '/v1/unknown']) {
      for (const method of ['GET', 'POST']) {
        const response = await exports.default.fetch(`http://localhost${path}`, {
          method, headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        expect(response.status).toBe(401);
        expect(response.headers.get('WWW-Authenticate')).toBe('Bearer');
        expect(await response.json()).toEqual({
          api: 'notes-remote', schema_version: 1, request_id: response.headers.get('X-Request-ID'),
          error: { code: 'unauthorized', message: 'Credencial ausente ou inválida.', retryable: false },
        });
      }
    }
  }
});

// Fixtures SQL de integração, não handlers CRUD nem validação de payload da #10.
function syntheticNote(auth: AuthenticatedIdentity, to: string, id: number) {
  const guard = activeCredentialGuard(auth);
  const author = authenticatedAuthor(auth);
  return sql(`INSERT INTO notes
    SELECT 'global', ?, 'fixture', 'fixture', 'fixture', 'fixture', ?, 'active', ?, ?, ?, ?, ?, 1
    WHERE ${guard.sql}`, id, to, now, now, author.id, author.id, `r_${crypto.randomUUID()}`, ...guard.bindings);
}

it('persists authenticated creator/editor in synthetic commits and never treats recipient as ACL', async () => {
  const a = await principal(alice.token);
  const b = await principal(bob.token);
  await db.batch([syntheticNote(a, 'bruno', 1), syntheticNote(b, 'agents', 2), syntheticNote(a, 'all', 3)]);
  for (const auth of [a, b]) {
    const guard = activeCredentialGuard(auth);
    const read = await db.batch([
      activeCredentialStatement(db, auth),
      sql(`SELECT id, to_recipient, created_by FROM notes WHERE ${guard.sql} ORDER BY id`, ...guard.bindings),
    ]);
    expect(read[0]!.results).toEqual([{ active: 1 }]);
    expect(read[1]!.results).toEqual([
      { id: 1, to_recipient: 'bruno', created_by: aliceId },
      { id: 2, to_recipient: 'agents', created_by: bobId },
      { id: 3, to_recipient: 'all', created_by: aliceId },
    ]);
  }
  const guard = activeCredentialGuard(b);
  await sql(`UPDATE notes SET updated_by = ? WHERE id = 1 AND ${guard.sql}`, authenticatedAuthor(b).id, ...guard.bindings).run();
  expect(await db.prepare('SELECT created_by, updated_by FROM notes WHERE id = 1').first()).toEqual({ created_by: aliceId, updated_by: bobId });
});

it('blocks a previously authenticated write after revocation wins, including no-op/replay classification', async () => {
  const a = await principal(alice.token);
  const b = await principal(bob.token);
  await syntheticNote(a, 'all', 1).run();
  await sql('INSERT INTO idempotency_receipts VALUES (?, ?, ?, ?, ?, ?, ?)', aliceId, 'fixture-key', 'a'.repeat(64), 'global', 1, 'r_initial', now).run();
  await sql('UPDATE credentials SET revoked_at = ? WHERE id = ?', now, alice.credentialId).run();
  const guard = activeCredentialGuard(a);
  const results = await db.batch([
    syntheticNote(a, 'all', 2),
    sql(`UPDATE notes SET updated_by = ? WHERE id = 1 AND ${guard.sql}`, bobId, ...guard.bindings),
    activeCredentialStatement(db, a),
    sql(`SELECT key FROM idempotency_receipts WHERE identity_id = ? AND ${guard.sql}`, aliceId, ...guard.bindings),
  ]);
  expect(results[0]!.meta.changes).toBe(0);
  expect(results[1]!.meta.changes).toBe(0);
  expect(results[2]!.results).toEqual([{ active: 0 }]);
  expect(results[3]!.results).toEqual([]);
  expect(await db.prepare('SELECT next_note_id FROM scopes WHERE id = \'global\'').first('next_note_id')).toBe(2);
  expect(await db.prepare('SELECT updated_by FROM notes WHERE id = 1').first('updated_by')).toBe(aliceId);
  const rotated = await issue(aliceId);
  const fresh = await principal(rotated.token);
  const freshGuard = activeCredentialGuard(fresh);
  expect(await sql(`SELECT key FROM idempotency_receipts WHERE identity_id = ? AND ${freshGuard.sql}`, aliceId, ...freshGuard.bindings).all()).toMatchObject({ results: [{ key: 'fixture-key' }] });
  await syntheticNote(b, 'all', 2).run();
  await sql('UPDATE identities SET disabled_at = ? WHERE id = ?', now, bobId).run();
  expect((await syntheticNote(b, 'all', 3).run()).meta.changes).toBe(0);
  expect(await activeCredentialStatement(db, b).first('active')).toBe(0);
});

it('fails closed on corrupted verifier or D1 failure without exposing secrets, SQL or stack', async () => {
  await sql('UPDATE credentials SET verifier_sha256 = ? WHERE id = ?', 'G'.repeat(64), alice.credentialId).run();
  const denied = await exports.default.fetch(request(alice.token));
  expect(denied.status).toBe(401);
  expect(await denied.text()).not.toContain(alice.token);
  await db.prepare('DROP TABLE credentials').run();
  const response = await exports.default.fetch(request(alice.token));
  expect(response.status).toBe(503);
  expect(response.headers.get('Retry-After')).toBe('1');
  expect(await response.json()).toEqual({
    api: 'notes-remote', schema_version: 1, request_id: response.headers.get('X-Request-ID'),
    error: { code: 'service_unavailable', message: 'Serviço indisponível.', retryable: true },
  });
  const health = await exports.default.fetch('http://localhost/healthz');
  expect(health.status).toBe(200);
  await health.text();
});
