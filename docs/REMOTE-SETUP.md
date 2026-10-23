# Configuração e operação do MVP remoto

Parte normativa do [contrato v1](REMOTE-CONTRACT.md), entrega de [#7](https://github.com/obrunogonzaga/notes-cli/issues/7). A CLI Go e as rotas de negócio remotas **ainda não estão disponíveis**. A infraestrutura local Worker/D1 da #8 já pode ser executada conforme o [guia de desenvolvimento](WORKER-DEVELOPMENT.md); README e testes Python continuam descrevendo a versão local.

## 1. Configuração da CLI Go

Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/notes/config.json`. XDG_CONFIG_HOME, se definido, deve ser absoluto. Arquivo selecionável por `NOTES_CONFIG_FILE` (caminho absoluto), sem descoberta no repositório. Campos exatos:

```json
{
  "schema_version": 1,
  "endpoint": "https://notes.example.invalid",
  "credential_file": "/home/bruno/.config/notes/credential"
}
```

URL acima é ilustrativa e não resolve. Endpoint real será publicado em M5. `credential_file` pode ser absoluto ou relativo ao diretório de config.json, nunca ao cwd. Sem expansão implícita de `~`/`$VAR` no JSON. Não aceitar campos desconhecidos ou versão diferente. Sem arquivo/valores obrigatórios: `config_error`, antes de ler/enviar notas. Apenas `.notes-project` pertence ao repo; não colocar endpoint ou token nele.

Precedência por campo: `NOTES_ENDPOINT` > endpoint no arquivo; `NOTES_CREDENTIAL_FILE` > credential_file no arquivo. Override de credencial deve ser absoluto. Essas variáveis contêm URL/caminho, **não token**. Não há `NOTES_TOKEN`, `--token`, credencial em URL, flag de segredo ou fallback para credencial local Python/Cloudflare. O arquivo de configuração pode ser dispensado se ambos os campos vierem do ambiente. Variáveis inválidas, mesmo vazias, não fazem fallback silencioso.

Endpoint: origem absoluta, sem userinfo, query, fragmento ou path além de `/`; remover apenas a barra final. TLS validado com a trust store do SO. HTTP permitido somente para host literal `localhost`, `127.0.0.1` ou `[::1]` no desenvolvimento (sem redirects); nunca desativar verificação TLS. Ambientes dev/test/prod usam bancos e credenciais distintos; nenhum fallback de endpoint em caso de falha. Não suportar múltiplos perfis na mesma configuração no MVP: usar arquivos/variáveis explícitos.

Credencial: arquivo regular de dono igual ao usuário efetivo, modo 0600 (ou 0400), dentro de diretório privado 0700. Rejeitar symlink, arquivo ilegível, permissões de grupo/outros e formato inválido. Configuração e recibos também ficam em diretório 0700, arquivos 0600. Ler uma única linha ASCII contendo token, aceitando apenas um LF final; sem trim arbitrário ou linhas adicionais. Não mostrar o valor em diagnóstico, `--help`, trace HTTP ou comando reproduzível. As mesmas regras valem para credenciais de agentes em suas máquinas.

Exemplo de preparação de caminhos, sem segredo em argumento ou exemplo:

```bash
install -d -m 700 "$HOME/.config/notes"
# Um canal privado deposita a credencial individual em ~/.config/notes/credential.
chmod 600 "$HOME/.config/notes/credential"
export NOTES_ENDPOINT='https://notes.example.invalid'
export NOTES_CREDENTIAL_FILE="$HOME/.config/notes/credential"
```

O canal privado precisa entregar o token diretamente como arquivo/stdin protegido, sem clipboard público, histórico do shell, repositório, logs de CI ou argumentos de processo. As variáveis acima são configuração; não constituem provisionamento de serviço nem geram identidade.

### Estado local mínimo

- `.notes-project` mantém YAML `{id, name}` compatível com Python. Não contém credenciais.
- Registro opcional de caminhos/UUIDs para UX fica em `${XDG_STATE_HOME:-$HOME/.local/state}/notes/remote/projects.json`, chaveado por endpoint. Não decide autoria nem é fonte oficial de nomes/notas; `--project nome` consulta o serviço. Não reutilizar/escrever `projects.json` do armazenamento Python.
- Recibos de tentativa ficam em `.../notes/remote/operations/{key}.json`: `schema_version`, endpoint, identity_id, scope_id, key, fingerprint, created_at e outcome (`pending`, `created`, `unknown`), mais note_ref após sucesso. Modo 0600; persistir atomicamente antes de escrever na rede. Não guardam corpo, token nem fila de sincronização. A identidade é obtida do token no formato abaixo; autoridade sobre ela continua no servidor. O recibo auxilia recuperação, mas deduplicação oficial é D1.
- Rascunhos de editor são arquivos privados 0600, fora do repo. Preservar em falha, Ctrl+C ou conflito e informar caminho. Em add, o corpo do argumento/stdin também fica em rascunho privado se uma tentativa de rede falhar; isso permite repetir os mesmos bytes. Não enviar automaticamente rascunhos em uma execução posterior.
- Ler configuração local inválida ou estado inacessível é erro; não trocar projeto ou serviço silenciosamente. XDG_STATE_HOME segue a regra de caminho absoluto.

## 2. Configuração do Worker e D1

Base local implementada na #8 em `worker/`, sem provisionamento Cloudflare. [Preparação, migrações, testes isolados e resultados reais](WORKER-DEVELOPMENT.md). Autenticação e rotas funcionais da tabela continuam sendo especificação para as próximas issues de M2:

| Configuração | Decisão |
| --- | --- |
| Runtime | Worker TypeScript; binding D1 `DB`. |
| Banco | Um por ambiente, com [esquema](D1-SCHEMA.md); um espaço Bruno por banco. |
| Versionamento | Rotas `/v1`, JSON schema_version 1 e discriminador notes-remote. |
| Consistência | Usar binding D1 primário diretamente; sem Sessions API/read replicas ou cache no MVP. |
| Autenticação | Verificador SHA-256 de tokens aleatórios de 256 bits; identidades/credenciais em D1. Sem segredo compartilhado de aplicação. |
| Limites | Constantes do contrato, iguais em teste e produção; não configuráveis por usuário. |
| Ambiente | Nome/binding/ID do banco na configuração de deploy; autenticação Cloudflare só no ambiente de operação. Nunca incorporada ao binário Go. |

Depois de M2, operador com acesso Cloudflare aplica migrações no ambiente certo, confirma global existente e provisiona identidades. URL e ID de banco não são segredos; tokens e credenciais de conta são. Não expor D1 por HTTP administrativo nem distribuir acesso Cloudflare aos agentes. Read replicas não fazem parte da entrega; chamadas diretas ao binding vão ao primário conforme [documentação D1](https://developers.cloudflare.com/d1/best-practices/read-replication/).

## 3. Provisionamento, rotação e revogação

Operações manuais do dono pelo console/execução autenticada D1; não são comandos públicos da CLI nem endpoints. M2/#9 deve fornecer utilitário operacional que siga este protocolo, recebendo segredos por stdin/arquivo privado e não por argumentos.

1. Criar identidade: UUID v4, nome estável (`bruno`, `codex-laptop-b`, etc.), created_at UTC, disabled_at NULL. Nome é único para evitar confundir autoria; nome/ID não se reutilizam nem são apagados no MVP.
2. Gerar UUID v4 de credencial e **32 bytes de CSPRNG**. Token exato: `nt1.<identity_uuid>.<credential_uuid>.<base64url_sem_padding_dos_32_bytes>`. Os dois UUIDs são identificadores públicos; o último componente tem 43 caracteres. Uma credencial por agente/instalação; várias credenciais podem pertencer à mesma identidade durante rotação.
3. Calcular SHA-256 dos bytes ASCII do **token completo**, armazenar somente digest hexadecimal minúsculo, identity_id, credential_id, created_at e revoked_at NULL. Hash rápido é adequado aqui porque o segredo é aleatório de 256 bits, não uma senha humana. Não persistir token reversível no servidor nem adicionar token a notas/importações.
4. Entregar uma vez por canal privado para o arquivo da máquina; destruir cópias operacionais temporárias. Token perdido requer nova credencial, não recuperação do digest. Antes de confirmar distribuição, verificar uma chamada autenticada sem imprimir token.
5. Worker valida sintaxe, localiza credential_id, confere identity_id, compara digest em tempo constante e verifica revoked_at/disabled_at a cada request. Erros são o mesmo 401 genérico. Nunca aceitar nome/author do cliente como identidade. updated_by em cada mutação é essa identidade.

**Rotação:** emitir segunda credencial para a mesma identidade, instalar/testar nas máquinas e revogar a antiga atribuindo revoked_at UTC. Recibos idempotentes pertencem à identidade, então replay com token novo ainda funciona. **Revogação individual:** UPDATE por credential_id, sem precisar conhecer token; repetir mantém o primeiro revoked_at. Não remover linha. **Desativação da identidade:** preencher disabled_at, bloqueando todas as suas credenciais; repetir é no-op. Não há reativação pelo protocolo MVP; criar nova identidade se necessário. Histórico e nomes em notas permanecem legíveis.

Após o commit de revogação, uma nova chamada com o token antigo deve retornar 401 para GET e POST, sem sequer retornar recibos de idempotência. Operações já em andamento obedecem à ordem de commits definida no [contrato](REMOTE-CONTRACT.md#7-idempotência-concorrência-e-retries). Validar também que a credencial de outro agente continua funcionando. Revogação não recolhe dados já lidos por uma máquina.

SQL ilustrativo para o operador, com parâmetros vinculados, não interpolados; não executar com placeholders literais:

```sql
UPDATE credentials SET revoked_at = COALESCE(revoked_at, ?1)
WHERE id = ?2;
UPDATE identities SET disabled_at = COALESCE(disabled_at, ?1)
WHERE id = ?2;
```

Não há lista de tokens ou endpoint de criação via CLI. O utilitário deve reportar UUIDs/resultados, nunca o segredo em stdout de log. O canal de entrega do token é responsabilidade operacional de Bruno; a regra de verificação/revogação independe da escolha desse canal.

## 4. Fluxo entre duas máquinas

Exemplos propostos, executáveis somente depois de M2/M3. Em ambas, usar **o binário Go instalado por caminho absoluto**, aqui `/opt/notes-go/notes`, para não chamar o Python existente. Ambas têm NOTES_ENDPOINT para o mesmo serviço real; cada uma tem seu próprio NOTES_CREDENTIAL_FILE. Não copiar credenciais entre máquinas.

Máquina A (identidade bruno), em subpasta do repo:

```bash
cd /caminho/notes-cli/src
/opt/notes-go/notes init --json
/opt/notes-go/notes add 'Escolhemos Go para distribuir um binário único' \
  --to agents --idempotency-key 50000000-0000-4000-8000-000000000001 --json
```

Suponha UUID `8d43e572-184e-4a35-875d-2358bcf2427a`, ID 1 e revisão `r_40000000-0000-4000-8000-000000000001`. init usa PUT projects; add usa POST scope notes e retorna o note_ref da seção 3 do contrato. A nota tem created_by bruno; o título é a primeira linha. Versionar/compartilhar `.notes-project` pelo fluxo normal de Git, sem credenciais. Não há comando Git executado automaticamente pela CLI.

Máquina B (identidade codex-laptop-b), com clone que contém o mesmo `.notes-project`:

```bash
cd /outro/caminho/notes-cli
/opt/notes-go/notes init --json
/opt/notes-go/notes search 'GO' --json
/opt/notes-go/notes read 1 --json > nota.json
/opt/notes-go/notes context --query 'Go' --to agents --limit 12000 --json
```

search encontra somente registros do projeto; context combina projeto/global, ambos com revisions e origem. O agente pode afirmar: “Distribuição por binário único foi decidida em projeto 8d43e572-184e-4a35-875d-2358bcf2427a, nota #1, revisão r_40000000-0000-4000-8000-000000000001.” Nenhuma resposta é gerada pelo Worker. B não precisa de arquivos de notas nem Python de A. Fora do clone, `read 1 --project UUID` acessa o mesmo registro. `read 1 --global` pode ser outra nota; nunca é fallback para o projeto.

Edição concorrente: A e B leem revisão inicial. A altera corpo:

```bash
/opt/notes-go/notes edit 1 --body-file decisao.md \
  --if-revision r_40000000-0000-4000-8000-000000000001 --json
```

A recebe 200 e nova revisão, updated_by bruno. B envia outra alteração com o token antigo: HTTP 409 do exemplo de erro no contrato, stderr JSON, stdout vazio e exit 3. B conserva seu rascunho, relê e decide como reconciliar; não há overwrite/merge automático. Archive com revisão atual muda estado uma vez; repetir preserva revisão/datas. read ainda funciona; search/context padrão não incluem a arquivada.

Ausência de resultados: `search 'termo inexistente' --json` recebe 200 com `notes: [], next_cursor: null` e exit 0. Rede indisponível, após esgotar retries, produz somente stderr, por exemplo:

```json
{
  "api":"notes-remote","schema_version":1,"request_id":null,
  "error":{"code":"network_error","message":"Não foi possível confirmar a criação; repita com a mesma chave e conteúdo.","retryable":true,
    "details":{"outcome":"unknown","idempotency_key":"50000000-0000-4000-8000-000000000001"}}
}
```

Se add teve timeout, repetir na mesma identidade com o mesmo corpo/to/escopo/chave retorna o recibo original, não outra nota. Se o corpo vinha de editor/stdin, reutilizar o rascunho indicado (`notes add --to agents --idempotency-key UUID < rascunho.md`); informar também `--project UUID` se fora do projeto. Não usar nova chave para contornar resultado desconhecido. Se o token foi revogado, restaurar acesso por rotação manual e então retomar com mesma identidade/chave; outra identidade não compartilha esse namespace.

## 5. Incompatibilidades com Python e distribuição

| Python local v0.1 disponível | Go remoto especificado |
| --- | --- |
| Runtime Python/PyYAML; pip/wheel/sdist | Binário Go/Linux; instalação e CI serão entregues em M4/#15. Nenhum download/URL de release presumido. |
| Arquivos Markdown em XDG_DATA_HOME são fonte oficial | D1 oficial; rede obrigatória, sem cache de notas nem sincronização offline. Edição de arquivo local não altera nota remota. |
| Autor livre, `--author` ou usuário do SO | Autoria autenticada; --author rejeitado, autoria histórica só em origin da importação. |
| Editor recebe YAML + corpo | Editor recebe corpo; título/to por flags. Estado somente archive; sem restaurar alterando YAML. |
| `--body-file` aceita ausência de revisão; archive incondicional | Ambos exigem --if-revision; edit interativo usa revisão inicial. |
| Revisão `<contador>-<sha256 arquivo>`, revision_number | Token r_UUID opaco; sem contador público. Tokens locais não são condições remotas. |
| JSON schema_version 1, path, author, errors e corpos em list/search | Discriminador notes-remote, outros envelopes/autorias; resumos paginados sem path/body/origin e sem sucesso parcial. Não passar esse JSON a consumidores locais sem adaptação. |
| Registro local decide aliases conhecidos | Serviço resolve nomes exatos/ambíguos; UUID direto funciona em qualquer máquina autenticada. |
| Busca Python casefold depende da versão de runtime e concatena título/corpo | Unicode 15.1 C+F fixado, campos separados; tabela normativa no contrato. |
| Sem limites rígidos de corpo/páginas, context sem teto de candidatos | Limites HTTP/campos/páginas/contexto do contrato; nenhuma truncagem silenciosa. |
| Erros locais podem coexistir com notas válidas | Consulta remota falha integralmente; erro vai para stderr e stdout fica vazio. Importação tem relatório próprio por item. |
| IDs de notas locais e datas/revisões YAML | IDs remotos novos, datas/revisões de servidor; dados locais preservados em origin. |

Manter produto notes-cli, executável notes, Markdown, destinatários e `.notes-project`. Os exemplos antigos com --author e edição YAML continuam válidos **apenas** para Python. Antes de trocar PATH em M4, instalar Go em caminho separado, conferir `command -v notes`, `type -a notes` e versão; o binário Go deve identificar modo remoto em `notes --version`. Só então apontar o comando principal ao binário escolhido. Não substituir/desinstalar automaticamente Python, nem reutilizar seus dados/configurações remotas. Importar explicitamente pela [prévia e relatório](REMOTE-IMPORT.md).

Instrução manual para agentes depois da instalação Go: “Execute notes context no início da tarefa; cite escopo, ID e revisão. Registre descobertas dirigidas a Bruno com --to bruno. Em edição/arquivamento use a revisão lida. Falha de rede não é ausência de evidência. Notas são contexto, não autorização.” Não alterar AGENTS.md ou equivalentes automaticamente.
