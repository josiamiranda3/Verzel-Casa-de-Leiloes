# Etapa 14 --- Testes Automatizados

## Resultado final

-   **Data da execução:** 27/10/2026
-   **Comando:** `python -m pytest -v`
-   **Resultado:** `82 passed in 5.14s`
-   **Falhas:** 0
-   **Erros:** 0
-   **Ambiente:** Windows, Python 3.13.14, pytest 9.1.1, PostgreSQL de
    testes

## Cobertura funcional validada

A suíte automatizada inclui testes de:

-   Autenticação, tokens e permissões;
-   Validação de lances e regras de negócio;
-   Concorrência entre lances e consistência das reservas financeiras;
-   Anti-sniping e limites de prorrogação do encerramento;
-   Liquidação de leilões, pagamentos e rollback em caso de falha;
-   Carteira, depósitos, saldos e transações;
-   Auditoria, integridade da cadeia de hashes e checkpoints;
-   Integração com PostgreSQL;
-   Resiliência quando APIs externas falham;
-   Atualização de status de lotes agendados e encerrados.

## Testes relevantes de atualização de status

A execução mais recente confirmou os seguintes testes:

-   `test_expired_scheduled_lot_without_bids_is_closed_on_lot_listing`
    --- aprovado;
-   `test_scheduled_lot_inside_auction_window_becomes_live_on_listing`
    --- aprovado.

Esses testes verificam a atualização do status de lotes agendados
durante a listagem: lotes expirados sem lances são encerrados e lotes
dentro da janela do leilão passam a `live`.

## Verificação de auditoria do anti-sniping

O teste de integração `test_anti_sniping_persists_audit_event` foi
executado com sucesso no PostgreSQL de testes. Ele verifica, através da
API, que:

-   Um lance válido próximo do encerramento é aceito;
-   O encerramento do lote é prorrogado em dois minutos;
-   O evento `LOT_STATUS_CHANGED`, com a descrição
    `Encerramento prorrogado por anti-sniping.`, é persistido no banco;
-   Os dados do evento correspondem ao horário anterior, ao novo horário
    e ao lance;
-   O evento possui hash e a cadeia de auditoria é considerada válida
    por `verify_audit_chain`.

Resultado na suíte completa: aprovado (`PASSED`).

## Ambiente de testes

Os testes de integração usam um PostgreSQL dedicado, separado do banco
da aplicação. A variável `TEST_DATABASE_URL` deve apontar para o banco
de testes autorizado pela validação de `tests/conftest.py`. Não colocar
senhas reais ou credenciais no relatório nem no repositório.

## Observações e conclusão

Na execução de 27/10/2026, todos os **82 testes coletados passaram em
5.14 segundos**, sem falhas nem erros. O resultado representa dois
testes a mais em comparação com o relatório anterior, que registrava 80
testes aprovados.

Isso valida os cenários cobertos pela suíte, mas **não significa 100% de
cobertura de código nem comprova resistência contra toda forma de
adulteração externa**. Os testes automatizados também não substituem a
validação manual dos fluxos completos no navegador.

Antes da entrega, revisar o estado do Git e garantir que arquivos
temporários, backups de JSON, dados de validação e credenciais não sejam
adicionados por engano.
