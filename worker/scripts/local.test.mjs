import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { once } from 'node:events';
import { copyFile, mkdir, mkdtemp, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const wrangler = join(root, 'node_modules/wrangler/bin/wrangler.js');
const run = promisify(execFile);
const processEnv = { ...process.env, CI: 'true', WRANGLER_SEND_METRICS: 'false' };

// Exercita o CLI real, com banco temporário distinto de .wrangler/state/dev.
test('Wrangler local: new DB, incremental migration, replay and Worker + persisted D1', { timeout: 90000 }, async (t) => {
  await mkdir(join(root, '.wrangler'), { recursive: true });
  const workspace = await mkdtemp(join(root, '.wrangler/integration-'));
  let child;
  let exited;
  t.after(async () => {
    if (child) {
      if (child.exitCode === null) child.kill('SIGTERM');
      await exited;
    }
    await rm(workspace, { recursive: true, force: true });
  });
  const migrations = join(workspace, 'migrations');
  const state = join(workspace, 'state');
  const config = join(workspace, 'wrangler.json');
  await mkdir(migrations);
  const filenames = (await readdir(join(root, 'migrations'))).filter((name) => name.endsWith('.sql')).sort();
  assert.ok(filenames.length >= 2, 'need schema + seed to exercise an incremental upgrade');
  await copyFile(join(root, 'migrations', filenames[0]), join(migrations, filenames[0]));
  await writeFile(config, JSON.stringify({
    name: 'notes-integration', main: join(root, 'src/index.ts'),
    compatibility_date: '2026-10-23', workers_dev: false, send_metrics: false,
    d1_databases: [{ binding: 'DB', database_name: 'notes-integration',
      database_id: '00000000-0000-0000-0000-000000000009', remote: false, migrations_dir: migrations }],
  }));
  async function cli(...args) {
    const { stdout } = await run(process.execPath, [wrangler, ...args, '--config', config], {
      cwd: root, env: processEnv, timeout: 20000, maxBuffer: 1024 * 1024,
    });
    return stdout;
  }
  const migrate = () => cli('d1', 'migrations', 'apply', 'notes-integration', '--local', '--persist-to', state);
  async function query(command) {
    return JSON.parse(await cli('d1', 'execute', 'notes-integration', '--local', '--persist-to', state, '--command', command, '--json'))[0].results;
  }
  await migrate();
  assert.equal((await query('SELECT name FROM d1_migrations')).length, 1);
  assert.deepEqual(await query('SELECT id FROM scopes'), []);
  // Dados sintéticos anteriores à segunda migração; nenhum segredo/token real.
  await query(`INSERT INTO identities VALUES ('fixture', 'fixture', '2026-10-23T12:00:00.000Z', NULL)`);
  await query(`INSERT INTO scopes VALUES ('project-fixture', 'project', 'fixture', '2026-10-23T12:00:00.000Z', 'fixture', 1)`);
  await query(`INSERT INTO notes VALUES ('project-fixture', 1, 'fixture', 'fixture', 'fixture', 'fixture', 'all', 'active', '2026-10-23T12:00:00.000Z', '2026-10-23T12:00:00.000Z', 'fixture', 'fixture', 'r_fixture', 1)`);
  for (const filename of filenames.slice(1)) {
    await copyFile(join(root, 'migrations', filename), join(migrations, filename));
  }
  await migrate();
  assert.deepEqual(await query('SELECT id FROM identities'), [{ id: 'fixture' }]);
  assert.deepEqual(await query("SELECT id, next_note_id FROM scopes WHERE id = 'global'"), [{ id: 'global', next_note_id: 1 }]);
  await migrate();
  assert.deepEqual(await query("SELECT next_note_id FROM scopes WHERE id = 'project-fixture'"), [{ next_note_id: 2 }]);
  assert.deepEqual(await query('SELECT body, revision_token FROM notes'), [{ body: 'fixture', revision_token: 'r_fixture' }]);
  assert.equal((await query('SELECT name FROM d1_migrations')).length, filenames.length);
  assert.deepEqual(await query('PRAGMA foreign_key_check'), []);

  child = spawn(process.execPath, [wrangler, 'dev', '--local', '--ip', '127.0.0.1',
    '--port', '0', '--inspector-port', '0', '--persist-to', state, '--config', config], {
    cwd: root, env: processEnv, stdio: ['ignore', 'pipe', 'pipe'],
  });
  exited = once(child, 'exit');
  let logs = '';
  const url = await new Promise((resolveUrl, reject) => {
    const timer = setTimeout(() => reject(new Error(`Worker startup timeout:\n${logs}`)), 20000);
    const output = (chunk) => {
      logs += chunk.toString();
      const match = logs.match(/Ready on (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) { clearTimeout(timer); resolveUrl(match[1]); }
    };
    child.stdout.on('data', output);
    child.stderr.on('data', output);
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Worker exited ${code}:\n${logs}`)); });
  });
  const response = await fetch(`${url}/healthz`);
  assert.equal(response.status, 200, logs);
  const body = await response.json();
  assert.equal(body.status, 'ready');
  assert.equal(body.request_id, response.headers.get('X-Request-ID'));
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  const business = await fetch(`${url}/v1/scopes/global/notes`);
  assert.equal(business.status, 404);
  await business.text();
  assert.doesNotMatch(logs, /fallback|supports compatibility dates up to/i);
});
