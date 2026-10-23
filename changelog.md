# Changelog

Registro de mudanças realizadas no projeto. Funcionalidades planejadas ficam no [PRD](PRD.md) e nas [milestones e issues](docs/ROADMAP.md).

## Como atualizar

- Registrar cada mudança entregue em “Não lançado”, junto da alteração e com links de issue/PR quando existirem.
- Usar categorias como Adicionado, Alterado, Corrigido e Removido; descrever o efeito para Bruno e os agentes.
- Registrar incompatibilidades, instruções de migração e validação relevante quando aplicáveis.
- Ao publicar uma versão, agrupar os registros com a versão e a data reais. Não tratar fechamento de planejamento como implementação.

## Não lançado

### Adicionado

- [#9 — Credenciais individuais e revogação](https://github.com/obrunogonzaga/notes-cli/issues/9): proteção de toda a superfície `/v1` antes de revelar rotas/recursos, token `nt1` com UUIDs v4 e 256 bits aleatórios, SHA-256 do token completo e comparação nativa em tempo constante. Identidade/credencial revalidadas no D1 primário a cada tentativa; sem cache. `/healthz` preservado como sonda pública de infraestrutura.
- [Utilitário operacional e runbook](docs/REMOTE-SETUP.md#utilitário-operacional-da-9): criação, rotação, revogação idempotente e desativação, com entrada por arquivo privado/stdin e token somente em novo arquivo 0600 em diretório 0700; parâmetros SQL vinculados, sem segredos em argumentos/logs/erros. Backend local verificado; adaptador para D1 existente via API Cloudflare implementado com teste de protocolo simulado, sem chamada remota ou provisionamento real.
- [Autoria e guardas para #10](docs/D1-SCHEMA.md#integração-obrigatória-dos-handlers-da-10): contexto autenticado imutável e predicados transacionais, demonstrados em fixtures SQL no D1 local. [Validação da #9](docs/WORKER-DEVELOPMENT.md#resultados-da-9-e-limites-de-aceite): TypeScript, 22 testes Workers, 4 testes Node/Wrangler, Ruff, 42 testes Python e build wheel/sdist aprovados. O registro distingue HTTP efetivo de autoria/recibos sintéticos e integração futura; CRUD, busca/contexto, importação e CLI Go continuam pendentes. Suíte Python preservada.

- Infraestrutura local da [#8](https://github.com/obrunogonzaga/notes-cli/issues/8) em `worker/`: Worker TypeScript com sonda `/healthz`, configuração local sem credenciais, dependências fixadas e duas migrações D1 de M1 (seis tabelas, FKs, índices, triggers de sequência e seed global). Não implementa autenticação, rotas de notas, busca/contexto ou importação.
- [Ambiente reproduzível e evidências](docs/WORKER-DEVELOPMENT.md): TypeScript, 13 testes Workers e 1 teste Wrangler aprovados, incluindo banco novo, atualização com dados existentes, reexecução e rollback de nota/contador/projeto; scripts locais de migração e Worker/D1 também verificados. Job CI Worker separado adicionado para validação hospedada; D1 remoto permanece pendente. Python preservado, com lint e 42 testes aprovados em ambiente isolado. Nenhum recurso Cloudflare, deploy ou piloto remoto criado.

- [Contrato HTTP/JSON v1 do MVP remoto](docs/REMOTE-CONTRACT.md) para [#7](https://github.com/obrunogonzaga/notes-cli/issues/7): endpoints, envelopes/erros/limites, Unicode, revisão condicional, idempotência permanente e retries, com matriz de cobertura dos 14 critérios do PRD.
- Especificações de [configuração e provisionamento/revogação](docs/REMOTE-SETUP.md), [esquema/transações D1](docs/D1-SCHEMA.md) e [importação explícita com origem, colisões e mapeamento](docs/REMOTE-IMPORT.md), incluindo fluxo entre duas máquinas e incompatibilidades Python. São documentação para M2–M4, sem implementação, provisionamento ou piloto remoto. [Revisão da especificação](docs/REMOTE-CONTRACT.md#9-revisão-de-especificação-da-issue-7): exemplos JSON, links/âncoras, orçamento de contexto e esquema/invariantes SQL verificados localmente; integração D1 permanece para M2.

- `changelog.md` com convenção de atualização contínua.
- [Mapa de entregas](docs/ROADMAP.md) com cinco [milestones](https://github.com/obrunogonzaga/notes-cli/milestones), dez issues para o MVP remoto e cinco de evolução posterior, incluindo dependências e critérios de conclusão.
- [PRD local v0.1](docs/PRD-local-v0.1.md) preservado como referência histórica da implementação Python.

### Alterado

- PRD, README, roadmap e validação histórica apontam para o contrato remoto; decisões antes pendentes de M1 estão registradas, preservando o planejamento e a referência Python.

- [PRD vigente](PRD.md) atualizado para memória compartilhada entre máquinas: CLI Go, Worker TypeScript, D1, credenciais individuais, revisões condicionais, busca textual para RAG e importação explícita. Este registro documenta a definição do escopo; os recursos remotos permanecem pendentes de implementação.
- README e matriz de validação identificam a versão local disponível e distinguem suas evidências do futuro MVP remoto.

## 0.1.0 — Base local implementada — 2026-10-23

Referência histórica da versão presente no código. Esta entrada não indica publicação de release ou tag no GitHub.

### Adicionado

- CLI Python com identidade persistente de projetos, notas Markdown em projeto/global e gravações coordenadas: [#1](https://github.com/obrunogonzaga/notes-cli/issues/1), [PR #4](https://github.com/obrunogonzaga/notes-cli/pull/4).
- Edição por editor/arquivo, entrada de textos longos, revisões condicionais, saída JSON e contexto para agentes: [#2](https://github.com/obrunogonzaga/notes-cli/issues/2), [PR #5](https://github.com/obrunogonzaga/notes-cli/pull/5).
- Validação automatizada, instalação de wheel/sdist e piloto automatizado Bruno/agente: [#3](https://github.com/obrunogonzaga/notes-cli/issues/3), [PR #6](https://github.com/obrunogonzaga/notes-cli/pull/6). Evidências históricas em [docs/VALIDATION.md](docs/VALIDATION.md); não equivalem a um piloto remoto ou validação humana.
