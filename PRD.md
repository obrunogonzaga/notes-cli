# PRD — notes-cli

Status: MVP 0.1.0 implementado; validação em [docs/VALIDATION.md](docs/VALIDATION.md).
Data: 23 de outubro de 2026.  
Responsável pelo produto: Bruno Gonzaga.  
Nome do projeto: `notes-cli`. Comando: `notes`.

## 1. Problema

No Maestri ADE, Bruno e os agentes podem ler e escrever notas compartilhadas. Essa experiência ajuda a manter contexto e trocar recados, mas Bruno quer um mecanismo semelhante disponível pelo terminal e por diferentes ADEs.

Conversas isoladas dificultam recuperar decisões e pendências quando uma sessão termina ou quando Bruno troca de agente ou ambiente. É necessário um lugar persistente, simples de consultar e editar, que possa ser usado tanto por uma pessoa quanto por agentes com acesso ao terminal.

## 2. Objetivo

Criar uma pequena CLI local para registrar, consultar, buscar, editar e arquivar notas compartilhadas entre Bruno e agentes. As notas devem continuar disponíveis independentemente da sessão e do ADE utilizado.

O fluxo principal deve exigir poucos comandos e permitir acesso direto aos arquivos pelo editor preferido de Bruno.

## 3. Usuários e casos de uso

| Usuário | Necessidade | Exemplo |
| --- | --- | --- |
| Bruno | Deixar contexto para os agentes | “Antes de alterar o login, leia docs/auth.md.” |
| Bruno | Consultar descobertas e pendências | Ver recados deixados pelos agentes ao finalizar uma tarefa. |
| Agente | Recuperar contexto de outra sessão | Ler decisões e convenções relevantes ao projeto atual. |
| Agente | Registrar um retorno para Bruno | “Precisamos escolher o provedor de e-mail.” |
| Bruno e agentes | Preservar uma decisão | Registrar uma escolha e os motivos que a sustentam. |

As notas cobrem três usos principais: contexto permanente, recados para agentes e retornos para Bruno. Na primeira versão, esses usos não precisam de sistemas de workflow separados.

## 4. Escopo do MVP

- Inicializar e identificar um projeto.
- Criar, listar, ler, editar, buscar e arquivar notas.
- Usar escopo de projeto ou escopo global explicitamente.
- Registrar título, autor, destinatário, datas e estado.
- Produzir contexto compacto para agentes.
- Oferecer saída estruturada para automação.
- Armazenar cada nota em Markdown legível e editável.
- Evitar perda silenciosa de conteúdo em operações concorrentes feitas pela CLI.

### Fora do MVP

- TUI, interface web e aplicativo próprio.
- Integração visual ou sincronização automática com notas do Maestri.
- Servidor MCP, serviço em segundo plano e notificações.
- Sincronização entre máquinas e colaboração remota.
- Upload de anexos, busca semântica e embeddings.
- Execução automática de tarefas a partir de notas.
- Gestão completa de tarefas, aprovações ou permissões entre usuários.
- Exclusão definitiva de notas pela CLI; o fluxo inicial usa arquivamento.

## 5. Experiência proposta

Os comandos abaixo descrevem a interface do MVP implementado.

```bash
# Registrar o projeto atual
notes init

# Bruno deixa contexto para agentes
notes add "Antes de alterar o login, leia docs/auth.md" --to agents

# Um agente registra um retorno
notes add "Precisamos escolher o provedor de e-mail" --to bruno --author codex

# Consultar e organizar
notes list
notes read 12
notes edit 12
notes search "autenticação"
notes archive 12

# Recuperar contexto para uma sessão
notes context

# Consultar um projeto de outra pasta
notes list --project meu-app

# Usar notas globais
notes add "Preferir respostas em português" --global
notes list --global

# Consumir a saída em uma ferramenta
notes list --json
```

### Comportamento dos comandos

| Comando | Comportamento esperado |
| --- | --- |
| `init` | Cria ou reconhece a identidade do projeto e o registra localmente. Reexecutar preserva o ID existente. |
| `add` | Cria uma nota e devolve ID, escopo e caminho do arquivo. Aceita texto como argumento; sem argumento, lê a entrada padrão quando redirecionada ou abre o editor quando executado em um terminal interativo. |
| `list` | Lista notas ativas do escopo escolhido com ID, título, destinatário e última atualização. `--archived` permite consultar as arquivadas. |
| `read <id>` | Exibe o conteúdo completo e os metadados de uma nota. |
| `edit <id>` | Abre a nota em `$VISUAL` ou `$EDITOR`. Se nenhum editor estiver configurado, orienta como configurá-lo. |
| `edit <id> --body-file <path>` | Permite a um agente fornecer o novo corpo a partir de um arquivo, preservando os metadados. Aceita uma revisão esperada com `--if-revision`. |
| `search <texto>` | Busca literal em título e corpo no escopo escolhido, sem distinguir maiúsculas de minúsculas. |
| `archive <id>` | Marca a nota como arquivada, preservando ID, arquivo e conteúdo. Reexecutar não causa erro. |
| `context` | Reúne notas ativas relevantes do projeto e notas globais, identificando claramente a origem de cada uma. |

Listagens e buscas devem ter ordenação determinística: atualização mais recente primeiro, com ID como desempate. `read` permite consultar uma nota arquivada pelo ID conhecido.

Saída JSON deve estar disponível em `list`, `read`, `search` e `context`, incluindo uma versão do formato. Erros vão para stderr e produzem código de saída diferente de zero; resultados de sucesso vão para stdout.

### Criação de notas com textos longos

Bruno deve poder escrever uma nota longa no editor ou importar seu conteúdo sem colocá-lo em um argumento do shell. A seleção da fonte segue estas regras:

1. Com argumento de texto, usar esse argumento como corpo, sem consumir ou mesclar a entrada padrão.
2. Sem argumento de texto e com entrada padrão redirecionada, ler o conteúdo completo até EOF. Isso cobre arquivo, pipe e heredoc, sem abrir editor.
3. Sem argumento de texto e com entrada padrão ligada a um terminal interativo, abrir o editor configurado: `$VISUAL` tem precedência sobre `$EDITOR`.
4. Se nenhum editor estiver configurado no fluxo interativo, informar como configurar um e apresentar a alternativa de redirecionar um arquivo. Não esperar que o usuário cole conteúdo no terminal nesse caso.

Exemplos da interface proposta:

```bash
# Escrever uma nota longa no editor configurado
notes add --to agents

# Importar o corpo de um arquivo Markdown
notes add --to agents < contexto.md

# Receber o corpo de outro comando
cat contexto.md | notes add --to agents

# Colar vários parágrafos pelo shell
notes add --to agents <<'EOF'
# Contexto da autenticação

Aqui entra um texto longo, com vários parágrafos.

## Decisões
- Usar login por e-mail.
- Manter compatibilidade com as sessões atuais.
EOF
```

O fluxo com editor usa um arquivo temporário contendo apenas o corpo Markdown. Ao fechar o editor com sucesso e conteúdo válido, a CLI cria a nota e gera seus metadados. O ID só é alocado ao persistir a nota; o bloqueio de escrita não permanece adquirido enquanto o editor está aberto.

Conteúdo vazio ou composto apenas por espaços e quebras de linha não cria nota. No editor, isso representa cancelamento normal; em argumento ou entrada padrão, deve gerar erro de validação. Se o editor falhar, nenhuma nota é criada e o caminho do rascunho deve ser informado para recuperação.

Todas as formas de entrada preservam parágrafos, caracteres UTF-8 e formatação Markdown. O título segue a regra da primeira linha não vazia. Conteúdo importado é tratado como corpo, inclusive quando começa com um bloco YAML; não pode substituir os metadados gerados pela CLI.

## 6. Identificação do projeto

### Regra principal

A CLI parte do diretório atual. A raiz Git fornece o local padrão para inicializar um projeto; um ID persistente identifica esse projeto depois da inicialização.

Exemplo:

```text
Diretório atual: ~/Projects/bruno/meu-app/src/components/
Raiz Git:       ~/Projects/bruno/meu-app/
Configuração:   ~/Projects/bruno/meu-app/.notes-project
```

O arquivo `.notes-project` contém:

```yaml
id: 8d43e572-184e-4a35-875d-2358bcf2427a
name: meu-app
```

`id` é um UUID imutável. `name` é um nome de exibição e um possível alias para seleção explícita. Renomear o projeto não altera sua identidade nem desloca suas notas.

### Ordem de resolução

1. `--global` seleciona diretamente o escopo global e dispensa resolução de projeto.
2. `--project <nome-ou-id>` seleciona um projeto já conhecido pelo registro local.
3. Sem seleção explícita, procurar `.notes-project` na pasta atual e nos ancestrais, usando o arquivo mais próximo.
4. Sem esse arquivo, consultar a raiz Git com `git rev-parse --show-toplevel`. A raiz é uma candidata à inicialização; ainda não é uma identidade persistente.
5. Sem configuração e sem Git, orientar o uso de `notes init` na pasta desejada ou a seleção de `--global`.

`--global` e `--project` são mutuamente exclusivos. Um arquivo `.notes-project` inválido gera erro informativo; a CLI não deve ignorá-lo e selecionar outro projeto silenciosamente.

### Inicialização e descoberta

- Dentro de um repositório sem configuração, `notes init` cria `.notes-project` na raiz Git, mesmo quando executado em uma subpasta.
- Fora de Git e sem configuração ancestral, `notes init` usa a pasta atual como raiz.
- Com uma configuração válida já encontrada, `notes init` preserva a identidade e atualiza o registro local.
- Comandos em um projeto ainda não inicializado informam a raiz detectada e pedem a execução de `notes init`; não criam uma identidade implicitamente.
- Uma configuração válida encontrada na navegação pode ser registrada automaticamente para posterior uso com `--project`.
- O registro local guarda ID, nome e caminhos conhecidos; as notas são localizadas pelo ID, não pelo caminho.
- Nomes duplicados são permitidos. Seleção ambígua por nome retorna as opções com seus IDs e exige escolha explícita.
- Um caminho conhecido que deixou de existir não remove o projeto nem suas notas. A seleção explícita pelo ID continua funcionando.

### Mudanças de pasta, clones e worktrees

- Mover uma pasta com `.notes-project` preserva a identidade.
- Clones e worktrees com o mesmo arquivo compartilham a identidade e acessam as mesmas notas no armazenamento local daquela máquina.
- Versionar `.notes-project` é recomendado quando clones e worktrees devem compartilhar a identidade. Clones sem o arquivo não são vinculados automaticamente pela URL do remoto.
- Em outra máquina, possuir o mesmo ID não transfere o conteúdo: sincronização de notas está fora do MVP.
- Copiar `.notes-project` também copia a identidade. Criar uma identidade independente a partir de uma cópia não será uma operação automática no MVP.
- A primeira versão não oferece um comando para inicializar um projeto aninhado dentro de outro já configurado.

O nome da pasta e a URL do remoto não são identificadores persistentes, pois podem mudar ou ser ambíguos.

## 7. Armazenamento e formato

Usar `$XDG_DATA_HOME/notes` como diretório de dados; quando a variável não estiver definida, usar `~/.local/share/notes`.

```text
~/.local/share/notes/
├── projects.json
├── global/
│   └── 001-preferencias.md
└── projects/
    └── 8d43e572-184e-4a35-875d-2358bcf2427a/
        ├── 001-contexto.md
        └── 002-provedor-email.md
```

O UUID organiza o armazenamento por projeto. Nomes amigáveis são resolvidos pelo registro local. Os arquivos ficam fora do repositório por padrão; somente `.notes-project` precisa estar na raiz do projeto.

Cada nota possui front matter YAML e corpo Markdown. Exemplo ilustrativo:

```markdown
---
schema_version: 1
id: 12
title: Escolher provedor de e-mail
author: codex
to: bruno
status: active
created_at: 2026-10-23T15:00:00Z
updated_at: 2026-10-23T15:00:00Z
revision: 1
---

Precisamos escolher o provedor de e-mail antes de implementar os envios.
```

### Regras dos dados

- ID numérico único dentro do escopo, sem reutilização de IDs arquivados.
- Toda saída que mistura escopos identifica projeto ou escopo global junto do ID.
- Destinatários iniciais: `bruno`, `agents` e `all`; padrão: `all`.
- `--author` registra quem escreveu; sem a opção, usar o nome do usuário local. Agentes devem informar seu nome ao criar notas.
- Autor e destinatário são metadados organizacionais, sem função de autenticação ou controle de acesso.
- Título derivado da primeira linha não vazia ao criar a nota; pode ser alterado na edição sem mudar o ID.
- Datas armazenadas em UTC e exibidas no fuso local quando a saída for destinada a pessoas.
- Estado inicial `active`; arquivamento muda para `archived`.
- A revisão aumenta em cada mutação feita pela CLI. Operações condicionais detectam também alterações diretas do arquivo, mesmo quando a revisão não foi atualizada pelo editor externo.
- Editar o corpo pela CLI preserva ID e data de criação. Alterações inválidas dos metadados são rejeitadas sem destruir a nota anterior.
- Arquivos inválidos devem ser identificados com seu caminho. Em consultas agregadas, preservar a apresentação das demais notas e indicar a ocorrência por stderr e código de saída.

Nenhum banco de dados ou serviço em execução é necessário no MVP. Eventuais índices futuros devem ser reconstruíveis a partir das notas e do registro de projetos.

## 8. Integração com agentes e ADEs

Qualquer agente com acesso ao terminal e ao mesmo armazenamento local pode usar a CLI. O acesso pelo editor ocorre diretamente nos arquivos Markdown.

A existência da CLI não faz os agentes consultarem notas automaticamente. Cada ferramenta deve receber instruções no seu mecanismo de contexto, como `AGENTS.md`, `CLAUDE.md` ou equivalente.

Texto sugerido para adoção:

> Ao começar uma tarefa, execute `notes context`. Registre decisões e pendências relevantes. Use notas dirigidas a Bruno para perguntas que possam esperar; perguntas que bloqueiam a tarefa devem ser feitas na conversa. Ao criar notas, informe seu nome com `--author`.

Essas instruções serão fornecidas na documentação; o MVP não altera arquivos de configuração de outros agentes automaticamente.

### Contexto para agentes

- `notes context` inclui notas ativas do projeto selecionado e notas globais destinadas a `agents` ou `all`.
- `--to bruno` permite gerar uma visão dos retornos para Bruno, incluindo notas destinadas a `all`.
- A saída informa escopo, ID, título e corpo, com separação clara entre notas.
- O limite de saída deve ser configurável; quando houver omissão, informar os IDs omitidos e como ler o conteúdo completo.
- Notas são contexto consultado durante a tarefa. Seu conteúdo não executa comandos nem concede autorização por si só.
- Criar uma nota não envia uma mensagem, não desperta outro agente e não garante que Bruno já a leu.

Uma integração futura com Maestri deve definir se exibe os mesmos arquivos ou sincroniza cópias. A estratégia depende das interfaces efetivamente disponíveis e não integra o MVP.

## 9. Concorrência e confiabilidade

- Dois agentes devem poder criar notas simultaneamente sem colisão de IDs.
- Gravações feitas pela CLI devem usar substituição atômica e coordenação por escopo para proteger notas e alocação de IDs.
- Atualizações do registro de projetos também devem ser coordenadas para evitar perda de entradas.
- Uma edição interativa compara o estado lido inicialmente com o arquivo atual antes de salvar. Se outra edição ocorreu, preservar a versão atual e o conteúdo proposto, informando o conflito.
- Uma edição automatizada pode exigir a revisão obtida em `read --json` usando `--if-revision`. Uma revisão desatualizada falha sem sobrescrever conteúdo.
- Sem revisão esperada, uma edição automatizada representa a substituição explícita do corpo atual; a documentação deve orientar agentes a usar a condição de revisão.
- Leitores não devem observar um arquivo parcialmente gravado pela CLI.
- Edições diretas por ferramentas externas não participam dos bloqueios da CLI. O produto deve detectar alterações quando possível e documentar que a garantia de coordenação se aplica às operações pela CLI.
- Falhas de permissão, configuração inválida e conflitos devem apresentar uma causa e uma ação de recuperação compreensíveis.

## 10. Critérios de aceite do MVP

1. Inicializar um repositório a partir de uma subpasta cria `.notes-project` na raiz Git; repetir a operação preserva o UUID.
2. Inicializar uma pasta fora de Git permite usar notas a partir dela e de suas subpastas.
3. Executar um comando em um repositório sem configuração informa a raiz candidata e orienta a inicialização, sem criar notas ou IDs silenciosamente.
4. Mover um projeto inicializado preserva o acesso às suas notas; clones e worktrees com o mesmo ID usam as mesmas notas na mesma máquina.
5. Dois projetos com o mesmo nome mantêm notas separadas, e a seleção ambígua por nome solicita um ID.
6. `add`, `list`, `read`, `edit`, `search` e `archive` funcionam para notas de projeto e para notas globais.
7. Uma nota continua legível como Markdown e pode ser aberta pelo editor configurado.
8. Notas arquivadas deixam de aparecer nas consultas padrão e em `context`, mas continuam acessíveis pelo ID e por `list --archived`.
9. `context` combina os escopos corretos e respeita destinatário e limite de saída, informando omissões.
10. Saídas JSON são válidas, identificam os escopos e incluem revisão para edição condicional.
11. Criações simultâneas produzem IDs distintos; edição interativa concorrente ou edição condicional desatualizada não perde conteúdo silenciosamente.
12. Um agente consegue registrar um retorno para Bruno, e Bruno consegue consultá-lo em uma nova sessão sem depender da conversa anterior.
13. `notes add` sem texto no terminal abre `$VISUAL` ou, na sua ausência, `$EDITOR`; salvar um corpo válido cria a nota, e sair com corpo vazio cancela sem criá-la.
14. Arquivo redirecionado, pipe e heredoc criam notas com textos longos preservando UTF-8 e Markdown, sem abrir editor; um argumento explícito tem precedência e não é mesclado com stdin.
15. Ausência de editor no fluxo interativo, falha do editor e entrada padrão vazia recebem tratamento documentado, sem criar notas parciais ou vazias.

## 11. Validação prevista

A implementação deverá validar o fluxo completo em diretórios temporários: inicialização, criação, consulta, edição, busca, contexto e arquivamento. Os cenários de identidade devem incluir mudança de pasta, nomes duplicados e worktrees.

A criação de notas longas deve cobrir argumento, arquivo redirecionado, pipe, heredoc e terminal interativo, usando um editor controlado para verificar precedência de `$VISUAL`, fallback para `$EDITOR`, cancelamento, falha e preservação de conteúdo. O reconhecimento de terminal deve ser verificado com um pseudoterminal.

Concorrência deve ser verificada com processos simultâneos reais, incluindo criação de notas e edição com revisão desatualizada. A usabilidade deve ser conferida manualmente no terminal e com um agente seguindo as instruções documentadas.

A implementação e os testes estão no repositório. A matriz de evidências dos 15 critérios e o piloto automatizado estão em [docs/VALIDATION.md](docs/VALIDATION.md). O piloto não representa validação humana de Bruno.

## 12. Etapas de entrega

1. Definir a linguagem, o empacotamento e o nome final do executável.
2. Implementar identidade, armazenamento Markdown e comandos essenciais.
3. Implementar contexto, saída JSON e edição condicional para agentes.
4. Validar concorrência e realizar um piloto automatizado dos fluxos de Bruno e agente em um projeto Git representativo, conforme a instrução de execução.
5. Avaliar TUI e integração com Maestri a partir do uso observado.

## 13. Decisões em aberto

Decisões do MVP implementado:

- Python 3.11+ em Linux; PyYAML para front matter; instalação por ambiente virtual, wheel ou sdist.
- Produto/pacote `notes-cli`; executável `notes`. Ambientes virtuais isolam comandos homônimos.
- Contexto limitado por padrão a 12.000 caracteres Unicode dos blocos de notas completos; `--limit` configura o orçamento, excluindo avisos de omissão e envelope JSON.
- Revisão condicional opaca com contador e SHA-256 do arquivo; `revision_number` expõe o contador no JSON.
- Piloto automatizado com sessões independentes, conforme instrução de execução, sem presumir participação humana.

Permanecem fora do MVP:
- Necessidade futura de restauração por comando, tags e histórico de alterações.
- Estratégia de sincronização entre máquinas, se necessária após o piloto.
- Forma de integração visual com Maestri e outros ADEs.

Essas decisões não impedem a especificação do MVP e devem ser resolvidas na etapa correspondente, sem ampliar seu escopo inicial.
