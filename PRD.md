# PRD — notes-cli: memória compartilhada entre Bruno e agentes

Status: MVP remoto e contrato HTTP/JSON v1 definidos; infraestrutura local Worker/D1 (#8) e autenticação individual/revogação (#9) implementadas, com [evidências e limites locais](docs/WORKER-DEVELOPMENT.md). Rotas de negócio e CLI Go pendentes. A versão disponível continua sendo a v0.1 local em Python.
Data: 23 de outubro de 2026.  
Responsável pelo produto: Bruno Gonzaga.  
Produto: `notes-cli`. Comando: `notes`.

O [PRD local v0.1](docs/PRD-local-v0.1.md) e sua [validação](docs/VALIDATION.md) ficam preservados como referência histórica. As evidências existentes não validam o MVP remoto descrito aqui. O [contrato HTTP/JSON v1](docs/REMOTE-CONTRACT.md) fecha as decisões da etapa 1; [configuração](docs/REMOTE-SETUP.md), [esquema D1](docs/D1-SCHEMA.md) e [importação](docs/REMOTE-IMPORT.md) integram essa especificação.

## 1. Problema e objetivo

Conversas e arquivos locais isolam decisões, descobertas e pendências em uma sessão ou máquina. Bruno precisa compartilhar conhecimento com agentes que executam em outras máquinas, independentemente do ADE utilizado.

O objetivo é oferecer uma memória central consultável e editável por Bruno e seus agentes. A primeira entrega deve permitir registrar uma decisão em uma máquina e recuperá-la em outra, com autoria identificada, contexto estruturado e proteção contra sobrescritas concorrentes.

A direção de produto é um segundo cérebro compartilhado. O MVP entrega notas e recuperação de contexto; não tenta implementar de início um sistema completo de conhecimento, colaboração ou tarefas.

## 2. Usuários e casos de uso

| Usuário | Necessidade | Exemplo |
| --- | --- | --- |
| Bruno | Registrar decisões reutilizáveis | “Escolhemos Go para distribuir um binário único.” |
| Agente remoto | Recuperar contexto do projeto | Consultar decisões antes de alterar a distribuição. |
| Agente remoto | Registrar descobertas e pendências | Deixar um retorno para Bruno ou para outro agente. |
| Bruno e agentes | Atualizar conhecimento compartilhado | Corrigir uma nota sem sobrescrever uma edição mais recente. |

## 3. Escopo do MVP remoto

- Um único espaço de Bruno, com notas globais e notas por projeto.
- CLI em Go, API em Cloudflare Worker com TypeScript e persistência em D1.
- Credencial individual para Bruno e para cada agente, provisionada manualmente, com possibilidade de revogação.
- Criar, listar, ler, editar, buscar e arquivar notas Markdown.
- Registrar título, autoria autenticada, destinatário, datas, estado e revisão.
- Identidade de projeto por UUID em `.notes-project`, compartilhável entre máquinas.
- Busca textual literal em título e corpo, sem distinguir maiúsculas de minúsculas; sem promessa de equivalência semântica ou de acentos.
- Recuperação de contexto por projeto e global, com consulta opcional, limite de saída e referências às notas.
- Saída JSON versionada para agentes e automação.
- Importação explícita dos dados locais existentes, preservando os arquivos originais.

### Fora desta entrega

- Vectorize, embeddings, busca semântica, reranking e geração de respostas no servidor.
- R2, anexos, PDFs e ingestão automática de documentos ou conversas.
- Interface web, TUI, MCP e integração visual com Maestri ou outros ADEs.
- Sincronização offline, cache de notas e resolução automática de conflitos.
- Múltiplos usuários/espaços, permissões detalhadas por projeto e fluxo de aprovação.
- Histórico completo de versões e restauração por comando; o MVP mantém a versão atual e seu contador de revisão.
- Tipos específicos de decisão/procedimento/pendência, confirmação de conhecimento e classificação automática.
- Exclusão definitiva, notificações, execução de tarefas e consulta automática pelos agentes.
- Compatibilidade completa com todos os comportamentos da CLI Python.

## 4. Arquitetura e fonte oficial

```text
Bruno / agentes em diferentes máquinas
                 |
          CLI notes em Go
                 | HTTPS + credencial individual
        API em Cloudflare Worker (TypeScript)
                 |
          D1: fonte oficial das notas
```

- A CLI identifica o projeto, recebe texto ou abre o editor e chama a API. Nenhum processo local permanente é necessário.
- O Worker autentica cada operação, valida entradas e aplica as regras de revisão e escopo.
- D1 guarda projetos, notas, identidades/credenciais e metadados de importação necessários para evitar duplicatas.
- Conteúdo Markdown é armazenado no banco; arquivos locais deixam de ser a fonte oficial na versão remota.
- O MVP exige conexão para consultar ou alterar notas. Erros de rede não podem ser apresentados como sucesso ou lista vazia.
- As credenciais da API não concedem acesso direto à conta Cloudflare nem ao banco.

## 5. Experiência e contrato da CLI

A interface abaixo está especificada no [contrato v1](docs/REMOTE-CONTRACT.md), mas ainda não está implementada. A [configuração de endpoint e arquivo de credencial](docs/REMOTE-SETUP.md#1-configuração-da-cli-go) é explícita, sem segredos no repositório ou em argumentos.

```bash
notes init
notes add "Escolhemos Go para distribuir um binário único" --to agents
notes list --json
notes search "Go" --json
notes read 1 --json
notes edit 1 --body-file decisao.md --if-revision 'REVISAO-DA-LEITURA'
notes context --query "distribuição" --json
notes archive 1 --if-revision 'REVISAO-ATUAL'
notes add "Preferir respostas em português" --global
notes list --project UUID-DO-PROJETO
```

| Comando | Comportamento esperado |
| --- | --- |
| `init` | Cria ou reconhece `.notes-project` e registra o UUID no serviço; repetir preserva a identidade. |
| `add` | Recebe corpo por argumento, stdin ou editor; cria a nota e retorna ID, escopo e revisão. |
| `list` | Lista notas ativas do escopo; `--archived` seleciona arquivadas. |
| `read <id>` | Retorna corpo completo e metadados, incluindo revisão, mesmo para uma nota arquivada. |
| `edit <id>` | Abre rascunho local no editor e envia a alteração condicionada à revisão inicial. |
| `edit <id> --body-file <path>` | Substitui apenas o corpo, exigindo `--if-revision`. |
| `search <texto>` | Busca textual nas notas ativas do escopo escolhido; permite consultar arquivadas explicitamente. |
| `context [--query <texto>]` | Recupera notas ativas do projeto e globais, com origem e limite de tamanho. |
| `archive <id>` | Arquiva sem apagar conteúdo; exige revisão esperada e é idempotente para o mesmo estado já arquivado. |

- `--global` e `--project` são mutuamente exclusivos. Nomes ambíguos exigem UUID.
- Sem seleção explícita, usar a configuração ancestral mais próxima. `init` mantém a regra de raiz Git, ou pasta atual fora de Git, da versão local.
- Clones e máquinas com o mesmo `.notes-project` acessam as mesmas notas quando autenticados no mesmo serviço. O UUID não é credencial.
- Uma falha no registro remoto pode deixar a configuração local criada; repetir `init` deve concluir o registro sem gerar outro UUID.
- IDs numéricos são únicos por escopo e nunca reutilizados. Toda referência inclui escopo e ID.
- Listagens e busca usam atualização decrescente, com ID crescente no desempate.
- Todos os comandos remotos aceitam `--json`, com `api: "notes-remote"` e `schema_version: 1`. Listagens/buscas retornam resumos paginados; `read` retorna o corpo completo. O [contrato v1](docs/REMOTE-CONTRACT.md) não presume compatibilidade com o JSON local.
- Resultados vão para stdout; erros para stderr, com saída diferente de zero. JSON não contém logs nem credenciais.

### Entrada de texto e editor

Preservar a precedência atual: argumento explícito; na ausência dele, stdin redirecionado; em terminal, `$VISUAL` ou `$EDITOR`. Preservar UTF-8, parágrafos e Markdown.

Criar com corpo vazio no editor cancela sem gravar; argumento ou stdin vazio gera erro. A edição acontece em rascunho local, sem manter transação aberta no servidor. Falha do editor, de rede ou conflito preserva o rascunho editado e informa seu caminho. O rascunho não constitui armazenamento offline sincronizado.

## 6. Dados, identidade e concorrência

- Projeto: UUID e nome; caminhos da máquina permanecem locais.
- Nota: ID no escopo, corpo Markdown, título, destinatário, estado, criação, atualização, criador, último editor e revisão.
- Título inicial: primeira linha não vazia do corpo. Destinatários: `bruno`, `agents` e `all`; padrão `all`.
- Datas são geradas pelo servidor em UTC. A revisão é retornada pela API e tratada como opaca pelo cliente.
- Criador e último editor vêm da credencial autenticada. `--author` não pode se passar por outra identidade; eventual autoria histórica importada é metadado separado.
- Destinatário organiza consultas; não restringe acesso. Todas as credenciais deste espaço têm leitura e escrita em todos os projetos e no global no MVP.
- Agentes podem criar, editar e arquivar diretamente; não há estado “confirmado” nem aprovação nesta entrega.
- Atualização deve comparar a revisão e gravar a mutação atomicamente no servidor. Revisão antiga recebe conflito sem sobrescrita; mudança efetiva incrementa a revisão e ausência de mudança preserva revisão e datas.
- Criações concorrentes recebem IDs distintos. Repetição de criação após timeout usa uma chave de idempotência para não duplicar a nota.
- Limites definidos no contrato e aplicados pela API: corpo até 65.536 bytes UTF-8, consulta até 256 caracteres/1.024 bytes, páginas até 100 registros e HTTP até 1 MiB. Caracteres são valores escalares Unicode. Busca usa full default case folding Unicode 15.1 (C + F), sem normalizar acentos; detalhes e casos de teste no contrato.
- Credenciais devem ser armazenadas como verificadores não reversíveis no servidor; segredos não aparecem em logs, notas nem mensagens de erro.

## 7. Contexto e RAG do MVP

O serviço entrega recuperação de contexto para RAG; o modelo do agente consumidor produz a resposta. Não é necessário chamar outro LLM no servidor.

1. O agente envia uma consulta e o projeto selecionado.
2. A API consulta notas ativas desse projeto e globais, respeitando destinatário.
3. Retorna notas completas que caibam no orçamento, com escopo, ID, título, autoria, atualização e revisão.
4. O agente usa o contexto na tarefa e referencia os registros que sustentam sua resposta.

`context` sem consulta mantém a recuperação por escopo. Com `--query`, aplica a mesma busca textual de `search`. O padrão inclui destinatários `agents` e `all`; `--to bruno` inclui `bruno` e `all`, e `--to all` inclui apenas `all`. `--global` consulta somente notas globais.

O orçamento padrão é 12.000 caracteres Unicode dos blocos completos, configurável por `--limit` entre 0 e 48.000. Após filtros, até 100 candidatos são processados; acima disso a API retorna erro explícito `context_too_broad`, orientando refinar a consulta ou usar busca paginada. O [contrato](docs/REMOTE-CONTRACT.md#5-contexto-e-orçamento) fixa os blocos e a contagem. Não cortar notas ao meio; informar omissões e como ler os registros completos. O JSON informa limite, caracteres usados, notas incluídas e omitidas. Metadados do envelope e avisos ficam fora do orçamento.

Uma consulta sem correspondências retorna uma busca vazia bem-sucedida; uma falha de rede ou do serviço retorna erro. O agente não deve tratar falta de evidência como confirmação. Busca textual pode deixar de encontrar sinônimos: essa é uma limitação explícita até a etapa semântica.

Notas são contexto, não autorização para executar ações. Criar uma nota não desperta agentes e não garante leitura humana. A documentação fornece instruções de adoção; a CLI não modifica `AGENTS.md` ou equivalentes automaticamente.

## 8. Migração e compatibilidade

- Manter produto `notes-cli`, comando `notes`, Markdown e UUID de `.notes-project`.
- A versão Python continua funcional durante a construção e validação do caminho remoto.
- Importação é explícita, com prévia do que será enviado e relatório de sucessos/falhas; não envia notas silenciosamente.
- Preservar corpo, escopo, autoria histórica e datas originais como dados de origem. Revisões remotas são novas e a autoria autenticada da importação é registrada separadamente.
- Importações repetidas identificam a mesma origem sem duplicar notas; colisões ou conteúdos divergentes são relatados, sem sobrescrita automática.
- O identificador remoto atribuído a cada nota consta do relatório. Tokens de revisão locais não são reutilizados na API remota.
- Não remover nem alterar o armazenamento Python. Após a transição, edições locais e remotas não são sincronizadas. O [formato de importação](docs/REMOTE-IMPORT.md) fixa `source_id`, hashes, prévia, remapeamento de IDs e relatório; a [tabela de incompatibilidades](docs/REMOTE-SETUP.md#5-incompatibilidades-com-python-e-distribuição) orienta a adaptação de agentes.
- Publicar instruções de instalação do binário e substituição do executável no PATH, evitando confundir as duas versões.

## 9. Critérios de aceite

1. Uma CLI Go instalada em Linux usa a API sem depender de Python no runtime.
2. Inicializar em subpasta Git e repetir `init` preserva o UUID; outra máquina com a mesma configuração acessa o mesmo projeto remoto.
3. Uma nota criada na máquina A é encontrada, lida e usada como contexto por um agente na máquina B.
4. Credenciais distintas registram autores distintos; credencial ausente, inválida ou revogada não permite ler nem gravar dados.
5. Criar, listar, ler, editar, buscar e arquivar funcionam em projeto e global, sem misturar projetos diferentes.
6. Editor, stdin e argumento preservam Markdown/UTF-8; falhas recuperáveis não descartam o rascunho.
7. Busca retorna somente correspondências textuais no escopo pedido; ausência de resultados é sucesso vazio, enquanto indisponibilidade é erro explícito.
8. `context` combina os escopos corretos, filtra consulta/destinatário, respeita o orçamento e informa referências, revisões e omissões.
9. Saídas JSON seguem o contrato documentado; erros não contaminam stdout nem expõem segredos.
10. Criações simultâneas recebem IDs distintos; repetir uma criação com a mesma chave de idempotência não duplica a nota.
11. Duas edições baseadas na mesma revisão não se sobrescrevem: uma é aceita e a outra recebe conflito. Operações sem mudança não incrementam revisão.
12. Arquivadas somem da busca/contexto padrão, permanecem legíveis por ID e o arquivamento repetido não altera novamente revisão ou datas.
13. Importação de uma amostra local preserva os dados de origem e informa o mapeamento; repetição não duplica notas, divergências são reportadas e os arquivos locais ficam intactos.
14. O piloto remoto registra um agente recuperando a decisão sobre Go e referenciando a nota de origem, sem geração de resposta dentro do Worker.

## 10. Próximos passos e ordem de entrega

As cinco etapas abaixo têm [milestones e issues no GitHub](docs/ROADMAP.md), com dependências e critérios de conclusão. Mudanças realizadas são registradas em [changelog.md](changelog.md).

| Etapa | Trabalho | Condição para avançar |
| --- | --- | --- |
| 1. Contratos e configuração | Definir endpoints, JSON, erros, limites, revisão, idempotência, credenciais e importação; escolher nomes das variáveis/configuração. | Contrato escrito e exemplos revisáveis cobrindo o fluxo entre duas máquinas. |
| 2. API e persistência | Criar Worker TypeScript, migrações D1, autenticação/revogação, projetos, CRUD, busca textual e contexto limitado. | Testes de integração cobrem credenciais, escopos, concorrência, retries e revisões. |
| 3. CLI Go | Implementar configuração, identidade local, chamadas HTTP, comandos, JSON, stdin e editor; build Linux. | Fluxo completo funciona contra a API de desenvolvimento com isolamento de dados de teste. |
| 4. Migração e distribuição | Implementar prévia/importação e relatório; documentar instalação e coexistência com Python. | Amostra importada sem perda ou duplicação; binário instalável em ambiente limpo. |
| 5. Piloto remoto | Publicar ambiente do MVP, provisionar credenciais e executar cenários reais em duas máquinas. | Registrar evidências dos 14 critérios, falhas de rede e conflito; separar validação automatizada de humana. |

A entrega termina com o piloto remoto e documentação de uso. Os testes Python continuam como referência do comportamento local; testes novos devem validar os riscos reais da API e da CLI remota. A etapa 1 está documentada no [contrato v1](docs/REMOTE-CONTRACT.md), com [cobertura de especificação dos 14 critérios](docs/REMOTE-CONTRACT.md#8-cobertura-dos-14-critérios-do-prd). As etapas 2–5 e o aceite funcional permanecem pendentes; documentação não equivale à implementação.

## 11. Evolução após o piloto

1. **Confiabilidade e recuperação:** exportação completa independente, procedimento de backup/restauração verificado, histórico de versões e observabilidade conforme uso real.
2. **Busca semântica:** avaliar Vectorize + embeddings ou AI Search; combinar busca textual e semântica, medir recuperação com perguntas reais, invalidar conteúdo antigo e conferir revisão/permissões antes de retorná-lo. O índice é derivado, reconstruível e não substitui D1.
3. **Conhecimento estruturado:** tipos de registro, referências de origem, registros superados e regra de aprovação para decisões confirmadas, a definir com Bruno.
4. **Novas interfaces:** MCP para agentes, interface web para Bruno e anexos em R2 quando houver demanda.
5. **Colaboração ampliada:** permissões por projeto, outros usuários/espaços e eventual modo offline, somente se o uso justificar.

## 12. Decisões e pendências

Decisões deste MVP: Go na CLI; Worker TypeScript; D1 como fonte oficial; um espaço de Bruno; credenciais individuais; projetos e global; busca textual para recuperação de contexto; importação explícita; sem sincronização offline nem compatibilidade integral com Python.

Contrato da etapa 1 fechado em [docs/REMOTE-CONTRACT.md](docs/REMOTE-CONTRACT.md), com decisões de [configuração e provisionamento/revogação](docs/REMOTE-SETUP.md), [esquema D1 e atomicidade](docs/D1-SCHEMA.md) e [origem/mapeamento da importação](docs/REMOTE-IMPORT.md). Recibos idempotentes não expiram no MVP; revisões são tokens opacos; autoria vem da identidade autenticada; importação nunca sobrescreve automaticamente. Essas escolhas não ampliam o escopo. Não restam decisões de contrato bloqueando M2/M3; URL real, recursos e credenciais serão provisionados nas respectivas etapas.

Histórico completo, aprovação de decisões e permissões por projeto não são requisitos desta entrega. A intenção de segundo cérebro orienta a evolução, mas não antecipa esses recursos.
