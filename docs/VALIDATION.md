# Validação do MVP local v0.1

Este documento valida os critérios do [PRD local v0.1](PRD-local-v0.1.md).
O [MVP remoto vigente](../PRD.md) ainda não foi implementado nem validado. A [matriz de cobertura do contrato remoto](REMOTE-CONTRACT.md#8-cobertura-dos-14-critérios-do-prd) relaciona os 14 critérios remotos a regras de especificação e às validações futuras; não usa os testes locais como evidência de aceite remoto.

Validação automatizada em Linux, 23/10/2026. Suite local: 42 testes passando,
sem skips. A CI executa lint, testes e build em Python 3.11 e 3.14.
Todos os testes usam diretórios temporários e armazenamento isolado.

## Matriz dos 15 critérios do PRD

| Critério | Evidência executável |
| --- | --- |
| 1. Inicialização na raiz Git e UUID estável | `test_git_root_and_reinitialize` em [test_core.py](../tests/test_core.py). |
| 2. Pastas fora de Git e subpastas | `test_non_git_and_metadata` em [test_core.py](../tests/test_core.py). |
| 3. Orientação sem inicialização implícita | `test_git_root_and_reinitialize` e `test_global_without_project_and_validation`. |
| 4. Movimento, clones e worktrees | `test_scope_resolution_duplicate_names_and_move` e `test_real_clone_and_worktree_share_identity` em [test_delivery.py](../tests/test_delivery.py); usa clone e worktree Git reais. |
| 5. Nomes iguais, isolamento e ambiguidade | `test_scope_resolution_duplicate_names_and_move`; verifica escolha por UUID mesmo com caminhos antigos ausentes. |
| 6. Comandos em projeto e global | Testes de criação/leitura/busca/arquivamento em `test_core.py`, `test_body_file_conditional_revision` parametrizado e piloto completo. |
| 7. Markdown legível e editor | `test_non_git_and_metadata`, `test_interactive_edit_metadata_and_invalid_preservation` em [test_agents.py](../tests/test_agents.py). |
| 8. Arquivamento e consulta por ID | `test_archive_idempotent_and_ids` nos dois escopos, `test_context_filters_limits_and_scopes` e piloto. |
| 9. Contexto, destinatários e orçamento | `test_context_filters_limits_and_scopes`: mistura de escopos, exclusão de outro projeto, destinatários, limites exato/zero/parcial, origem e comandos de leitura. |
| 10. JSON e revisão | `test_json_and_partial_errors`, `test_body_file_conditional_revision`, contrato no [README](../README.md#automação-e-revisões). |
| 11. Concorrência e ausência de perda silenciosa | `test_concurrent_adds_and_registry`, `test_concurrent_project_adds`, `test_concurrent_conditional_updates`, `test_editor_does_not_lock_and_detects_conflict` e `test_interactive_edit_detects_external_file_change`. São processos reais, com sincronização do editor por arquivos de sinalização. |
| 12. Retorno recuperável em outra sessão | `test_automated_bruno_agent_pilot` em [test_distribution.py](../tests/test_distribution.py); cada comando roda em novo processo/sessão. |
| 13. Editor, precedência e cancelamento | `test_tty_editor_precedence`, `test_editor_cancel_failure_and_missing`, usando pseudoterminais reais. |
| 14. Argumento/arquivo/pipe/heredoc e UTF-8 | `test_long_input` em quatro modalidades, inclusive CRLF, Markdown e YAML no corpo; `test_explicit_argument_does_not_read_stdin` mantém stdin aberto e exige término sem EOF. |
| 15. Editor ausente, falha e stdin vazio | `test_editor_cancel_failure_and_missing` verifica orientação, rascunho recuperável, ausência de nota/ID parcial e cancelamento; `test_non_utf8_body_is_rejected` verifica recuperação sem sobrescrita. |

## Confiabilidade e distribuição

- `test_readers_never_observe_partial_cli_writes`: leitores de JSON observam somente
  corpos completos durante 18 substituições de 80 mil caracteres; revisão final 19.
- `test_file_and_write_permissions_preserve_notes`: arquivo ilegível não esconde
  outras notas; falha de gravação preserva a versão anterior e não cria nota parcial.
- `test_unreadable_scope_is_error_and_context_preserves_global`: diretório sem
  permissão retorna erro e caminho, mantendo contexto global válido. Este teste
  reproduziu uma falha inicial: `Path.glob` ocultava a falta de permissão. A leitura
  agora enumera explicitamente o diretório e preserva a causa do erro.
- `test_malformed_metadata_errors_without_traceback`: rejeita tipos inválidos,
  versão desconhecida e metadados corrompidos indicando o caminho.
- `test_global_xdg_fallback` e `test_unregistered_project_config_auto_registers`:
  fallback XDG e descoberta de configuração válida em armazenamento novo.
- `test_clean_wheel_install_and_console_script` e
  `test_clean_source_distribution_install`: wheel e sdist instalados em ambientes
  virtuais novos, sem herdar pacotes do ambiente de desenvolvimento. O módulo
  importado vem de site-packages do ambiente instalado, fora do checkout.
- Nome de produto/pacote: `notes-cli`; executável: `notes`. Nenhum executável
  `notes` foi encontrado no PATH do ambiente original antes da instalação. Um
  ambiente virtual evita conflitos com ferramentas homônimas de outras origens.
- Conferência adicional em terminal PTY: ajuda, criação, listagem, leitura, contexto
  e arquivamento exibiram origem/ID, conteúdo e datas no fuso local corretamente.
- Lint: `ruff check .`; distribuição: `python -m build`; CI: `.github/workflows/ci.yml`.

Os testes de permissão precisam de usuário sem privilégios de root; essa é a
configuração local validada e dos runners da CI. Os testes de instalação baixam
dependências e precisam de acesso ao índice de pacotes.

## Piloto automatizado

[scripts/pilot.py](../scripts/pilot.py) cria um projeto Git representativo com
`docs/auth.md` e `src/`, inicializa a CLI pela subpasta e usa dados isolados.
O piloto executou 16 comandos da CLI instalada em ambiente limpo:

1. Bruno deixa contexto de login para agentes e uma preferência global.
2. O agente lê o contexto combinado e registra uma pendência para Bruno.
3. Uma nova sessão representando Bruno recupera a pendência sem depender da conversa.
4. A nota é editada com a revisão lida; um agente com revisão antiga recebe conflito.
5. Busca recupera a decisão; arquivamento é idempotente; leitura por ID preserva o corpo.

Resultado: aprovado, com 15 comandos de status zero e uma falha esperada de revisão
obsoleta. Evidência real de execução: [pilot.json](pilot.json), incluindo horário,
versão, argumentos, saída e código de cada comando. Caminhos temporários foram
normalizados para `<sandbox>`; os diretórios usados no piloto foram removidos.

Esse piloto é **automatizado**, sem participação nem validação humana de Bruno.
A instrução de execução autorizou simular os dois papéis sem aguardar aprovação.

Para reproduzir:

```bash
.venv/bin/python scripts/pilot.py --notes .venv/bin/notes --output /tmp/notes-pilot.json
```

## Limites documentados

O suporte inicial é Linux/Python 3.11+. O orçamento de contexto mede caracteres
Unicode de blocos completos; envelope JSON e avisos de omissão ficam fora dele.
Edição externa não participa dos bloqueios: o hash detecta o conteúdo alterado
observado antes da gravação, mas não coordena ferramentas que gravem durante a
janela de comparação/substituição. Não há sincronização entre máquinas, TUI,
restauração por comando ou integração visual com Maestri no MVP.
