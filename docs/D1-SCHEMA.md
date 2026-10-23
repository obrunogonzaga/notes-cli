# Esquema D1 e invariantes do MVP

Parte normativa do [contrato v1](REMOTE-CONTRACT.md), [#7](https://github.com/obrunogonzaga/notes-cli/issues/7). SQL abaixo é **especificação**, não migração aplicada. M2/#8 criará os arquivos de migração e os testes contra D1. Não há API/servidor novo nesta entrega.

## 1. Esquema lógico inicial

Um banco por ambiente e espaço de Bruno. Sem tenant, tabela de embeddings, cache de notas, histórico de corpos ou exclusão. Identidades/credenciais são provisionadas manualmente. Datas TEXT em UTC, revisão pública token aleatório, contador interno independente. Worker valida UUID, UTF-8, datas, nomes, tamanho Unicode e fingerprints; constraints SQL complementam essa validação.

```sql
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

INSERT INTO scopes(id, kind, name, created_at, created_by)
VALUES ('global', 'global', 'global', '2026-10-23T00:00:00.000Z', NULL);
```

Instante do seed acima é ilustrativo; migração usa sua data real. Global não depende de identidade provisionada. `next_note_id = 9007199254740992` é sentinela de esgotamento, jamais exposta como ID. Se contador de IDs/revisões esgotar, devolver 422 `capacity_exceeded`, sem overflow/reutilização. Revisão número 1 em criação/importação. Tokens de revisão são r_UUID v4 novos por mudança efetiva; limite interno de revisão não é formato de cliente.

`scopes` representa projetos + global, expostos como tipos separados pela API. Nomes de projeto não são únicos. Não registrar caminhos de máquina. DTO de nota traduz to_recipient para to, busca identidades para created_by/updated_by e junta imported_notes para origin. Datas de origem preservam strings do Python; não são ordenadas como datas de servidor. Mapeamento, origem e recibos permanecem mesmo após edição, arquivamento ou revogação de credencial.

`title_fold`/`body_fold` são derivados Unicode 15.1, atualizados junto com título/corpo. Sem índice FTS; consulta parametrizada usa `(instr(title_fold, ?q) > 0 OR instr(body_fold, ?q) > 0)` e filtro de escopo/estado antes da ordenação/paginação. Índices ajudam filtros/ordem; a busca substring ainda pode varrer notas do escopo. Índices derivados podem ser reconstruídos; corpo D1 é fonte oficial. Nunca usar SQL lower/NOCASE como se fossem full Unicode folding.

## 2. Transações e consistência

Usar prepared statements e `DB.batch()` para commits de múltiplas instruções. O [binding D1](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch) documenta execução sequencial e rollback do batch em falha; as [foreign keys D1](https://developers.cloudflare.com/d1/sql-api/foreign-keys/) são aplicadas por padrão. Não tentar manter BEGIN aberto entre fetches ou em torno do editor. O contrato requer transação para **todas** as invariantes abaixo; não basta executar queries independentes após um SELECT no Worker.

Estratégia implementável para criação normal:

1. Autenticar, validar e calcular fingerprint/token de revisão antes do batch. Gerar token de revisão novo para essa tentativa.
2. No batch, `INSERT INTO notes ... SELECT` do scope usando seu next_note_id, guardado por existência de credencial/identidade ainda ativas, ausência do recibo `(identity,key)` e contador não esgotado. Trigger confere/incrementa sequência; se não inseriu, não consome ID.
3. No mesmo batch, inserir recibo a partir da nota com o **token novo e único desta tentativa**; guardar scope/id/revisão inicial/fingerprint. Selecionar recibo resultante e estado de auth/capacidade para classificar a resposta. Sem nota nova, não criar recibo órfão.
4. Recibo já existente: comparar fingerprint, retornar replay ou 409. Auth revogada tem precedência sobre replay. Conflito UNIQUE de corrida deve causar rollback, depois releitura autenticada e classificação de replay/conflito; nunca repetir mutação com outra chave.

Como instruções do batch formam uma transação, dois adds distintos veem contadores sucessivos; dois com mesma chave não criam duas notas/recibos. Não usar INSERT OR IGNORE na nota como forma de ocultar constraints. Evitar guardar resultado de SELECT de contador fora do commit. Se houver erro posterior à nota antes do recibo, rollback deve restaurar também o contador do trigger.

PATCH: UPDATE condicionado por `(scope_id,id,revision_token)` e credencial ativa, somente se campos mutáveis forem diferentes. Distinguir no mesmo batch estado ausente, no-op com revisão atual, revisão divergente e auth revogada; retornar snapshot selecionado no batch. Para mudança real, contador +1, token novo, timestamp e updated_by mudam juntos. Não comparar antes no Worker e gravar UPDATE incondicional depois. Archive segue a mesma regra, com exceção de estado já archived descrita no contrato. Se duas alterações divergentes e efetivas partem da mesma revisão, só um UPDATE afeta linha. No-op não muda nada, inclusive autor.

PUT projeto: INSERT condicionado por auth ativa e UUID ausente; selecionar existente ou criado no mesmo batch. Não modificar nome/created_by de projeto existente. Global não pode ser criado/renomeado pela rota de projetos.

Importação: batch registra projeto ausente se a nota validada for realmente nova, insere nota guardada por auth ativa e ausência da chave de origem, e insere imported_notes a partir do token novo exclusivo. Seleciona mapeamento/nota existentes para distinguir repetição/divergência. Se mapeamento já existe, não alterar projeto nem nota. Hash/mapeamento e nota devem ser um commit; falha em qualquer etapa reverte também sequência/projeto novo. Em replay, comparar hashes com a origem guardada, não com o corpo remoto atual. Não comparar local_id com next_note_id para escolher ID: importação sempre aloca novo ID.

Leituras usam binding direto ao primário, sem Sessions API/read replicas nem cache de auth/notas. Isso garante que uma consulta iniciada em B depois de A receber confirmação observe o commit de A. A opção é deliberada para o fluxo entre máquinas, conforme [comportamento de leitura D1](https://developers.cloudflare.com/d1/best-practices/read-replication/). Auth e seleção do contexto em um batch de leitura: até 101 candidatos no mesmo snapshot para contagem, seleção/omissões e revisão coerentes. Paginação list/search não mantém snapshot entre requests. Revogação bloqueia requisições iniciadas após seu commit; escritas usam guardas no commit e respeitam a ordenação de concorrência.

Não retornar campos `meta` de D1, SQL ou stack ao cliente. Traduzir conflito de constraints esperado para resultado de domínio e falha transitória/quota para 503. O limite de resposta HTTP da aplicação é distinto dos [limites de plataforma D1](https://developers.cloudflare.com/d1/platform/limits/); o contrato usa corpos pequenos e instr parametrizado para não depender de limite de padrão LIKE. Plano Cloudflare, CPU/cotas e custo reais devem ser aferidos em M2/piloto; exceder cota é erro explícito, sem fallback para dados locais.

## 3. Validação exigida em M2

- Executar migração em D1 local/ambiente isolado, conferir FKs, triggers, índices e seed global. SQL verificado em SQLite na especificação não substitui D1.
- Disparar adds simultâneos distintos e com mesma chave, resposta perdida, mesma chave em outro scope e credencial rotacionada. Verificar uma nota por recibo e sequência sem reutilização.
- Forçar falha entre nota/recibo e nota/origem: rollback integral, inclusive contador/projeto. Corrida com revogação não pode gravar depois de perder a condição de auth.
- Duas revisões concorrentes, no-op, archive repetido, token inválido, campos Unicode e consulta com %, _, aspas, acentos e emoji. Checar limites exatos e acima do limite.
- Importar origens iguais/divergentes em paralelo, preservar alteração remota posterior, remapear IDs e validar ausência de sobrescrita. Nenhum teste toca banco/dados reais de Bruno.
