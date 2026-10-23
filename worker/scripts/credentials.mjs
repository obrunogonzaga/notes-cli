import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { prepareOperation, validateOperation } from './credential-operations.mjs';
import { readInput, readPrivateFile, writeNewPrivateFile } from './private-files.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const help = 'Uso: node scripts/credentials.mjs --input /caminho/privado/operacao.json (ou --input - via stdin). Veja docs/REMOTE-SETUP.md. Nenhum token em argumentos.';
let safeResult = {};
let dispose;
let tokenWritten = false;
try {
  if (process.argv.length === 3 && process.argv[2] === '--help') {
    process.stdout.write(`${help}\n`);
  } else {
    if (process.argv.length !== 4 || process.argv[2] !== '--input') throw new Error('usage');
    const input = JSON.parse(await readInput(process.argv[3]));
    if (!input || Object.keys(input).some((key) => !['target', 'action'].includes(key))) throw new Error('input');
    const { target, action } = input;
    validateOperation(action);
    let batch;
    if (target?.mode === 'local') {
      if (Object.keys(target).some((key) => !['mode', 'persist_to'].includes(key)) ||
          typeof target.persist_to !== 'string' || !isAbsolute(target.persist_to)) throw new Error('target');
      // Configuração fixa, bindings remotos desligados; nunca inferir conta/ambiente.
      const { getPlatformProxy } = await import('wrangler');
      const platform = await getPlatformProxy({ configPath: join(root, 'wrangler.jsonc'),
        envFiles: [], remoteBindings: false, persist: { path: join(target.persist_to, 'v3') } });
      dispose = platform.dispose;
      batch = (statements) => platform.env.DB.batch(statements.map(({ sql, params }) => platform.env.DB.prepare(sql).bind(...params)));
    } else if (target?.mode === 'remote') {
      if (Object.keys(target).some((key) => !['mode', 'account_id', 'database_id', 'api_credential_file'].includes(key)) ||
          !/^[a-f0-9]{32}$/.test(target.account_id ?? '') ||
          !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(target.database_id ?? '')) throw new Error('target');
      const apiToken = await readPrivateFile(target.api_credential_file, 4096);
      if (!/^[\x21-\x7e]+\n?$/.test(apiToken)) throw new Error('api_credential');
      batch = async (statements) => {
        const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${target.account_id}/d1/database/${target.database_id}/query`, {
          method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
          headers: { Authorization: `Bearer ${apiToken.replace(/\n$/, '')}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ batch: statements }),
        });
        if (!response.ok) throw new Error('remote_failure');
        const body = await response.json();
        if (body.success !== true || !Array.isArray(body.result) || body.result.length !== statements.length ||
            body.result.some((item) => item.success !== true)) throw new Error('remote_failure');
        return body.result;
      };
    } else throw new Error('target');

    const plan = await prepareOperation(action);
    safeResult = plan.result;
    // Persistir antes da transação: resposta perdida nunca perde o único token recuperável.
    if (plan.token) {
      await writeNewPrivateFile(action.credential_file, `${plan.token}\n`);
      tokenWritten = true;
    }
    const results = await batch(plan.statements);
    if (results.at(-1)?.results?.length !== 1) throw new Error('not_applied');
    process.stdout.write(`${JSON.stringify({ ...safeResult, outcome: 'applied' })}\n`);
  }
} catch {
  // Não imprimir exceção, entrada, token, verificador, SQL, resposta remota ou stack.
  process.stderr.write(`${JSON.stringify({ ...safeResult, outcome: 'unconfirmed', credential_file_preserved: tokenWritten,
    error: 'Operação não confirmada. Confira entrada/permissões e estado pelos UUIDs; preserve o arquivo emitido. Não repita emissão automaticamente.' })}\n`);
  process.exitCode = 1;
} finally {
  // Falha de encerramento do proxy não desfaz um commit já confirmado.
  try { await dispose?.(); } catch { /* resultado da operação já reportado */ }
}
