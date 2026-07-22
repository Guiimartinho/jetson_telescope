---
description: Cria um adapter de hardware seguindo o padrão Hexagonal + contract test
argument-hint: <port> <nome>   (ex.: Mount OnStep  |  Solver Cedar)
---
Crie um novo **adapter de hardware** para o port **$1** chamado **$2**, seguindo os padrões do projeto
(ver `docs/08-reusar-vs-construir.md` e `docs/11-arquitetura-recomendada.md`):

1. Implemente a classe em `src/control/` (Mount/Focuser/Solver) ou `src/capture/` (Source), herdando o port `$1`.
2. **Import tardio** do SDK/lib de hardware (dentro do `__init__`), para NÃO quebrar o caminho de simulação no PC.
3. **Falhe de forma clara** se a lib/hardware faltar (mensagem útil), com `TODO(bring-up)` onde precisar validar no hardware real. **Não invente a API do SDK.**
4. Adicione teste(s) em `tests/`: no mínimo (a) o contrato do port é respeitado e (b) falha limpo sem hardware (`pytest.raises`).
5. Rode `py -3.11 -m pytest -q` e confirme verde. Atualize o `CHANGELOG.md`.

Mantenha o núcleo e os testes existentes intactos (Ports & Adapters: trocar adapter não muda o resto).
