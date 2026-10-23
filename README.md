# notes-cli

CLI local de notas compartilhadas entre Bruno e agentes, acessível pelo terminal e por diferentes ambientes de desenvolvimento.

O projeto nasce da experiência com as notas do Maestri: um lugar persistente para deixar contexto, decisões, recados e retornos, sem depender de um ADE específico.

## Estado do projeto

Planejamento. A CLI ainda não foi implementada; os comandos apresentados na documentação são a interface proposta.

## Documentação

- [PRD](./PRD.md): objetivo, experiência de uso, identificação dos projetos, armazenamento, requisitos e critérios de aceite.

## Direção inicial

- Comando proposto: `notes`.
- Um arquivo Markdown por nota.
- Notas por projeto e notas globais.
- Identificação persistente do projeto por `.notes-project`.
- Uso por agentes através da CLI e das instruções de cada ferramenta.
- TUI e integração visual com Maestri previstas para etapas posteriores.

O nome da pasta é `notes-cli`; o nome definitivo do produto e a disponibilidade do comando `notes` ainda serão avaliados antes da distribuição.
