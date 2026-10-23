# Desenvolvimento local do Worker e D1

Infraestrutura da [#8](https://github.com/obrunogonzaga/notes-cli/issues/8), sobre M1/PR #22, e autenticação individual da [#9](https://github.com/obrunogonzaga/notes-cli/issues/9), sobre main com PR #23 integrado. Verificadas em 23/10/2026. O projeto em `worker/` é independente do pacote Python: não executa `notes`, não lê arquivos Markdown locais e não usa XDG_DATA_HOME. Toda a superfície `/v1` está protegida; handlers de negócio continuam pendentes. [Operação de credenciais](REMOTE-SETUP.md#utilitário-operacional-da-9).

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

O resultado inclui `api: "notes-remote"`, `schema_version: 1`, um `request_id` e `status: "ready"`. `X-Request-ID` repete o ID; respostas usam JSON e `Cache-Control: no-store`. GET `/healthz` é uma sonda de infraestrutura sem autenticação, fora de `/v1`: lê somente a presença/forma do seed global, sem devolver dados de usuário ou metadados D1. Não audita a integridade de todas as tabelas ou credenciais. Banco sem migração/seed ou falha no binding retorna 503 genérico; outro método recebe 405/Allow: GET. Em `/v1` e qualquer caminho sob `/v1/`, todos os métodos exigem credencial antes de classificação da rota/entrada: ausente/inválida/revogada/desativada recebe o mesmo 401; credencial válida recebe 404 enquanto os handlers não existem. Outras rotas recebem 404. Falha de D1 durante autenticação retorna 503 genérico; ambos os 503 incluem Retry-After: 1. Não publicar esta base como serviço funcional de notas.

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

- `npm test`: 22 casos no runtime Workers via plugin oficial (13 da base e 9 de autenticação). O plugin fornece armazenamento separado por arquivo; `beforeEach` reconstrói o banco entre casos. Binding de teste tem ID `notes-integration-only`, sem persistência no banco dev. Não usar testes concorrentes sobre esse mesmo fixture.
- `npm run test:local`: quatro casos Node. O teste Wrangler original cria diretório único em `.wrangler/integration-*`, aplica só a migração inicial, grava identidade/projeto/nota sintéticos, adiciona as migrações restantes e verifica preservação dos dados e do contador. Reaplica tudo, verifica tracking/FKs e sobe o Worker em porta livre sobre o mesmo D1 persistido. O teste operacional cria outro D1 em `.wrangler/credentials-*`, executa o utilitário por arquivo/stdin e verifica rotação/revogação/desativação por HTTP com Worker real. Um caso testa permissões/I/O e outro somente o protocolo remoto simulado. Processos são encerrados e diretórios removidos ao terminar.

A CI ganhou job independente para `npm ci` e `npm run check` em Node 24; os jobs Python existentes foram preservados. Os tipos em `worker-configuration.d.ts` são gerados, não versionados; `npm run types` também pode ser usado para prepará-los no editor.

## Resultados e limites registrados

Em Linux, Node 26.8.2, npm 12.2.0, Wrangler 4.152.0/workerd 1.20261019.1:

- `npm ci` e `npm run check` passaram: TypeScript, 13 testes Workers e 1 teste Wrangler. Sem banco remoto, mocks de D1 ou credenciais reais.
- Migrações em banco novo, atualização em duas etapas com dados preexistentes, reexecução sem pendências, FKs ligadas/`foreign_key_check` vazio, dois triggers e quatro índices explícitos confirmados no D1 local.
- Sequências independentes por escopo, recusa de salto/reuso, ID máximo/sentinela, constraints de nota/credencial, unicidade de recibos/origens e FKs de autoria/referência verificadas. Falha após inserir nota reverte contador; falha de origem também reverte projeto criado no batch. Edição/arquivamento sintéticos não alteram os metadados de origem.
- Os scripts documentados `db:migrate` (duas vezes), `db:list` e `dev` foram executados. A segunda aplicação/listagem não encontrou migrações pendentes; GET `/healthz` respondeu HTTP 200 com `status: ready` e D1 local.
- `ruff check .` e os 42 testes Python passaram em Python 3.14.7, incluindo instalação wheel/sdist e piloto automatizado local. Para manter os temporários dentro desta worktree, a suíte foi executada na raiz com `GIT_CEILING_DIRECTORIES="$PWD/.pytest_cache/tmp" .venv/bin/python -m pytest -q --basetemp=.pytest_cache/tmp/run`. Sem esse teto, os temporários dentro da checkout descobrem o Git ancestral, causando 10 falhas de seleção de projeto; a configuração criada nessa primeira tentativa foi removida. Código, testes e armazenamento Python foram preservados.

São evidências de **D1 local**, não de serviço Cloudflare real, desempenho, cotas ou piloto entre máquinas. A validação de CI hospedada é acompanhada no PR desta entrega. A tentativa de `PRAGMA integrity_check` foi recusada pelo D1 local (`SQLITE_AUTH`); não faz parte das verificações aprovadas. Usamos as FKs e constraints acima, sem afirmar uma auditoria completa do banco.

Esses resultados da #8 antecedem autenticação. A #9 acrescenta os resultados abaixo; permanecem #10 (projetos/notas/revisão/idempotência), #11 (folding/busca/contexto), #12–#13 (Go) e #14 (importação). Migrações aplicadas permanecem inalteradas. Validações de campos das futuras rotas, Unicode/datas, fingerprints e imutabilidade de origem continuam nessas entregas, além das constraints já migradas.

## Resultados da #9 e limites de aceite

No mesmo ambiente Linux/Node 26.8.2/npm 12.2.0/Python 3.14.7 e dependências fixadas da #8:

- `npm ci` e `npm run check` aprovados: tipos gerados, TypeScript, **22 testes Workers e 4 testes Node**. Nenhum mock de D1; fixtures locais isoladas. Somente o adaptador HTTP remoto usa uma resposta simulada; não foi exercitado contra Cloudflare.
- `nt1` canônico com dois UUIDs v4 e 32 bytes de CSPRNG, base64url de 43 caracteres sem padding, SHA-256 do token completo (conferido também com node:crypto) e comparação por `crypto.subtle.timingSafeEqual`, a [primitiva nativa documentada](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/#timingsafeequal). A comparação recebe sempre dois digests de 32 bytes; ID inexistente/verificador malformado usa digest substituto. Isso verifica uso da primitiva e rejeições, não mede canais laterais de toda a requisição.
- HTTP real no runtime Workers cobre `/v1`, projetos, notas, busca/contexto, importação e rota desconhecida, inclusive métodos GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD, antes de negociar método/tipo ou consultar recursos. Ausente, malformada, falsificada, desconhecida, revogada e identidade desativada têm 401 uniforme e WWW-Authenticate: Bearer. D1 indisponível recebe 503 genérico sem SQL/stack/segredos; healthz continua público e independente das credenciais.
- Utilitário executado contra D1 persistido, com entrada em arquivo 0600 e stdin: duas identidades sintéticas, rotação com duas credenciais simultâneas, revogação repetida preservando a primeira data, desativação de identidade, nome duplicado, ID ausente, recusa de sobrescrita e de rotação de identidade desativada. Chamadas GET/POST ao Worker aceitam tokens emitidos (404 autenticado), passam a 401 após cada bloqueio e mantêm acesso da outra identidade. Logs capturados de Worker/utilitário não contêm tokens, componentes secretos ou verificador testados.
- I/O privado testa 0400/0600, diretório privado, permissões inseguras, symlinks de arquivo/diretório, tamanho e exclusividade da saída. Emissão interrompida/falha preserva arquivo para reconciliação, com stdout vazio e diagnóstico genérico. API Cloudflare usa batch parametrizado, origem HTTPS fixa e segredo de conta somente por arquivo privado; teste de protocolo/erro simulado não comprova atomicidade/permissões remotas.
- Auth retorna contexto imutável sem token/hash e deriva autores distintos mesmo se corpo/header sugerir outra identidade. Fixtures SQL usam o helper de autoria para created_by/updated_by e guarda ativa no INSERT/UPDATE; criador é preservado ao outro agente editar. Ambas as identidades leem notas dirigidas a bruno/agents/all, sem ACL por destinatário. Autenticar, revogar e então tentar o commit não grava nem consome contador; desativação também bloqueia. Credencial rotacionada da mesma identidade consegue consultar recibo sintético; a revogada não. Esses são testes determinísticos da ordem de commits, sem CRUD/replay HTTP implementado.
- `ruff check .` e **42 testes Python** aprovados, incluindo wheel/sdist e piloto automatizado local, sem mudanças em código/testes Python. A primeira invocação desta #9 falhou na preparação porque o diretório pai de basetemp ainda não existia; criado o diretório abaixo, a suíte passou. Na raiz da worktree, a reprodução isolada exige:

```bash
mkdir -p .pytest_cache/tmp
.venv/bin/ruff check .
GIT_CEILING_DIRECTORIES="$PWD/.pytest_cache/tmp" .venv/bin/python -m pytest -q --basetemp=.pytest_cache/tmp/run
```

Build Python separado aprovado com `.venv/bin/python -m build --outdir .pytest_cache/distribution` (wheel e sdist). Revisão documental: 14 blocos JSON decodificados, 101 links/âncoras locais verificados e `git diff --check` sem erros. Sintaxe dos três módulos operacionais e `--help` também verificados com Node.

**Pendente para revisão/integração:** #10 deve passar o contexto aos handlers, rejeitar author/created_by/updated_by na entrada, preservar criador/no-op e aplicar as guardas em cada escrita e classificação de replay/conflito, conforme [instruções D1](D1-SCHEMA.md#integração-obrigatória-dos-handlers-da-10). A ausência de ACL por destinatário deverá ser revalidada nas rotas reais. Corridas HTTP completas, revisões, idempotência e leitura de dados não são aceitas apenas pelos fixtures desta issue. Busca/contexto/importação/CLI Go não foram antecipados. Operação em D1 remoto existente, CI hospedada e piloto continuam sem evidência nesta worktree; nenhum recurso Cloudflare, credencial real, deploy ou merge foi executado.

O backend local do utilitário usa [getPlatformProxy](https://developers.cloudflare.com/workers/wrangler/api/) com remoteBindings: false, configuração explícita e persistência em `persist_to/v3`, conforme o mapeamento documentado para `wrangler --persist-to`.

## Documentação oficial consultada

Consultada em 23/10/2026; versões dos pacotes confirmadas no registry e suas declarações de tipos locais:

- [Wrangler: configuração](https://developers.cloudflare.com/workers/wrangler/configuration/) e [D1 local](https://developers.cloudflare.com/d1/best-practices/local-development/).
- [Migrações D1](https://developers.cloudflare.com/d1/reference/migrations/), [foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/) e [D1Database/batch](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch).
- [Plugin Vitest atual](https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/), [APIs de teste/migrações](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/) e [isolamento por arquivo](https://developers.cloudflare.com/workers/testing/vitest-integration/isolation-and-concurrency/). No pacote 1.4.7, `readD1Migrations` é exportado pela raiz `@cloudflare/vitest-plugin`; o tipo de `env` usa `Cloudflare.Env`.
- [Tipos gerados do Worker](https://developers.cloudflare.com/workers/languages/typescript/#generate-types), [TSConfig](https://www.typescriptlang.org/tsconfig/) e [configuração Vitest](https://vitest.dev/config/).
