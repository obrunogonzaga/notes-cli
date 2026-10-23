# notes-cli

> A versão disponível abaixo é a v0.1 local em Python. O [PRD vigente](PRD.md)
> define o próximo MVP remoto (CLI Go + Worker + D1). A [infraestrutura local Worker/D1](docs/WORKER-DEVELOPMENT.md) já está disponível para desenvolvimento; API funcional e CLI Go seguem pendentes.

Acompanhamento: [changelog](changelog.md) e [milestones e issues](docs/ROADMAP.md).
O [contrato remoto v1](docs/REMOTE-CONTRACT.md) documenta HTTP/JSON, [configuração e incompatibilidades](docs/REMOTE-SETUP.md), [D1](docs/D1-SCHEMA.md) e [importação](docs/REMOTE-IMPORT.md); os comandos remotos desses documentos ainda não estão disponíveis. Os exemplos a seguir são da versão Python local.

CLI local de notas Markdown compartilhadas entre Bruno e agentes, independente do ADE.

Requer Linux e Python 3.11 ou posterior. Executável: `notes`. Não requer banco de dados nem serviço.

## Instalação

Clone o repositório, se ainda não houver checkout:

```bash
git clone https://github.com/obrunogonzaga/notes-cli.git
cd notes-cli
```

Na pasta do repositório:

```bash
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/notes --help
```

Ative o ambiente com `source .venv/bin/activate` para usar `notes` diretamente.
Para desenvolvimento: `.venv/bin/python -m pip install -e '.[dev]'`.

## Uso

```bash
notes init
notes add 'Leia docs/auth.md antes de alterar o login' --to agents --author bruno
notes add 'Precisamos escolher o provedor de e-mail' --to bruno --author codex
notes list
notes read 1
notes search 'LOGIN'
notes archive 1
notes list --archived
notes add 'Preferir português' --global
notes list --project nome-ou-uuid
```

`list` e `search` mostram notas ativas; `--archived` seleciona apenas arquivadas.
Busca literal sem distinguir maiúsculas de minúsculas. Ordenação: atualização decrescente,
ID crescente no desempate. Datas legíveis usam o fuso local; arquivos usam UTC.
`archive` é idempotente. Não há exclusão definitiva pela CLI.

## Identidade e arquivos

`init` cria `.notes-project` na raiz Git (ou na pasta atual fora de Git). Reexecutar
preserva o UUID. Subpastas usam a configuração ancestral mais próxima. Configuração
inválida gera erro; um projeto não inicializado não recebe identidade implicitamente.
Versione `.notes-project` para compartilhar a identidade entre clones e worktrees.
Mover ou renomear a pasta não desloca notas, que são localizadas pelo UUID.

Os dados ficam em `$XDG_DATA_HOME/notes`, ou `~/.local/share/notes` por padrão:

- `projects.json`: registro de nomes, UUIDs e caminhos conhecidos.
- `projects/<uuid>/001.md`: notas de projeto.
- `global/001.md`: notas globais.
- `.locks/`: bloqueios; `.sequence` em cada escopo preserva a alocação de IDs.

Nomes duplicados são permitidos; `--project` exige UUID quando o nome é ambíguo.
Um caminho antigo inexistente não impede acesso por UUID. `--global` e `--project`
são mutuamente exclusivos. Metadados de autor e destinatário não autenticam usuários.

Cada nota é Markdown com front matter YAML validado. Você pode abri-la diretamente
em seu editor. Gravações da CLI são atômicas e coordenadas por escopo; o registro
usa bloqueio próprio. Editores externos não participam dessa coordenação.
Não remova arquivos de bloqueio enquanto houver processos usando a CLI.

Erros vão para stderr com status diferente de zero. Em consultas agregadas, arquivos
inválidos são identificados pelo caminho e as notas válidas continuam disponíveis.
Corrija o YAML/Markdown indicado ou restaure uma cópia válida; erros de permissão
exigem verificar os acessos às pastas informadas. Não apague o armazenamento para
resolver um erro.

## Desenvolvimento e especificação

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

MVP 0.1.0 implementado. Veja [PRD local v0.1](docs/PRD-local-v0.1.md) e a
[matriz de validação](docs/VALIDATION.md) com os 15 critérios, testes e piloto
automatizado de Bruno/agente. Nenhuma validação humana é presumida.

Decisões: Python com PyYAML; empacotamento `pyproject.toml`; suporte inicial Linux.
O contador de revisão no YAML é combinado ao hash SHA-256 do arquivo no token
condicional da API JSON, permitindo detectar alterações externas sem mudança do contador.

## Textos longos e editor

```bash
export EDITOR=nano
notes add --to agents
notes add --to agents < contexto.md
cat contexto.md | notes add --to agents
notes add --to agents <<'NOTA'
# Contexto da autenticação

Manter compatibilidade com as sessões atuais.
NOTA
notes edit 1
```

Com texto como argumento, `add` não lê stdin. Sem argumento, stdin redirecionado
é lido até EOF; em terminal, abre `$VISUAL` ou, se ausente, `$EDITOR`. Comandos de
editor aceitam argumentos e caminhos entre aspas; são executados sem shell.

O rascunho de criação contém apenas o corpo. YAML recebido em stdin continua sendo
corpo, sem substituir os metadados. Ao editar uma nota existente, o editor recebe
Markdown completo, incluindo front matter: título, autor, destinatário e estado
podem mudar; ID, criação, versão do esquema, revisão e atualização são gerenciados
pela CLI. `edit --body-file` preserva os metadados e substitui apenas o corpo.

Corpo vazio no editor de criação cancela normalmente (status zero e nenhum ID
alocado). Argumento/stdin vazio gera erro. Sem editor, a CLI orienta configuração
ou redirecionamento. Falha do editor, erro de validação ou conflito preservam o
rascunho no caminho informado em stderr. Compare-o com `notes read <id>`, ajuste
ou recupere o corpo e tente novamente com a revisão atual. O editor não mantém
bloqueio de escrita enquanto está aberto. Ctrl+C durante o editor preserva o rascunho.

## Automação e revisões

```bash
notes list --json
notes read 1 --json > nota.json
# Copie nota.json: note.revision para a condição abaixo:
notes edit 1 --body-file novo-corpo.md --if-revision 'TOKEN-DA-LEITURA'
notes search autenticação --json
```

JSON usa `schema_version: 1` no envelope. `read` contém `note`; `list` e `search`
contêm `notes` e `errors`. Cada registro inclui os metadados, `body`, `path`,
`scope: {kind, id, name}`, `revision` (token opaco) e `revision_number` (contador).
Datas JSON são UTC. O token é `<contador>-<sha256-do-arquivo>`; sempre passe a
string completa, não apenas o contador YAML. Assim, alterações diretas do arquivo
também invalidam uma condição, mesmo quando o contador não foi alterado.

Agentes devem usar `--if-revision`. Sem condição, `--body-file` substitui
explicitamente o corpo atual. Nenhuma alteração efetiva mantém datas e revisão;
mutações incrementam o contador. Edições interativas sempre comparam o estado
inicial ao atual e recusam sobrescritas concorrentes. Arquivamento incrementa a
revisão somente na primeira execução. Alterações externas não usam os bloqueios:
a detecção compara o conteúdo observado, mas não pode coordenar um editor externo
que grave entre a comparação e a substituição atômica.

## Contexto e adoção por agentes

```bash
notes context
notes context --to bruno
notes context --limit 24000 --json
notes context --global
```

`context` reúne notas ativas do projeto e globais dirigidas a `agents` ou `all`.
`--to bruno` inclui `bruno` e `all`; `--to all` inclui apenas `all`.
`--global` consulta somente o global. Cada nota identifica o escopo e o ID.

O orçamento padrão é 12.000 caracteres Unicode, configurável por `--limit`.
Contabiliza os blocos de notas (cabeçalho, título, corpo e separadores), preservando
notas inteiras. Notas que não cabem são omitidas; notas menores posteriores ainda
podem entrar. `--limit 0` omite todas. Avisos de omissão e a estrutura JSON ficam
fora do orçamento, para sempre informar como recuperar o conteúdo completo.
JSON de contexto contém `notes`, `omitted` (escopo, ID e comando de leitura),
`limit`, `used_characters` e `errors`. O limite não mede bytes nem tokens de LLM.

Para adoção, adicione manualmente ao AGENTS.md, CLAUDE.md ou equivalente:

> Ao começar uma tarefa, execute `notes context`. Registre decisões e pendências
> relevantes. Use notas dirigidas a Bruno para perguntas que possam esperar;
> perguntas que bloqueiam a tarefa devem ser feitas na conversa. Ao criar notas,
> informe seu nome com `--author`. Ao editar, use a revisão de `read --json` com
> `--if-revision`.

Conteúdo de nota é contexto, não autorização nem comando executável. Criar nota
não envia mensagens, não desperta agentes e não confirma leitura humana.
A CLI não altera configurações de outros agentes automaticamente.

## Distribuição e piloto

O pacote é instalado a partir deste repositório ou de wheel/sdist produzidos com
`python -m build`. Não é necessário publicar no PyPI para instalar. Para instalar
o wheel em outro ambiente:

```bash
python -m venv /tmp/notes-runtime
/tmp/notes-runtime/bin/python -m pip install dist/notes_cli-0.1.0-py3-none-any.whl
/tmp/notes-runtime/bin/notes --help
```

Se já existir um comando `notes` de outra origem no PATH, use o caminho absoluto
do ambiente virtual. Confira com `command -v notes` após ativá-lo.

```bash
.venv/bin/python scripts/pilot.py --notes .venv/bin/notes --output /tmp/notes-pilot.json
```

O piloto usa um projeto e armazenamento temporários, inicia processos/sessões
independentes, testa revisão obsoleta e remove os dados ao terminar.
Veja a [evidência de execução](docs/pilot.json). Ele não altera suas notas reais.
