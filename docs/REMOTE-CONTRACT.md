# Contrato do MVP remoto — HTTP/JSON v1

Especificação normativa de 23/10/2026 para [#7](https://github.com/obrunogonzaga/notes-cli/issues/7), baseada no [PRD](../PRD.md). **Não implementada.** Fecha M1 e orienta M2–M4; não comprova o aceite funcional do MVP. A versão disponível continua sendo Python local.

Documentos integrantes: [configuração, operação e compatibilidade](REMOTE-SETUP.md), [persistência D1](D1-SCHEMA.md) e [importação](REMOTE-IMPORT.md). Em caso de dúvida, o PRD define escopo; estes documentos fixam as decisões de implementação dentro dele. Mudanças incompatíveis exigem revisão conjunta e nova versão do contrato.

## 1. Transporte e versão

- Endpoint configurado é a origem, sem `/v1`: `https://notes.example.invalid`. Todas as rotas abaixo começam com `/v1`. HTTPS obrigatório, exceto loopback de desenvolvimento conforme [configuração](REMOTE-SETUP.md#1-configuração-da-cli-go).
- Toda rota exige `Authorization: Bearer <token>`, inclusive descoberta de projetos e prévia de importação. Um espaço de Bruno por banco/ambiente; sem parâmetro de usuário ou tenant. Todas as identidades têm leitura/escrita em todo o espaço. Destinatário não é ACL.
- Requisições com corpo: `Content-Type: application/json` (charset=utf-8 opcional), UTF-8 sem BOM, objeto JSON com `schema_version: 1`. GET não recebe corpo. `Accept: application/json`; ausência equivale a JSON. Outro tipo explicitamente solicitado recebe 406. Respostas: `application/json; charset=utf-8` e `Cache-Control: no-store`.
- `api: "notes-remote"` e `schema_version: 1` estão em **todos** os envelopes, de sucesso ou erro. O discriminador evita confundir este JSON com o `schema_version: 1` do Python. Versão ausente/incompatível no corpo: 400 `unsupported_schema_version`. Uma rota `/v2` não implementada recebe 404, sem fallback silencioso.
- Clientes ignoram campos novos nas respostas; servidor rejeita campos de entrada e parâmetros de consulta desconhecidos (400). Duplicatas de chaves JSON/parâmetros, tipos errados, `null` onde não permitido e UTF-8/surrogates inválidos são rejeitados. Em corpos JSON não há coerção de strings em números/booleanos. Na query string, page_size e limit usam decimal canônico não negativo (sem sinal, fração ou zeros iniciais, exceto o próprio 0), dentro dos intervalos abaixo.
- Não há DELETE, restauração, API administrativa, autenticação interativa, upload de arquivos binários ou geração de texto por LLM. Métodos não suportados em rota existente: 405 com `Allow`; rota inexistente: 404.
- Sem redirects automáticos na CLI, para não encaminhar credenciais a outro destino. HTTP 3xx, resposta não JSON, corpo truncado ou versão inesperada são falhas de protocolo, nunca sucesso vazio.
- Cada resposta HTTP tem `request_id` opaco novo (UUID). Cabeçalho `X-Request-ID` repete esse valor. Logs podem registrar ID, rota, status e identidade; nunca token, cabeçalho Authorization, corpos, consultas ou hashes de credencial.

## 2. Tipos e limites

Todos os limites são inclusivos. Tamanhos de texto são medidos após decodificar JSON, antes de case folding. “Caracteres” significa valores escalares Unicode (code points), não bytes, unidades UTF-16, grafemas nem tokens de LLM. Emoji composto conta vários; Go deve contar runes, TypeScript deve iterar code points.

| Campo/recurso | Regra |
| --- | --- |
| UUID | Representação canônica minúscula com hífens; novos UUIDs são v4; UUIDs locais válidos são preservados. |
| ID de nota | Inteiro JSON de 1 a 9.007.199.254.740.991, único no escopo, nunca reutilizado. Na URL, decimal sem zeros iniciais. |
| Corpo Markdown | 1–65.536 bytes UTF-8, com pelo menos um caractere fora de Unicode White_Space 15.1; NUL proibido. Preservar bytes UTF-8 do texto decodificado, inclusive CRLF, espaços e newline final. |
| Título | 1–256 caracteres, sem CR/LF/NUL/controles C0/C1, não só White_Space. Na criação, primeira linha não vazia, aparada por White_Space 15.1 e cortada em 256 caracteres; corpo permanece intacto. Linha separada por LF, CRLF ou CR. |
| Nome de projeto/identidade | 1–128 caracteres, mesmas restrições de linha/controles do título. Nome inicial de projeto: nome da pasta; erro local se inválido. |
| `to` / `status` | `bruno`, `agents`, `all` / `active`, `archived`. Padrões de criação: `all`, `active`. |
| Consulta `q` | 1–256 caracteres e até 1.024 bytes; somente White_Space é inválido. Sem trim ou normalização implícitos. |
| Página de notas/projetos | `page_size` inteiro 1–100, padrão 50. Respostas de coleção são resumos, sem corpo. |
| Contexto `limit` | Inteiro 0–48.000 caracteres de blocos completos; padrão 12.000. |
| Candidatos de contexto | Até 100 correspondências após filtros; acima disso: 422 `context_too_broad`, sem resultado parcial. Usar consulta mais específica ou list/search paginados. |
| Corpo HTTP | Máximo 1.048.576 bytes serializados, em qualquer requisição/resposta; nenhum request comprimido (415). Limite aferido mesmo sem Content-Length. |
| Cursor | Opaco, até 2.048 bytes; vinculado à rota, escopo, filtros e page_size. Não contém corpo de nota. |
| Idempotency-Key | UUID v4 canônico; obrigatório somente em criação normal de nota. |
| Importação | Uma nota por aplicação, manifesto até 10 notas na prévia, respeitando o limite HTTP; detalhes no [formato](REMOTE-IMPORT.md). |

Corpo HTTP excessivo: 413 `request_too_large`. Campo excedido ou texto vazio: 422 `validation_error`, com campo e limite, sem ecoar conteúdo. Se a serialização exceder o teto de resposta, retornar 422 `response_too_large` em envelope pequeno; nunca cortar corpo de nota ou JSON. Para coleções, reduzir page_size; para contexto, reduzir limit/consulta. Não há truncamento silencioso.

Datas remotas são UTC RFC 3339 com milissegundos fixos (`2026-10-23T13:00:00.000Z`), geradas pelo Worker. `created_at` imutável; `updated_at >= created_at`. Uma mudança efetiva usa instante não anterior ao anterior (igualdade em um milissegundo é possível). Autoria é `{id, name}` da identidade autenticada, sem renomeação no MVP. `revision` é string opaca `r_` seguida de UUID v4; clientes apenas armazenam e comparam. Não existe `revision_number` público.

### Registro completo

```json
{
  "api": "notes-remote",
  "schema_version": 1,
  "request_id": "20000000-0000-4000-8000-000000000001",
  "note": {
    "scope": {"kind": "project", "id": "8d43e572-184e-4a35-875d-2358bcf2427a", "name": "notes-cli"},
    "id": 1,
    "title": "Escolhemos Go",
    "body": "Escolhemos Go\nBinário único para Linux.\n",
    "to": "agents",
    "status": "active",
    "created_at": "2026-10-23T13:00:00.000Z",
    "updated_at": "2026-10-23T13:00:00.000Z",
    "created_by": {"id": "30000000-0000-4000-8000-000000000001", "name": "bruno"},
    "updated_by": {"id": "30000000-0000-4000-8000-000000000001", "name": "bruno"},
    "revision": "r_40000000-0000-4000-8000-000000000001",
    "origin": null
  }
}
```

`scope` global é sempre `{"kind":"global","id":"global","name":"global"}`. A identidade de uma nota é o par `(scope.id, id)`. O resumo contém todos os campos acima **exceto `body` e `origin`**. `origin` é `null` para criação normal ou objeto histórico imutável definido na [importação](REMOTE-IMPORT.md#2-formato-json-de-transferência). Não há `path` remoto.

## 3. Rotas e comandos

`{scope}` na tabela significa literalmente `global` ou UUID de projeto, sem o prefixo `project:`. Projeto não registrado: 404 `project_not_found`; o global já existe. `--global` e `--project` são mutuamente exclusivos. O mesmo número de nota em outro escopo não pode ser usado como fallback.

| Comando/uso | Método e rota | Entrada específica | Sucesso |
| --- | --- | --- | --- |
| `init` | `PUT /v1/projects/{uuid}` | `name` | 201 ao registrar; 200 ao reconhecer o mesmo UUID. |
| Resolver `--project nome` | `GET /v1/projects` | `name` opcional (igualdade exata), page_size, cursor | 200 `projects`, `next_cursor`. |
| Reconhecer UUID | `GET /v1/projects/{uuid}` | — | 200 `project`. |
| `add` | `POST /v1/scopes/{scope}/notes` | `body`, `to` opcional; Idempotency-Key | 201 `note_ref`; replay também 201. |
| `list` | `GET /v1/scopes/{scope}/notes` | status, page_size, cursor | 200 `notes`, `next_cursor`. |
| `read <id>` | `GET /v1/scopes/{scope}/notes/{id}` | — | 200 `note` completo, inclusive arquivado. |
| `edit <id>` | `PATCH /v1/scopes/{scope}/notes/{id}` | `if_revision`; um ou mais de body/title/to | 200 `note` completo. |
| `archive <id>` | `POST /v1/scopes/{scope}/notes/{id}/archive` | `if_revision` | 200 `note` completo. |
| `search <texto>` | `GET /v1/scopes/{scope}/search` | `q` obrigatório, status, page_size, cursor | 200 `notes` (resumos), `next_cursor`. |
| `context` | `GET /v1/context` | `scope` obrigatório, q/to/limit opcionais | 200 contexto completo, seção 5. |
| Prévia de importação | `POST /v1/imports/preview` | Resumo do manifesto (sem corpo/título/histórico) | 200 relatório sem mutação. |
| Aplicar importação | `POST /v1/imports` | Origem + uma nota | 200 relatório de item (inclusive conflitos). |

Todos os corpos de entrada também levam `schema_version: 1`. Não se envia `api` nem `request_id`. IDs, datas, estado, autoria e origem são rejeitados em add/PATCH; exceções são somente os campos históricos da importação. Add não aceita título explícito. O título inicial é derivado; editar somente o corpo **preserva o título**. PATCH não aceita remoção de campos ou JSON Patch.

### Projetos e resolução local

PUT recebe `{"schema_version":1,"name":"notes-cli"}`; resposta contém `project: {id,name,created_at,created_by}`. UUID já registrado devolve o registro existente, mesmo se o nome enviado diferir; não renomeia nem sobrescreve silenciosamente. A CLI avisa a diferença de nomes em stderr e usa o nome remoto nas referências. Não há comando de renomeação remota no MVP.

`GET /projects?name=notes-cli` compara nome exato, case-sensitive, sem normalização Unicode. Zero resultados: erro local de seleção; múltiplos: listar UUIDs e exigir UUID. A CLI percorre todas as páginas para decidir ambiguidade. `--project UUID` consulta diretamente o serviço, dispensando registro local. Ordenação dos projetos: UUID crescente. Nenhum caminho local é enviado.

`init` preserva o YAML `.notes-project` com apenas `id` e `name`, seleção ancestral mais próxima e raiz Git definidos no PRD. Cria o arquivo local atomicamente antes do PUT; falha remota não o remove. Repetir registra o mesmo UUID. Outros comandos não registram implicitamente um projeto ausente no servidor: orientam repetir `init`. Nenhuma nota pode ser criada em UUID desconhecido.

### Criação e coleções

```json
{"schema_version":1,"body":"Escolhemos Go\nBinário único para Linux.\n","to":"agents"}
```

Resposta 201 (inclusive replay):

```json
{
  "api":"notes-remote","schema_version":1,
  "request_id":"20000000-0000-4000-8000-000000000002",
  "note_ref":{
    "scope":{"kind":"project","id":"8d43e572-184e-4a35-875d-2358bcf2427a","name":"notes-cli"},
    "id":1,"revision":"r_40000000-0000-4000-8000-000000000001"
  }
}
```

`note_ref` é o recibo da criação; a revisão é a **inicial**, mesmo se a nota tiver sido editada depois do timeout. Ler novamente antes de editar. Header `Location: /v1/scopes/{scope}/notes/{id}`. Não retorna corpo completo nem histórico em replay.

`status=active` é o padrão de list/search; `status=archived` seleciona apenas arquivadas (`--archived`). Não há modo implícito “ambos”. As duas rotas retornam o mesmo envelope `notes: []`, `next_cursor: null` quando vazias. Nenhum campo `errors` com falhas parciais: falha de banco/validação invalida toda a resposta.

List/search ordenam por `updated_at DESC, id ASC`. Paginação por chave, sem offset: cursor carrega último par e vínculo aos filtros. Cursor inválido ou reaproveitado com outro filtro: 400 `invalid_cursor`. Não expira por tempo; não é snapshot entre requests: edições concorrentes podem mover registros entre páginas. Isso deve ser informado em uso de múltiplas páginas; para retomada determinística, repetir a consulta. O uso principal de `--json` retorna uma página/envelope da API, com `--page-size` e `--cursor` expostos na CLI; não agrega silenciosamente tudo. A contagem do contexto é uma leitura única coerente, não essa navegação paginada.

### Edição e arquivamento

```json
{"schema_version":1,"if_revision":"r_40000000-0000-4000-8000-000000000001","body":"Escolhemos Go\nDistribuição por binário Linux.\n"}
```

- `if_revision` é obrigatório nas duas mutações; ausente: 428 `revision_required`; tipo/formato inválido: 422. Não se usa If-Match nem o token contador/hash do Python.
- PATCH compara revisão **antes** de verificar ausência de mudança. Token antigo recebe 409 `revision_conflict`, mesmo se o payload coincidir com o estado atual. Corpo/título/to idênticos com token atual: 200, preservando revisão, datas e último editor.
- Mudança efetiva gera novo token, incrementa contador interno e altera updated_at/updated_by no mesmo commit. Duas alterações efetivas partindo da mesma revisão: somente uma vence. Nenhum merge automático. Notas arquivadas podem ter corpo/título/to corrigidos; permanecem arquivadas.
- Archive exige token válido presente. Se já arquivada, retorna estado atual sem mutação, **mesmo com token antigo**: exceção explícita para repetir o mesmo estado. Se ativa, revisão deve coincidir; caso contrário, conflito. Archive não altera corpo/título/to, nem oferece desarquivamento.
- Edit interativo trabalha num rascunho local de corpo Markdown, sem YAML gerenciável; título/to permanecem ou são alterados por `--title`/`--to`. Essas flags também podem acompanhar `--body-file`; sem elas preservam metadados. `--author` não existe na CLI remota. `--if-revision` pode restringir a leitura inicial interativa; a CLI não abre o editor com revisão já divergente.
- `edit --body-file` e archive exigem `--if-revision` explícito. Edit interativo usa a revisão de sua leitura inicial. Erro do editor, validação, rede ou conflito preserva o rascunho e informa caminho; nenhuma transação aberta durante o editor. Sem alteração não envia escrita desnecessária. Add preserva precedência argumento > stdin > VISUAL/EDITOR e cancelamento vazio do PRD.

## 4. Busca literal Unicode

Worker deriva `title_fold` e `body_fold` usando **Unicode 15.1 full default case folding**, mapeamentos C + F de [CaseFolding.txt](https://www.unicode.org/Public/15.1.0/ucd/CaseFolding.txt), excluindo T, independente de locale. A [definição de case folding do Unicode](https://unicode.org/faq/casemap_charprop.html) distingue esse algoritmo de simples lowercase. Caracteres sem mapeamento permanecem iguais. M2 deve fixar os dados da tabela, sem depender da versão Unicode implícita de Go, Python ou do runtime do Worker.

Correspondência: `fold(q)` é substring contígua de `title_fold` **ou** de `body_fold`. Não cruza a fronteira título/corpo. Sem tokenização, operadores, regex, stemming, remoção de acentos, NFC/NFKC ou expansão de sinônimos. `%`, `_`, aspas e `*` são literais; usar `instr` com parâmetros SQL, não LIKE/NOCASE/FTS. Corpo/título originais nunca são substituídos pelas versões derivadas.

| Consulta / texto | Resultado esperado |
| --- | --- |
| `GO` / `Escolhemos Go` | Encontra. |
| `AÇÃO` / `ação` | Encontra. |
| `acao` / `ação` | Não encontra. |
| `STRASSE` / `Straße` | Encontra (full folding). |
| `σ` / `ς` | Encontra. |
| `é` U+00E9 / `e` + U+0301 | Não encontra. |
| `I` / `ı` U+0131 | Não encontra (sem regra turca). |
| `100%` / `100 por cento` | Não encontra. |
| `distribuição` / `binário único` | Não encontra; sem recuperação semântica. |

GET percent-encode UTF-8 dos valores; `+` em query string representa espaço, então `+` literal usa `%2B`. `q` ausente em search é 400 `missing_query`; `q=` ou só espaços é 422. Em context omitir q significa sem filtro textual; não equivale a enviar q vazio.

## 5. Contexto e orçamento

`GET /v1/context?scope={uuid}&to=agents&limit=12000&q=Go` usa projeto + global; `scope=global` usa só global. `--project` explícito mantém projeto + global. `to=agents` padrão inclui agents/all; bruno inclui bruno/all; all inclui apenas all. List/search não filtram destinatário no MVP. Somente notas ativas entram no contexto.

Buscar e selecionar candidatos em uma leitura coerente no primário, ordenada por `updated_at DESC, id ASC, scope.id ASC` (desempate binário). Ler no máximo 101 para detectar excesso; 101 ou mais correspondências gera `context_too_broad`, em vez de esconder referências. Esse limite operacional é independente de `limit`, inclusive quando zero.

Para cada candidato construir **exatamente** o bloco abaixo, usando LF nos separadores, corpo original e valores remotos. Campos entre chaves são substituídos sem aspas extras; kind é project/global e author é created_by.id. O token e o título são os atuais. Nenhum escape Markdown é acrescentado ao bloco:

```text
[{kind}:{scope.id} #{id}] {title}\n
created_by={created_by.id}; updated_by={updated_by.id}; updated_at={updated_at}; revision={revision}\n
{body}\n\n
```

Na notação acima `\n` significa um único LF, não os dois caracteres barra+n; as quebras de linha de apresentação não acrescentam bytes. Os nomes de exibição e demais metadados continuam nos registros JSON. Cada bloco conta cabeçalho, metadados, título, corpo e os dois LFs finais, mesmo se o corpo já terminar em LF.

Percorrer todos os candidatos em ordem: incluir o bloco se `used_characters + caracteres(bloco) <= limit`; se não couber, omitir e continuar tentando notas menores. Não cortar notas. `limit=0` inclui zero, mas devolve todas as referências omitidas (até 100). Envelope, avisos e lista de omissões ficam fora do orçamento.

Resposta sempre tem `scopes` (objetos dos escopos consultados), `query` (string ou null), `to`, `limit`, `used_characters`, `notes` (registros completos), `blocks` (strings, paralelas a notes), `omitted` e `included_count`/`omitted_count`. `used_characters` é a soma dos blocos, igual à contagem Unicode de sua concatenação. Human-readable imprime os blocos, depois aviso com leituras das omitidas. O JSON não mede o próprio tamanho como orçamento.

Cada omitida: `{"scope":{"kind":"global","id":"global","name":"global"},"id":2,"revision":"r_40000000-0000-4000-8000-000000000002","reason":"budget","read_command":"notes read 2 --global --json"}`. Para projeto, read_command usa UUID: `notes read 1 --project 8d43e572-184e-4a35-875d-2358bcf2427a --json`. Nunca usar nome, caminho ou conteúdo da nota como shell command.

Exemplo completo sem correspondências (200):

```json
{
  "api":"notes-remote","schema_version":1,
  "request_id":"20000000-0000-4000-8000-000000000003",
  "scopes":[{"kind":"global","id":"global","name":"global"}],
  "query":"inexistente","to":"agents","limit":12000,"used_characters":0,
  "notes":[],"blocks":[],"omitted":[],"included_count":0,"omitted_count":0
}
```

Exemplo 200 com uma correspondência e nenhuma nota global candidata; o bloco usa 289 caracteres:

```json
{
  "api": "notes-remote",
  "schema_version": 1,
  "request_id": "20000000-0000-4000-8000-000000000006",
  "scopes": [
    {
      "kind": "project",
      "id": "8d43e572-184e-4a35-875d-2358bcf2427a",
      "name": "notes-cli"
    },
    {
      "kind": "global",
      "id": "global",
      "name": "global"
    }
  ],
  "query": "Go",
  "to": "agents",
  "limit": 12000,
  "used_characters": 289,
  "notes": [
    {
      "scope": {
        "kind": "project",
        "id": "8d43e572-184e-4a35-875d-2358bcf2427a",
        "name": "notes-cli"
      },
      "id": 1,
      "title": "Escolhemos Go",
      "body": "Escolhemos Go\nBinário único para Linux.\n",
      "to": "agents",
      "status": "active",
      "created_at": "2026-10-23T13:00:00.000Z",
      "updated_at": "2026-10-23T13:00:00.000Z",
      "created_by": {
        "id": "30000000-0000-4000-8000-000000000001",
        "name": "bruno"
      },
      "updated_by": {
        "id": "30000000-0000-4000-8000-000000000001",
        "name": "bruno"
      },
      "revision": "r_40000000-0000-4000-8000-000000000001",
      "origin": null
    }
  ],
  "blocks": [
    "[project:8d43e572-184e-4a35-875d-2358bcf2427a #1] Escolhemos Go\ncreated_by=30000000-0000-4000-8000-000000000001; updated_by=30000000-0000-4000-8000-000000000001; updated_at=2026-10-23T13:00:00.000Z; revision=r_40000000-0000-4000-8000-000000000001\nEscolhemos Go\nBinário único para Linux.\n\n\n"
  ],
  "omitted": [],
  "included_count": 1,
  "omitted_count": 0
}
```

O Worker só recupera dados. Consumidor cita `scope.id`, ID e revisão; falta de correspondência não confirma afirmações. Conteúdo de nota não autoriza ações nem dispara agentes.

## 6. Erros e saída da CLI

Envelope de erro é exclusivo (sem note/notes de sucesso):

```json
{
  "api":"notes-remote","schema_version":1,
  "request_id":"20000000-0000-4000-8000-000000000004",
  "error":{
    "code":"revision_conflict","message":"A nota mudou; leia novamente antes de editar.",
    "retryable":false,
    "details":{"scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a","id":1,"current_revision":"r_40000000-0000-4000-8000-000000000002"}
  }
}
```

Mensagens são humanas e não estáveis; automações usam code. details é sempre objeto, com apenas campos seguros de diagnóstico. Token de revisão não é segredo; nenhuma mensagem ecoa payload, consulta, credencial, verificador, SQL ou stack trace.

| HTTP | code | Condição / ação |
| --- | --- | --- |
| 400 | `invalid_request`, `missing_query`, `invalid_cursor`, `unsupported_schema_version` | Corrigir entrada/versão; sem retry automático. |
| 401 | `unauthorized` | Credencial ausente, malformada, inválida, identidade desativada ou credencial revogada: mesma mensagem genérica; `WWW-Authenticate: Bearer`. |
| 404 | `not_found`, `project_not_found`, `note_not_found` | Rota/recurso ausente; não é coleção vazia. |
| 405 / 406 / 415 | `method_not_allowed`, `not_acceptable`, `unsupported_media_type` | Corrigir método/negociação/tipo. |
| 409 | `revision_conflict`, `idempotency_conflict` | Releitura/reconciliação; não reenviar com nova revisão/chave automaticamente. |
| 413 | `request_too_large` | Reduzir corpo/lote. |
| 422 | `validation_error`, `context_too_broad`, `response_too_large`, `capacity_exceeded` | details pode conter field, max_bytes/max_characters/max_candidates; corrigir consulta/entrada. |
| 428 | `revision_required`, `idempotency_key_required` | Falta condição/chave obrigatória. |
| 429 | `rate_limited` | retryable true; `Retry-After` em segundos inteiros. |
| 500 | `internal_error` | retryable false; registrar request_id, verificar estado antes de repetir mutação. |
| 503 | `service_unavailable` | D1 indisponível/ocupado/cota da plataforma; retryable true e Retry-After (padrão 1 segundo). |

Outros erros de importação são resultados por item descritos em [importação](REMOTE-IMPORT.md#3-prévia-aplicação-e-relatório). Não há rate limiter de produto obrigatório em M1; 429 padroniza eventual limitação da infraestrutura. Erros de plataforma fora do Worker podem ser HTML ou 502/504: a CLI os trata como indisponibilidade, nunca como JSON de sucesso. Autenticar antes de consultar existência de recursos; pedidos sem credencial não revelam dados.

Na CLI, `--json` é aceito em todos os comandos remotos e devolve o envelope da operação, sem logs em stdout (import agrega relatórios conforme seu contrato). Uma página HTTP corresponde a uma página CLI. Falhas de execução escrevem um único envelope de erro em stderr e **zero bytes** em stdout; saída humana segue a mesma separação. Códigos de saída: 0 sucesso/cancelamento vazio no editor; 1 falha local, rede, protocolo ou serviço; 2 uso/configuração/validação; 3 conflito; 4 autenticação; 5 importação com um ou mais itens rejeitados ou falhas locais (relatório é resultado em stdout e diagnóstico em stderr). Importação interrompida por rede segue a seção própria.

Erro local com --json usa o mesmo discriminador/versão, `request_id: null`, `details` com causas seguras e code `config_error`, `validation_error`, `editor_error`, `network_error` ou `protocol_error`. `network_error` inclui `outcome: "unknown"` se uma mutação pode ter sido enviada; erro de rede não produz notes vazio. Exemplos de CLI e recuperação em [configuração](REMOTE-SETUP.md#4-fluxo-entre-duas-máquinas).

## 7. Idempotência, concorrência e retries

### Criação normal

- Cliente gera Idempotency-Key **antes** de enviar add e reutiliza a chave em todas as tentativas da mesma criação. Namespace: `(identity_id, key)` em todo o espaço, não por token, projeto ou máquina. Trocar a credencial da mesma identidade preserva deduplicação; outra identidade deve usar a própria operação/chave.
- Fingerprint SHA-256 da operação canônica: array JSON compacto UTF-8 `["POST", "/v1/scopes/{scope}/notes", 1, body, to]`, com to padrão materializado. Serialização determinística conforme [JCS/RFC 8785](https://www.rfc-editor.org/rfc/rfc8785); sem normalizar texto. Mudança de rota/escopo/body/to com a mesma chave: 409 `idempotency_conflict`.
- Alocação de ID, nota e registro `(identity,key,fingerprint,recibo)` são **um commit**. Mesmo hash/chave: retorna 201 e mesmo note_ref inicial, `Idempotency-Replayed: true`; primeira aplicação usa false. request_id é novo. Nenhum segundo ID/nota é alocado. Concorrência com mesma chave termina em replay ou conflito, não em 500 por UNIQUE.
- Recibos não expiram no MVP, não são apagados com revogação e não guardam corpo histórico. Não há janela após a qual seja seguro duplicar a criação. Indisponibilidade não autoriza descartar a chave. Chave não é credencial.
- CLI oferece `add --idempotency-key UUID`; sem flag gera UUID. Não há flag de token de autenticação. Antes da primeira tentativa persiste recibo local da operação (endpoint, identity_id, scope, chave e fingerprint) fora do repo, conforme setup; não guarda corpo nem fila offline. Se terminar com resultado desconhecido, informa chave e comando para repetir com **o mesmo corpo/destinatário/escopo/identidade**. Reenviar chave com conteúdo diferente é erro, nunca “novo add”.

### Demais operações

PUT de projeto é idempotente por UUID. GET não muda estado. PATCH é condicionado: resposta perdida seguida de retry pode receber conflito, pois o primeiro commit já venceu; ler a nota e comparar todos os campos pretendidos, sem atribuir indevidamente a autoria a si. Não chamar esse conflito de sucesso automático. Archive já arquivado é no-op. Importação deduplica permanentemente por origem, independente da chave HTTP, como definido no documento próprio.

Credencial é revalidada em **cada tentativa**, inclusive replay. Alterações devem incluir o estado de autenticação no mesmo commit que grava dados: operação concorrente com revogação é ordenada pelo commit (se a revogação vencer, não grava). Leituras já iniciadas antes da revogação podem terminar; novas requisições após o commit da revogação recebem 401. Sem cache de autenticação ou de notas.

IDs usam contador por escopo em D1, sem SELECT MAX + 1 fora de transação. Revisão e comparação/gravação são atômicas, sem mutex em memória no Worker. Estratégia concreta e invariantes: [D1](D1-SCHEMA.md#2-transações-e-consistência).

### Política do cliente Go

Timeout total de 15 s por tentativa (conexão/TLS até 5 s), no máximo **3 tentativas totais**. Retry automático para falha transitória de rede, 429/503 e 502/504 de infraestrutura; respeitar retryable=false em envelope válido. Backoff: 250 ms e 1.000 ms mais jitter uniforme de 0–250 ms; Retry-After válido substitui o backoff se maior. Se exceder 30 s, encerrar orientando tentar mais tarde (não esperar indefinidamente). Cancelamento por usuário, certificado TLS inválido, redirect, 4xx restantes e erro de protocolo não são retentados automaticamente.

É seguro repetir automaticamente apenas GET, PUT projeto, add com mesma chave e importação com mesma origem/payload. PATCH/archive com precondição também podem repetir exatamente o request, mas um 409 interrompe as tentativas para releitura; a CLI não avança revisão sozinha. Após esgotar tentativas, estado de escrita pode ser desconhecido: preservar rascunho/recibo e orientar reconciliação. Mesmo 500 exige releitura ou replay explícito; nunca criar nova chave para “resolver” timeout. Corpo, chave e if_revision ficam estáveis entre tentativas.

## 8. Cobertura dos 14 critérios do PRD

Esta matriz é revisão de **especificação**, não evidência de funcionalidade. Os testes Python e [validação histórica](VALIDATION.md) não aprovam o MVP remoto. M2/M3 devem transformar as regras em testes de integração; M5 registra o piloto real.

| # | Regra fechada / referência | Validação executável pendente |
| --- | --- | --- |
| 1 | Go/Linux sem runtime Python; [setup](REMOTE-SETUP.md#5-incompatibilidades-com-python-e-distribuição). | M3/M4: binário em Linux limpo, sem Python. |
| 2 | UUID, raiz Git, ancestral, PUT idempotente; seção 3. | M3: init em subpasta, repetição após falha e segundo clone. |
| 3 | Mesmo endpoint/UUID, credenciais distintas; [duas máquinas](REMOTE-SETUP.md#4-fluxo-entre-duas-máquinas). | M5: criar A, buscar/ler/contextualizar B. |
| 4 | Autoria e revogação; seções 1/7 e [runbook](REMOTE-SETUP.md#3-provisionamento-rotação-e-revogação). | M2: ausente/inválida/revogada, duas identidades e corrida com revogação. |
| 5 | Rotas, scopes e filtros; seção 3. | M2/M3: operações em global e dois UUIDs, IDs coincidentes e isolamento. |
| 6 | Preservação de texto/rascunho; seções 2/3 e setup. | M3: argumento/stdin/editor, CRLF/UTF-8, cancelamento, rede e conflito. |
| 7 | Literal Unicode, vazio e erro distintos; seções 4/6. | M2: tabela de busca, filtros, paginação, banco/rede indisponível. |
| 8 | Destinatários, blocos, orçamento e omissões; seção 5. | M2/M3: limite exato/zero, emoji, nota grande omitida, menor posterior, >100 candidatos e escopos. |
| 9 | Discriminador/versão, envelopes e stderr; seções 1/6. | M2/M3: JSON válido, unknown fields, sem logs/token em erros/stdout. |
| 10 | Sequência e deduplicação permanente; seção 7 e D1. | M2: adds simultâneos, mesma chave simultânea, resposta perdida, troca de token e chave divergente. |
| 11 | CAS e no-op; seção 3 e D1. | M2: duas edições da mesma revisão, no-op atual, no-op obsoleto e leitura posterior. |
| 12 | Arquivo conserva conteúdo, legível, no-op; seção 3. | M2/M3: busca/contexto/list padrão excluem, read inclui, archive repetido mantém revisão/datas. |
| 13 | [Manifesto, identidade e mapeamento](REMOTE-IMPORT.md). | M4: amostra Python, hashes antes/depois, repetição, origem divergente e IDs remapeados. |
| 14 | Recuperação textual sem LLM; seção 5 e duas máquinas. | M5: agente real recupera decisão Go e cita escopo/ID/revisão; evidência distinta de simulação. |

Decisões de contrato para M2/M3 estão fechadas. Permanecem trabalhos de implementação e operação: criar Worker/migrações, CLI Go, importador, distribuição e piloto; escolher a URL real e provisionar ambientes/credenciais em M2/M5. Não há credenciais, recursos Cloudflare ou evidência de piloto criados por esta especificação.

## 9. Revisão de especificação da issue #7

Verificação local em 23/10/2026, sem alterar código de produto ou criar recursos remotos:

- Issue #7 lida no GitHub e confrontada com PRD, roadmap, changelog e implementação Python local. Os 14 critérios estão mapeados acima, distinguindo especificação de aceite funcional futuro.
- 13 blocos JSON dos documentos de planejamento/contrato passaram por `json.loads`; 83 links/âncoras locais foram conferidos. O exemplo de contexto com resultado tem 289 valores escalares Unicode e segue exatamente o template de bloco.
- SQL deste esquema executado em SQLite em memória, com foreign_keys ligado: seis tabelas, dois triggers e nenhuma violação de FK. Verificados avanço de sequência, recusa de salto, rollback conjunto de nota/contador ao duplicar chave de idempotência e UPDATE condicional em que a segunda revisão obsoleta não afeta linha.
- `git diff --check` sem erros. O conteúdo do PRD histórico local foi preservado, com normalização apenas de espaços ao fim das linhas; os seis documentos de planejamento recebidos foram preservados como contexto, com alterações de contrato/links registradas no changelog.

Essas verificações não executam Worker, CLI Go, importador, migrações em D1 ou piloto. Testes e provisionamento reais continuam nas milestones M2–M5; a suíte Python existente é evidência histórica, não valida este contrato remoto.
