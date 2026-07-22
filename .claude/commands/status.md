---
description: Resumo do estado do projeto (fases, testes, pendências, próximo passo)
---
Dê um resumo conciso do estado atual do projeto do telescópio Jetson:

1. Leia o índice de `README.md` e o `CHANGELOG.md` para as fases concluídas.
2. Rode `py -3.11 -m pytest -q` e (se `cpp/build` existir) `ctest --test-dir cpp/build` — reporte verdes/vermelhos.
3. Liste as pendências conhecidas (escafolds `Indi*`/`Astap*` a validar no hardware; Fase 3) e **sugira o próximo passo**.

Seja breve e direto. Não implemente nada — só relate.
