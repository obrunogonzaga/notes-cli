# Desenvolvimento local do Worker e D1

Infraestrutura da [#8](https://github.com/obrunogonzaga/notes-cli/issues/8), verificada em 23/10/2026 sobre M1/PR #22. O projeto em `worker/` é independente do pacote Python: não executa `notes`, não lê arquivos Markdown locais e não usa XDG_DATA_HOME. Autenticação e operações do contrato `/v1` ainda não estão implementadas.

## Preparação e execução

Requer Linux, Node.js 24 ou posterior dentro do intervalo de `worker/package.json`, npm e acesso ao registry na instalação. `worker/.node-version` seleciona Node 24 para desenvolvimento/CI; a execução local registrada abaixo usou Node 26.8.2/npm 12.2.0. Dependências diretas estão fixadas, com transitivas em `package-lock.json`: Wrangler 4.152.0, TypeScript 7.0.2, Vitest 5.0.5 e `@cloudflare/vitest-plugin` 1.4.7.

A partir da raiz desta checkout:

```bash
cd worker
npm ci
npm run db:migrate
npm run db:list
npm run dev
```

Não exige login, conta, token Cloudflare ou `.dev.vars`. A configuração versionada é **somente local**, usa binding `DB`, banco `notes-local`, ID placeholder e `remote: false`. Os scripts de banco passam `--local` explicitamente. O servidor escuta somente em `127.0.0.1`, normalmente na porta 8787; `npm run dev -- --port 0 --inspector-port 0` escolhe portas livres e imprime a URL. A `compatibility_date` está fixada em `2026-10-23`.

Em outro terminal, com a porta impressa pelo Wrangler:

```bash
curl --fail --silent --show-error http://127.0.0.1:8787/healthz
```

O resultado inclui `api: "notes-remote"`, `schema_version: 1`, um `request_id` e `status: "ready"`. `X-Request-ID` repete o ID; respostas usam JSON e `Cache-Control: no-store`. GET `/healthz` é uma sonda de infraestrutura sem autenticação, fora de `/v1`: lê somente a presença/forma do seed global, sem devolver dados de usuário ou metadados D1. Não audita a integridade de todas as tabelas. Banco sem migração/seed ou falha no binding retorna 503 genérico; outro método recebe 405/Allow: GET. Outras rotas recebem 404, inclusive `/v1`; isso não é autenticação nem aceite funcional da API. Não publicar esta base como serviço de notas.

## Migrações e persistência

| Migração | Conteúdo |
| --- | --- |
| `0001_initial_schema.sql` | Seis tabelas de M1, FKs RESTRICT, quatro índices explícitos, dois triggers de sequência e constraints. |
| `0002_seed_global.sql` | Um escopo global sem identidade/credencial; timestamp fixo da data da migração, `2026-10-23T00:00:00.000Z`. |

`npm run db:migrate` prepara banco novo e aplica somente arquivos pendentes, registrados em `d1_migrations`. Repetir é um no-op; não executar o SQL bruto novamente para simular esse fluxo. Migrações aplicadas são imutáveis: mudanças futuras usam novo arquivo numerado. O seed não renomeia nem reseta escopos existentes. Uma falha deve ser investigada antes de prosseguir; não usar `INSERT OR IGNORE` para mascarar divergências.

Banco de desenvolvimento persiste em `worker/.wrangler/state/dev`, compartilhado somente pelos scripts `dev`, `db:migrate` e `db:list` desta checkout. Para uma inspeção local, dentro de `worker/`:

```bash
npx --no-install wrangler d1 execute notes-local --local \
  --persist-to .wrangler/state/dev \
  --command "SELECT id, kind, name, next_note_id FROM scopes"
```

Para recomeçar **descartando somente os dados locais de desenvolvimento**, pare o Worker, remova `worker/.wrangler/state/dev` e aplique as migrações de novo. Testes não precisam dessa remoção. Não apontar `--persist-to` para armazenamento Python ou diretórios de uso real.

Nenhum comando desta entrega cria recurso Cloudflare, usa `--remote` ou faz deploy. Não há configuração de produção ou script de deploy. Provisionamento de bancos reais, credenciais operacionais, URL e testes de cotas ficam para a operação/piloto. `workers_dev: false` e `preview_urls: false` não são um bloqueio de deploy: não executar deploy com esta configuração local. Segredos, estado, dependências e tipos gerados estão ignorados pelo Git; nenhum token de fixture é necessário.

## Verificações reproduzíveis e isolamento

Dentro de `worker/`:

```bash
npm run check
```

O comando gera tipos com `wrangler types`, verifica TypeScript do Worker/testes/configuração e executa:

- `npm test`: 13 casos no runtime Workers via plugin oficial. O plugin fornece armazenamento separado por arquivo; `beforeEach` reconstrói o banco entre casos. Binding de teste tem ID `notes-integration-only`, sem persistência no banco dev. Não usar testes concorrentes sobre esse mesmo fixture.
- `npm run test:local`: um teste com o CLI Wrangler real. Cria diretório único em `.wrangler/integration-*`, aplica só a migração inicial, grava identidade/projeto/nota sintéticos, adiciona as migrações restantes e verifica preservação dos dados e do contador. Reaplica tudo, verifica tracking/FKs e sobe o Worker em porta livre sobre o mesmo D1 persistido. Encerra o processo e remove esse diretório ao terminar.

A CI ganhou job independente para `npm ci` e `npm run check` em Node 24; os jobs Python existentes foram preservados. Os tipos em `worker-configuration.d.ts` são gerados, não versionados; `npm run types` também pode ser usado para prepará-los no editor.

## Resultados e limites registrados

Em Linux, Node 26.8.2, npm 12.2.0, Wrangler 4.152.0/workerd 1.20261019.1:

- `npm ci` e `npm run check` passaram: TypeScript, 13 testes Workers e 1 teste Wrangler. Sem banco remoto, mocks de D1 ou credenciais reais.
- Migrações em banco novo, atualização em duas etapas com dados preexistentes, reexecução sem pendências, FKs ligadas/`foreign_key_check` vazio, dois triggers e quatro índices explícitos confirmados no D1 local.
- Sequências independentes por escopo, recusa de salto/reuso, ID máximo/sentinela, constraints de nota/credencial, unicidade de recibos/origens e FKs de autoria/referência verificadas. Falha após inserir nota reverte contador; falha de origem também reverte projeto criado no batch. Edição/arquivamento sintéticos não alteram os metadados de origem.
- Os scripts documentados `db:migrate` (duas vezes), `db:list` e `dev` foram executados. A segunda aplicação/listagem não encontrou migrações pendentes; GET `/healthz` respondeu HTTP 200 com `status: ready` e D1 local.
- `ruff check .` e os 42 testes Python passaram em Python 3.14.7, incluindo instalação wheel/sdist e piloto automatizado local. Para manter os temporários dentro desta worktree, a suíte foi executada na raiz com `GIT_CEILING_DIRECTORIES="$PWD/.pytest_cache/tmp" .venv/bin/python -m pytest -q --basetemp=.pytest_cache/tmp/run`. Sem esse teto, os temporários dentro da checkout descobrem o Git ancestral, causando 10 falhas de seleção de projeto; a configuração criada nessa primeira tentativa foi removida. Código, testes e armazenamento Python foram preservados.

São evidências de **D1 local**, não de serviço Cloudflare real, desempenho, cotas ou piloto entre máquinas. A validação de CI hospedada é acompanhada no PR desta entrega. A tentativa de `PRAGMA integrity_check` foi recusada pelo D1 local (`SQLITE_AUTH`); não faz parte das verificações aprovadas. Usamos as FKs e constraints acima, sem afirmar uma auditoria completa do banco.

Permanecem concretamente: #9 implementa verificação/provisionamento/revogação de credenciais; #10 implementa rotas de projetos/notas, validação de entrada, revisão e idempotência sob concorrência; #11 implementa folding Unicode/busca/contexto; #12–#13 entregam Go; #14 implementa prévia/aplicação de importação. Os testes desta base verificam mecanismos SQL e atomicidade de batches, não retries HTTP, corridas de autenticação ou lógica de importação ainda inexistente. Validação de UUID, hashes hexadecimais, Unicode/datas e imutabilidade de origem pela aplicação continua nessas entregas, além das constraints de M1 já migradas.

## Documentação oficial consultada

Consultada em 23/10/2026; versões dos pacotes confirmadas no registry e suas declarações de tipos locais:

- [Wrangler: configuração](https://developers.cloudflare.com/workers/wrangler/configuration/) e [D1 local](https://developers.cloudflare.com/d1/best-practices/local-development/).
- [Migrações D1](https://developers.cloudflare.com/d1/reference/migrations/), [foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/) e [D1Database/batch](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch).
- [Plugin Vitest atual](https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/), [APIs de teste/migrações](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/) e [isolamento por arquivo](https://developers.cloudflare.com/workers/testing/vitest-integration/isolation-and-concurrency/). No pacote 1.4.7, `readD1Migrations` é exportado pela raiz `@cloudflare/vitest-plugin`; o tipo de `env` usa `Cloudflare.Env`.
- [Tipos gerados do Worker](https://developers.cloudflare.com/workers/languages/typescript/#generate-types), [TSConfig](https://www.typescriptlang.org/tsconfig/) e [configuração Vitest](https://vitest.dev/config/).
