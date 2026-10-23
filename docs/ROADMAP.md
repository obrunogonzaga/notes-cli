# Milestones e issues

O [PRD](../PRD.md) define o escopo. O [GitHub](https://github.com/obrunogonzaga/notes-cli/issues) registra andamento, responsáveis e discussão; o [changelog](../changelog.md) registra mudanças realizadas.

Planejamento criado em 23/10/2026. A infraestrutura local Worker/D1 da #8 foi implementada; a API funcional e a CLI Go continuam pendentes. A versão de uso disponível continua sendo a v0.1 local em Python. Nenhum prazo foi assumido.

## MVP remoto

| Milestone | Issues | Dependências |
| --- | --- | --- |
| [M1 — Contrato do MVP remoto](https://github.com/obrunogonzaga/notes-cli/milestone/1) | [#7](https://github.com/obrunogonzaga/notes-cli/issues/7) | Contrato documentado; implementar M2/M3 a partir dele. |
| [M2 — API remota com Worker e D1](https://github.com/obrunogonzaga/notes-cli/milestone/2) | [#8](https://github.com/obrunogonzaga/notes-cli/issues/8), [#9](https://github.com/obrunogonzaga/notes-cli/issues/9), [#10](https://github.com/obrunogonzaga/notes-cli/issues/10), [#11](https://github.com/obrunogonzaga/notes-cli/issues/11) | M1. |
| [M3 — CLI em Go](https://github.com/obrunogonzaga/notes-cli/milestone/3) | [#12](https://github.com/obrunogonzaga/notes-cli/issues/12), [#13](https://github.com/obrunogonzaga/notes-cli/issues/13) | Contrato M1; integração com M2. |
| [M4 — Migração e distribuição](https://github.com/obrunogonzaga/notes-cli/milestone/4) | [#14](https://github.com/obrunogonzaga/notes-cli/issues/14), [#15](https://github.com/obrunogonzaga/notes-cli/issues/15) | M2 e M3. |
| [M5 — Piloto remoto e aceite do MVP](https://github.com/obrunogonzaga/notes-cli/milestone/5) | [#16](https://github.com/obrunogonzaga/notes-cli/issues/16) | M1–M4. |

Contrato de M1: [HTTP/JSON e matriz dos 14 critérios](REMOTE-CONTRACT.md), [configuração/credenciais/compatibilidade](REMOTE-SETUP.md), [D1](D1-SCHEMA.md) e [importação](REMOTE-IMPORT.md). A entrega de #7 é especificação; não aplica migrações, cria API/CLI remotas ou valida o piloto.

A #8 entrega [migrações, base Worker e testes isolados](WORKER-DEVELOPMENT.md), sem recursos Cloudflare ou deploy. M2 permanece em andamento: autenticação (#9), projetos/notas (#10) e busca/contexto (#11) não foram antecipados.

### Entregas

- [#7 — Definir contrato HTTP/JSON e configuração do MVP remoto](https://github.com/obrunogonzaga/notes-cli/issues/7)
- [#8 — Preparar Worker TypeScript, migrações D1 e ambiente de desenvolvimento](https://github.com/obrunogonzaga/notes-cli/issues/8)
- [#9 — Implementar credenciais individuais, autoria autenticada e revogação](https://github.com/obrunogonzaga/notes-cli/issues/9)
- [#10 — Implementar projetos e API de notas com revisões e idempotência](https://github.com/obrunogonzaga/notes-cli/issues/10)
- [#11 — Implementar busca textual e contexto limitado para RAG](https://github.com/obrunogonzaga/notes-cli/issues/11)
- [#12 — Criar base da CLI Go, configuração HTTP e identidade de projetos](https://github.com/obrunogonzaga/notes-cli/issues/12)
- [#13 — Implementar comandos Go, entrada de texto, editor e JSON](https://github.com/obrunogonzaga/notes-cli/issues/13)
- [#14 — Importar notas Python com prévia e relatório sem duplicação](https://github.com/obrunogonzaga/notes-cli/issues/14)
- [#15 — Distribuir binário Linux e adaptar CI e documentação ao MVP remoto](https://github.com/obrunogonzaga/notes-cli/issues/15)
- [#16 — Publicar ambiente do MVP e validar piloto entre duas máquinas](https://github.com/obrunogonzaga/notes-cli/issues/16)

As dependências detalhadas e os critérios de conclusão estão no corpo de cada issue. Consultar o GitHub para o estado atual; a documentação de M1 não altera automaticamente issues ou milestones. O aceite final exige evidências dos 14 critérios do PRD e piloto em duas máquinas reais.

## Backlog pós-MVP

Estas issues não integram as milestones do MVP. Cada uma precisa de detalhamento e, quando necessário, divisão em entregas menores após o piloto.

- [#17 — exportação completa, recuperação e histórico de versões](https://github.com/obrunogonzaga/notes-cli/issues/17)
- [#18 — avaliar busca híbrida com Vectorize ou AI Search](https://github.com/obrunogonzaga/notes-cli/issues/18)
- [#19 — estruturar decisões, procedimentos e conhecimento superado](https://github.com/obrunogonzaga/notes-cli/issues/19)
- [#20 — avaliar MCP, interface web e anexos em R2](https://github.com/obrunogonzaga/notes-cli/issues/20)
- [#21 — avaliar permissões por projeto, múltiplos espaços e offline](https://github.com/obrunogonzaga/notes-cli/issues/21)

## Como manter o acompanhamento

- Associar cada entrega à issue e à milestone correspondentes; referenciar a issue no PR.
- Ao entregar uma mudança, atualizar a seção “Não lançado” de `changelog.md` com o resultado e links de issue/PR. Não registrar trabalho planejado como funcionalidade pronta.
- Fechar a issue somente após cumprir seus critérios; registrar evidências de validação e limitações relevantes.
- Fechar cada milestone quando suas entregas e condições de conclusão estiverem atendidas.
- Ao publicar uma versão, mover os registros de “Não lançado” para a versão e a data reais, mantendo uma nova seção para alterações seguintes.
- Se o escopo mudar, atualizar PRD e issues; este mapa não substitui o estado do GitHub.
