
# Procedimento Manual de Checkpoint de Auditoria

## 1. Objetivo

O checkpoint registra uma referência do estado da cadeia de auditoria e complementa a verificação dos hashes, permitindo detectar divergências em relação ao estado previamente registrado.

## 2. Limitações

O checkpoint atual é armazenado em um arquivo JSON local. Ele não oferece proteção absoluta contra alguém que consiga modificar tanto o banco quanto o arquivo.

Para produção, recomenda-se armazenamento independente e protegido, controle de acesso e monitoramento de alterações.

## 3. Verificação antes da atualização

Antes de criar ou atualizar um checkpoint:

1. Confirme o ambiente e o banco de dados utilizados.
2. Verifique a integridade da cadeia de hashes.
3. Investigue inconsistências antes de prosseguir.
4. Revise as operações legítimas realizadas desde o checkpoint anterior.
5. Registre a justificativa e a autorização para a atualização.

Uma cadeia matematicamente íntegra não prova, por si só, que todas as operações foram legítimas.

## 4. Criação inicial

O script `create_audit_checkpoint.py` utiliza a variável `TEST_DATABASE_URL` e valida o destino autorizado:

- Host: `localhost` ou `127.0.0.1`
- Porta: `5433`
- Banco: `verzel_test`
- Usuário: `verzel_test`

Comando:

```bash
PYTHONPATH=. python create_audit_checkpoint.py
```

Se o checkpoint já existir, a criação será recusada por padrão.

## 5. Atualização manual

A atualização exige autorização explícita e confirmação de revisão:

```bash
PYTHONPATH=. python create_audit_checkpoint.py --update --confirm-reviewed
```

Execute somente após revisar as alterações e investigar possíveis divergências. A opção confirma a revisão humana, mas não verifica automaticamente a legitimidade de cada operação.

## 6. Verificação pela API pública

A rota pública consulta a cadeia de hashes e o checkpoint. Se o checkpoint estiver ausente, inválido ou divergente, a API deve indicar que a integridade não foi confirmada.

A rota pública não deve criar nem atualizar o checkpoint.

## 7. Testes

Testes específicos:

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_service.py tests/test_audit_checkpoint.py tests/test_audit_routes.py
```

Suíte completa:

```bash
PYTHONPATH=. python -m pytest -q
```

## 8. Produção

Não utilize este procedimento de testes para registrar checkpoints do Supabase.

Antes da implantação, defina armazenamento independente e protegido, autorização administrativa real, trilha de aprovação e monitoramento de alterações.
