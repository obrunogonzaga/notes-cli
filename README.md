# notes-cli

CLI local de notas Markdown compartilhadas entre Bruno e agentes, independente do ADE.

Requer Linux e Python 3.11 ou posterior. Executável: `notes`. Não requer banco de dados nem serviço.

## Instalação

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

Veja [PRD](PRD.md). A primeira entrega cobre identidade, persistência e comandos
básicos. Editor, stdin, JSON e contexto serão entregues na issue #2; validação
integrada e piloto estão na issue #3.

Decisões: Python com PyYAML; empacotamento `pyproject.toml`; suporte inicial Linux.
O contador de revisão no YAML será combinado ao hash SHA-256 do arquivo no token
condicional da API JSON, permitindo detectar alterações externas sem mudança do contador.
