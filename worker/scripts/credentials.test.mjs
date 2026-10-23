import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { chmod, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import test from 'node:test';
import { getPlatformProxy } from 'wrangler';
import { readPrivateFile, writeNewPrivateFile } from './private-files.mjs';
import { validateOperation } from './credential-operations.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const processEnv = { ...process.env, CI: 'true', WRANGLER_SEND_METRICS: 'false' };
const run = promisify(execFile);
async function workspace(t) {
  await mkdir(join(root, '.wrangler'), { recursive: true });
  const path = await mkdtemp(join(root, '.wrangler/credentials-'));
  t.after(() => rm(path, { recursive: true, force: true }));
  return path;
}
function cli(input, args = [], inputPath = '-') {
  return new Promise((resolveResult, reject) => {
    const child = spawn(process.execPath, [...args, join(root, 'scripts/credentials.mjs'), '--input', inputPath], {
      cwd: root, env: processEnv, stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => { child.kill(); reject(new Error('operator timeout')); }, 20000);
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', (code) => { clearTimeout(timer); resolveResult({ code, stdout, stderr }); });
    child.stdin.end(JSON.stringify(input));
  });
}

async function startWorker(state, t) {
  const child = spawn(process.execPath, [join(root, 'node_modules/wrangler/bin/wrangler.js'), 'dev',
    '--local', '--ip', '127.0.0.1', '--port', '0', '--inspector-port', '0', '--persist-to', state],
  { cwd: root, env: processEnv, stdio: ['ignore', 'pipe', 'pipe'] });
  const exited = once(child, 'exit');
  t.after(async () => { if (child.exitCode === null) child.kill('SIGTERM'); await exited; });
  let logs = '';
  const url = await new Promise((resolveUrl, reject) => {
    const timer = setTimeout(() => reject(new Error('Worker startup timeout')), 20000);
    const output = (chunk) => {
      logs += chunk;
      const match = logs.match(/Ready on (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) { clearTimeout(timer); resolveUrl(match[1]); }
    };
    child.stdout.on('data', output);
    child.stderr.on('data', output);
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', () => { clearTimeout(timer); reject(new Error('Worker exited')); });
  });
  return {
    logs: () => logs,
    probe: async (token, expectedStatus) => {
      for (const method of ['GET', 'POST']) {
        const response = await fetch(`${url}/v1/scopes/global/notes`, { method, headers: { Authorization: `Bearer ${token}` } });
        assert.equal(response.status, expectedStatus);
        await response.text();
      }
    },
  };
}

test('operator + persisted D1: separate identities, rotation, revocation, disablement, rollback and protected output', { timeout: 120000 }, async (t) => {
  const path = await workspace(t);
  const state = join(path, 'state');
  await run(process.execPath, [join(root, 'node_modules/wrangler/bin/wrangler.js'), 'd1', 'migrations', 'apply',
    'notes-local', '--local', '--persist-to', state], { cwd: root, env: processEnv, timeout: 20000 });
  const platform = await getPlatformProxy({ configPath: join(root, 'wrangler.jsonc'), envFiles: [], remoteBindings: false, persist: { path: join(state, 'v3') } });
  t.after(() => platform.dispose());
  const db = platform.env.DB;
  const worker = await startWorker(state, t);
  const target = { mode: 'local', persist_to: state };
  const outputs = [];
  const tokens = [];
  async function apply(action, expectedCode = 0, inputPath = '-') {
    const result = await cli({ target, action }, [], inputPath);
    outputs.push(result.stdout, result.stderr);
    assert.equal(result.code, expectedCode, 'unexpected operator exit (diagnostic intentionally redacted)');
    assert.equal(expectedCode ? result.stdout : result.stderr, '');
    const report = JSON.parse(expectedCode ? result.stderr : result.stdout);
    assert.equal(report.outcome, expectedCode ? 'unconfirmed' : 'applied');
    return report;
  }
  const fileA = join(path, 'alice.token');
  const actionA = { operation: 'create', name: "fixture-alice ' SQL parameter 😀", credential_file: fileA };
  const inputPath = join(path, 'input.json');
  await writeFile(inputPath, JSON.stringify({ target, action: actionA }), { mode: 0o600 });
  const a = await apply(actionA, 0, inputPath);
  const b = await apply({ operation: 'create', name: 'fixture-bob', credential_file: join(path, 'bob.token') });
  assert.notEqual(a.identity_id, b.identity_id);
  assert.notEqual(a.credential_id, b.credential_id);
  tokens.push((await readFile(fileA, 'utf8')).replace(/\n$/, ''));
  assert.equal((await lstat(fileA)).mode & 0o777, 0o600);
  const verifier = createHash('sha256').update(tokens[0], 'ascii').digest('hex');
  const tokenB = (await readFile(join(path, 'bob.token'), 'utf8')).replace(/\n$/, '');
  tokens.push(tokenB);
  await worker.probe(tokens[0], 404);
  await worker.probe(tokenB, 404);
  assert.equal(await db.prepare('SELECT verifier_sha256 FROM credentials WHERE id = ?').bind(a.credential_id).first('verifier_sha256'), verifier);
  const rotatedFile = join(path, 'rotated.token');
  const rotated = await apply({ operation: 'rotate', identity_id: a.identity_id, credential_file: rotatedFile });
  tokens.push((await readFile(rotatedFile, 'utf8')).replace(/\n$/, ''));
  assert.equal(rotated.identity_id, a.identity_id);
  assert.notEqual(tokens[0], tokens[2]);
  await worker.probe(tokens[2], 404);
  assert.equal(await db.prepare('SELECT count(*) AS n FROM credentials WHERE identity_id = ? AND revoked_at IS NULL').bind(a.identity_id).first('n'), 2);
  await apply({ operation: 'revoke', credential_id: a.credential_id });
  await worker.probe(tokens[0], 401);
  await worker.probe(tokens[2], 404);
  await worker.probe(tokenB, 404);
  const revokedAt = await db.prepare('SELECT revoked_at FROM credentials WHERE id = ?').bind(a.credential_id).first('revoked_at');
  await apply({ operation: 'revoke', credential_id: a.credential_id });
  assert.equal(await db.prepare('SELECT revoked_at FROM credentials WHERE id = ?').bind(a.credential_id).first('revoked_at'), revokedAt);
  assert.equal(await db.prepare('SELECT revoked_at FROM credentials WHERE id = ?').bind(b.credential_id).first('revoked_at'), null);
  await apply({ operation: 'disable', identity_id: a.identity_id });
  await worker.probe(tokens[2], 401);
  await worker.probe(tokenB, 404);
  const disabledAt = await db.prepare('SELECT disabled_at FROM identities WHERE id = ?').bind(a.identity_id).first('disabled_at');
  await apply({ operation: 'disable', identity_id: a.identity_id });
  assert.equal(await db.prepare('SELECT disabled_at FROM identities WHERE id = ?').bind(a.identity_id).first('disabled_at'), disabledAt);
  await apply({ operation: 'rotate', identity_id: a.identity_id, credential_file: join(path, 'disabled.token') }, 1);
  await apply({ operation: 'create', name: actionA.name, credential_file: join(path, 'duplicate.token') }, 1);
  // Falha de emissão não cria identidade órfã; credenciais e histórico permanecem.
  assert.equal(await db.prepare('SELECT count(*) AS n FROM identities').first('n'), 2);
  assert.equal(await db.prepare('SELECT count(*) AS n FROM credentials').first('n'), 3);
  const original = await readFile(fileA, 'utf8');
  await apply({ operation: 'rotate', identity_id: b.identity_id, credential_file: fileA }, 1);
  assert.equal(await readFile(fileA, 'utf8'), original);
  assert.equal(await db.prepare('SELECT count(*) AS n FROM credentials').first('n'), 3);
  await apply({ operation: 'revoke', credential_id: crypto.randomUUID() }, 1);
  for (const filename of ['disabled.token', 'duplicate.token']) tokens.push((await readFile(join(path, filename), 'utf8')).replace(/\n$/, ''));
  for (const output of [...outputs, worker.logs()]) {
    for (const token of tokens) assert.ok(!output.includes(token) && !output.includes(token.split('.')[3]));
    assert.ok(!output.includes(verifier));
    assert.doesNotMatch(output, /INSERT|UPDATE|SQLITE|stack|Authorization/);
  }
});

test('private I/O rejects unsafe files, directories, links, overwrites, malformed operations and secret arguments', async (t) => {
  const path = await workspace(t);
  const file = join(path, 'private');
  await writeNewPrivateFile(file, 'private input\n');
  assert.equal(await readPrivateFile(file), 'private input\n');
  await chmod(file, 0o400);
  assert.equal(await readPrivateFile(file), 'private input\n');
  await assert.rejects(writeNewPrivateFile(file, 'overwrite'));
  await assert.rejects(readPrivateFile(file, 2));
  await chmod(file, 0o644);
  await assert.rejects(readPrivateFile(file));
  await chmod(file, 0o600);
  await symlink(file, join(path, 'link'));
  await assert.rejects(readPrivateFile(join(path, 'link')));
  await symlink(path, join(path, 'dirlink'));
  await assert.rejects(writeNewPrivateFile(join(path, 'dirlink/new'), 'secret'));
  await chmod(path, 0o755);
  await assert.rejects(readPrivateFile(file));
  await assert.rejects(writeNewPrivateFile(join(path, 'new'), 'secret'));
  await chmod(path, 0o700);
  for (const action of [
    { operation: 'create', name: '   ', credential_file: file },
    { operation: 'create', name: 'a\n', credential_file: file },
    { operation: 'create', name: 'a'.repeat(129), credential_file: file },
    { operation: 'rotate', identity_id: 'not-a-uuid', credential_file: file },
    { operation: 'disable', identity_id: crypto.randomUUID(), enabled: true },
    { operation: 'constructor' }, { operation: 'revoke', credential_id: '' },
  ]) assert.throws(() => validateOperation(action));
  const secret = 'secret-not-for-arguments';
  const result = await cli({}, ['--no-warnings'], secret);
  assert.equal(result.code, 1);
  assert.equal(result.stdout, '');
  assert.ok(!result.stderr.includes(secret));
});

test('remote adapter protocol only: bound batch and generic failure with token file preserved; no Cloudflare call', async (t) => {
  const path = await workspace(t);
  const apiCredential = 'synthetic-cloudflare-credential';
  const apiFile = join(path, 'api.token');
  await writeNewPrivateFile(apiFile, `${apiCredential}\n`);
  const preload = join(path, 'mock.mjs');
  await writeFile(preload, `
    globalThis.fetch = async (url, options) => {
      if (url !== 'https://api.cloudflare.com/client/v4/accounts/${'a'.repeat(32)}/d1/database/00000000-0000-4000-8000-000000000009/query') throw new Error('wrong endpoint');
      if (options.redirect !== 'error' || options.headers.Authorization !== 'Bearer ${apiCredential}') throw new Error('headers');
      const body = JSON.parse(options.body);
      if (!body.batch.every(s => s.sql.includes('?') && Array.isArray(s.params))) throw new Error('unbound SQL');
      return Response.json({ success: true, result: body.batch.map(() => ({ success: true, results: [{ id: 'synthetic' }] })) });
    };
  `);
  const target = { mode: 'remote', account_id: 'a'.repeat(32), database_id: '00000000-0000-4000-8000-000000000009', api_credential_file: apiFile };
  const result = await cli({ target, action: { operation: 'create', name: 'fixture', credential_file: join(path, 'remote.token') } }, ['--import', preload]);
  assert.equal(result.code, 0);
  assert.equal(result.stderr, '');
  const token = (await readFile(join(path, 'remote.token'), 'utf8')).replace(/\n$/, '');
  assert.ok(!result.stdout.includes(token) && !result.stdout.includes(apiCredential));
  await writeFile(preload, `globalThis.fetch = async () => { throw new Error('${apiCredential} Authorization SQL stack'); };`);
  const failure = await cli({ target, action: { operation: 'rotate', identity_id: crypto.randomUUID(), credential_file: join(path, 'uncertain.token') } }, ['--import', preload]);
  assert.equal(failure.code, 1);
  assert.equal(failure.stdout, '');
  assert.equal(JSON.parse(failure.stderr).credential_file_preserved, true);
  assert.ok(!failure.stderr.includes(apiCredential));
  assert.doesNotMatch(failure.stderr, /Authorization|SQL|stack/);
  assert.ok((await readFile(join(path, 'uncertain.token'), 'utf8')).startsWith('nt1.'));
});
