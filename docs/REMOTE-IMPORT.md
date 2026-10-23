# Importação explícita do armazenamento Python

Parte normativa do [contrato remoto v1](REMOTE-CONTRACT.md), [#7](https://github.com/obrunogonzaga/notes-cli/issues/7). O importador será implementado em M4/#14; não há migração automática nesta entrega.

## 1. Origem e comandos

A origem é uma **instalação/conjunto de dados local**, identificada por `source_id` UUID v4 escolhido uma vez por Bruno, não pelo hostname, caminho, agente autenticado ou hash do conteúdo. `--source-id UUID` é obrigatório em toda importação. Guardar o UUID no plano/relatório fora dos arquivos originais; uma cópia do mesmo conjunto usa o mesmo UUID. Dois conjuntos independentes usam UUIDs distintos, mesmo que tenham os mesmos IDs/conteúdo. Se cópias divergirem, manter source_id evidencia conflito; trocar UUID para contornar conflito criaria outra origem e duplicatas intencionais.

Cada nota de origem é identificada permanentemente por `(source_id, scope_id, local_id)`, com scope_id global ou UUID original do projeto. Caminho/nome do arquivo não participa da identidade; mover ou renomear arquivo não cria uma nota nova. Arquivos diferentes com o mesmo par scope_id/local_id são colisão local, mesmo se idênticos: marcar ambos, não escolher arbitrariamente. Projeto mantém UUID; somente números de notas são remapeados. Sem deduplicação por similaridade de texto, nome de projeto ou autor.

Interface Go proposta:

```bash
# Apenas lê a origem, valida e consulta a prévia remota; não grava D1.
notes import --source-dir "$HOME/.local/share/notes" \
  --source-id 60000000-0000-4000-8000-000000000001 --dry-run --json > previa.json

# --apply autoriza enviar explicitamente os dados validados.
notes import --source-dir "$HOME/.local/share/notes" \
  --source-id 60000000-0000-4000-8000-000000000001 --apply --json > relatorio.json
```

Sem --apply o padrão é dry-run. Flags --apply/--dry-run são mutuamente exclusivas; import não combina --global/--project dos comandos de notas. Exigir exatamente uma fonte: --source-dir ou --manifest; sem descoberta/upload silencioso de dados. Importar todos os escopos válidos encontrados naquela raiz. Alternativa `--manifest arquivo.json` usa o formato da seção 2, mutuamente exclusiva com source-dir; source_id do manifesto deve coincidir com --source-id. Permite preparar uma amostra/nomes faltantes em um arquivo de transferência separado, sem editar o armazenamento original. Nenhuma flag ignora colisões ou sobrescreve destino.

A prévia mostra escopos, quantidade/bytes de corpos a enviar, notas arquivadas, erros de leitura/validação e ações previstas; identifica o endpoint e avisa que somente --apply envia Markdown/autoria/datas. --dry-run consulta o serviço apenas com UUIDs, nomes de projetos e fingerprints (formato abaixo), sem corpo/título de nota nem dados históricos. Também não altera a origem. `--apply` é consentimento explícito, não requer prompt interativo. A CLI executa prévia antes de aplicar e relata alterações observadas entre prévia e aplicação. Uma prévia separada não reserva estado: concorrência remota pode mudar o resultado final.

Ler `projects.json`, `projects/<uuid>/*.md` e `global/*.md` da v0.1. Ignorar arquivos auxiliares `.sequence`/`.locks`, sem apagá-los ou alterá-los. Não seguir symlinks nem buscar fora da raiz. Validar front matter schema_version 1 e campos da implementação Python, nomes/UUIDs e datas UTC (updated_at >= created_at), preservando o corpo após remover **somente** o envelope YAML e a única linha separadora definida no parser local. UTF-8 e CRLF originais devem ser preservados; não usar tradução universal de newlines na leitura. Corpo, título e demais campos ainda devem caber nos limites remotos; não aparar/truncar conteúdo importado para fazê-lo caber.

Origem é read-only: não criar marker, lock, renumerar, mover, arquivar, corrigir YAML ou atualizar projects.json nela. Calcular SHA-256 dos arquivos brutos antes de ler e imediatamente antes do envio; se mudou, marcar `source_changed`, não importar aquela versão nesta execução. Usuário deve suspender gravações Python durante a amostra para evitar alterações entre verificação/envio. A validação posterior compara hashes dos originais; a importação não passa a sincronizá-los.

Nome de projeto vem do registro local válido; caminhos registrados são ignorados. Diretório de projeto sem nome registrado: falha local `missing_project_metadata`; usuário pode fornecer manifesto explícito com nome validado. Nenhum arquivo absoluto de origem, caminho de máquina ou token local é enviado ao Worker. O relatório local pode identificar o arquivo com caminho relativo à raiz para diagnóstico.

## 2. Formato JSON de transferência

Arquivo de transferência --manifest, também produzido em memória ao ler source-dir (a CLI valida todo o conjunto antes de dividi-lo em prévias de até 10 notas; colisões são detectadas antes dos lotes):

```json
{
  "schema_version":1,
  "source_id":"60000000-0000-4000-8000-000000000001",
  "projects":[{"id":"8d43e572-184e-4a35-875d-2358bcf2427a","name":"notes-cli"}],
  "notes":[{
    "scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a",
    "local_id":12,
    "title":"Escolhemos Go",
    "body":"Escolhemos Go\nBinário único para Linux.\n",
    "author":"codex",
    "to":"agents","status":"active",
    "created_at":"2026-10-20T10:00:00.000000Z",
    "updated_at":"2026-10-21T11:00:00.000000Z",
    "revision_number":3,
    "raw_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }]
}
```

Digest acima é apenas ilustrativo. `POST /v1/imports/preview` recebe **somente** o resumo abaixo, nunca o manifesto com corpos:

```json
{
  "schema_version":1,
  "source_id":"60000000-0000-4000-8000-000000000001",
  "projects":[{"id":"8d43e572-184e-4a35-875d-2358bcf2427a","name":"notes-cli"}],
  "notes":[{
    "scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a","local_id":12,
    "raw_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "payload_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }]
}
```

Os hashes declarados na prévia permitem comparar mapeamentos existentes; não comprovam validade do conteúdo. Cada resumo deve ter exatamente scope_id, local_id e os dois hashes. Na aplicação por nota, `POST /v1/imports` recebe `schema_version`, `source_id`, `project` (objeto id/name ou null para global) e `note` (um dos objetos de notes acima). A aplicação calcula de novo o fingerprint no servidor a partir do conteúdo, sem confiar no digest da prévia. Não recebe api, if_revision, autoria remota ou Idempotency-Key. Campos desconhecidos são rejeitados. Lista vazia é prévia válida; aplicação exige exatamente uma nota. A prévia aceita até 10 resumos e 10 definições de projeto; aplicação aceita apenas o projeto da nota. Arquivo --manifest pode ser maior, desde que cada nota caiba sozinha no teto HTTP de 1 MiB. notes duplicadas por chave ou projects duplicados por UUID no manifesto: 422 `validation_error` antes de consultar/gravar qualquer item. Mais de 10 notas: 422; bytes excessivos: 413. Cada projeto usado exige sua definição; global não admite project.

`author`: texto histórico de uma linha de 1–128 caracteres, não autenticado; `revision_number`: inteiro positivo no intervalo seguro do contrato, vindo do contador YAML, não do token hash Python. Datas históricas: strings RFC 3339 UTC, com 0–6 casas decimais e sufixo Z ou +00:00, preservadas como recebidas. A aplicação source-dir usa a representação dos campos YAML locais, sem convertê-las para o horário de importação. `raw_sha256`: 64 hex minúsculos dos bytes completos do Markdown local (YAML + separador + corpo); servidor não consegue verificar o arquivo original, registra a declaração como origem não confiável. schema local é sempre 1; outras versões não são importadas.

Servidor calcula `payload_sha256`: SHA-256 do JSON canônico [JCS/RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) do array `[source_id, scope_id, local_id, project_name_ou_null, title, body, author, to, status, created_at, updated_at, revision_number]`. Não inclui raw_sha256. Preservação textual é exata; timestamps equivalentes com strings diferentes têm fingerprint diferente. Não aceitar digest de payload fornecido pelo cliente como autoridade. Valores default não são aceitos neste formato: todos os campos são obrigatórios.

Em nova nota, preservar título (sem derivar novamente), corpo, to, status e escopo originais. Criar novo ID, nova revisão e created_at/updated_at do servidor; created_by/updated_by são a identidade autenticada importadora. Estado arquivado já nasce arquivado. Dados históricos imutáveis ficam em `origin` da leitura completa:

```json
{
  "source_id":"60000000-0000-4000-8000-000000000001",
  "scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a",
  "scope_name":"notes-cli",
  "note_id":12,
  "schema_version":1,
  "author":"codex",
  "created_at":"2026-10-20T10:00:00.000000Z",
  "updated_at":"2026-10-21T11:00:00.000000Z",
  "revision_number":3,
  "raw_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "payload_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

`scope_name` é nome histórico enviado, global usa "global"; não renomeia projeto remoto existente. Hashes ilustrativos. Origin não concede autoria/permissão remota e não muda quando a nota remota é editada. Não há histórico de todos os corpos antigos no MVP.

## 3. Prévia, aplicação e relatório

Prévia é autenticada e compara com D1 **sem gravar projetos, notas, recibos ou mapeamentos**. Valida estrutura do resumo, projetos e hashes; conteúdo/histórico é validado localmente na prévia e novamente pelo servidor somente na aplicação. Para cada nota válida retorna ação `would_create`, `already_imported`, `source_diverged` ou `source_bytes_changed`, e `would_create_project` quando necessário. Não prevê ID numérico remoto para nota nova, pois não reserva sequência. Projeto existente com mesmo UUID e nome diferente não é outra identidade: usar nome remoto e emitir warning `project_name_differs`; guardar o nome histórico em origin. Projetos com mesmo nome e UUID diferente continuam separados.

Aplicação por item é atômica, incluindo registro de projeto ausente, alocação de ID, nota e origem. Não existe transação de todo o diretório. Uma falha em um item não desfaz sucessos anteriores. Servidor revalida tudo na aplicação; não confia em “aprovado na prévia”. Política:

| Situação | Resultado | Efeito |
| --- | --- | --- |
| Chave de origem ainda não existe | `imported` | Novo ID remoto sequencial, mesmo se ID local estiver livre. |
| ID local já usado remotamente por nota sem essa origem | `imported`, `id_remapped: true` se números diferem | Preservar nota existente, alocar próximo ID; não há sobrescrita. |
| Mesma chave de origem, payload_sha256 e raw_sha256 iguais | `already_imported` | Retornar mapeamento atual, sem mudar nota, revisão/datas ou autoria. Vale também se a nota remota foi editada/arquivada depois. |
| Mesma chave, payload_sha256 diferente | `source_diverged` | Rejeitar, preservar ambos os lados; não aplicar atualização local automaticamente. |
| Mesma chave, payload igual, raw_sha256 diferente | `source_bytes_changed` | Rejeitar mudança do arquivo/envelope de origem; não ocultar divergência de bytes como repetição exata. |
| Outra origem com mesmo texto/ID | `imported` | Criar nota distinta; sem deduplicar conteúdos independentes. |
| Payload inválido ou campo acima de limite | HTTP 422 | Nada gravado para o item. CLI converte em item rejeitado e continua os demais. |

Não existe flag force/overwrite/adopt para vincular origem a nota remota já existente. Reconciliação manual usa read/edit com revisão, preservando a origem anterior. Reimportar não desfaz edições remotas nem reabre arquivadas. Colisão entre duas aplicações simultâneas da mesma origem tem um único vencedor; perdedora relê o mapeamento e responde already_imported ou divergência. UNIQUE interno não deve vazar como 500.

Resposta de aplicação é 200 para os quatro resultados de domínio (imported, already_imported, source_diverged, source_bytes_changed). Divergência por item é parte do relatório, com `code` do resultado, não HTTP 409 (409 fica para revisão/idempotência das rotas normais). Não retornar corpo/token/SQL no relatório. Exemplo de nova nota cujo local_id 12 foi mapeado para ID remoto 18:

```json
{
  "api":"notes-remote","schema_version":1,
  "request_id":"20000000-0000-4000-8000-000000000005",
  "mode":"apply",
  "source_id":"60000000-0000-4000-8000-000000000001",
  "results":[{
    "source_scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a","local_id":12,
    "outcome":"imported","id_remapped":true,"warnings":[],
    "remote_ref":{"scope_id":"8d43e572-184e-4a35-875d-2358bcf2427a","id":18,"revision":"r_40000000-0000-4000-8000-000000000018"}
  }],
  "counts":{"imported":1,"already_imported":0,"rejected":0}
}
```

Preview usa o mesmo envelope com `mode: "preview"`, outcomes acima e counts `would_create`, `already_imported`, `rejected`; inclui por item `would_create_project`, `id_remapped: null` para novas, `remote_ref: null` para novas e warnings. Aplicação usa `mode: "apply"`. Para origem já existente, remote_ref aponta para ID e revisão **atuais**, inclusive em divergência; para inválida/desconhecida, null. Divergência tem `error: {code,message}` por item; sucesso não tem error. Não expor fingerprints existentes no diagnóstico. Mapeamento original é permanente em D1.

CLI (source-dir ou manifest) agrega os resultados num único envelope de relatório com request_id null e `request_ids` dos requests, mode, source_id, results e counts. Inclui `source_path` relativo para arquivos locais; erros de leitura/collision/oversize aparecem como rejeições de item, sem esconder os demais. Processamento ordenado por scope_id e local_id crescentes; não altera IDs antigos. A aplicação com rejeições termina exit 5; dry-run com previsões de divergências/erros também termina exit 5, sem escrita. Nenhuma rejeição: exit 0. Relatórios não incluem corpos nem credenciais.

Rede/serviço esgotou retries ou autenticação falhou durante importação: interromper envios novos, salvar relatório parcial privado em XDG_STATE_HOME/notes/remote/imports/{uuid}.json e escrever erro de execução em stderr com caminho e exit 1/4. **Stdout permanece vazio nessa falha de execução**; a CLI deve bufferizar o relatório final até concluir. Marcar item em voo `outcome: "unknown"` e restantes `not_attempted`; counts inclui essas categorias no relatório parcial. Em falhas antes de qualquer envio, não há successes presumidos. Repetir --apply com mesmo source_id e arquivos/payload retoma por deduplicação, sem duplicar sucessos e sem precisar de uma sessão de importação no servidor.

Relatório é mapeamento, não backup dos corpos. Guardar originais e o source_id. Importação não remove dados Python nem troca o executável no PATH; instalação/coexistência em [setup](REMOTE-SETUP.md#5-incompatibilidades-com-python-e-distribuição).
