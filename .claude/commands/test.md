---
description: Roda as duas suítes de teste (pytest + C++/ctest) e resume o resultado
allowed-tools: Bash(py -3.11 -m pytest:*), Bash(ctest:*), Bash(cmake:*)
---
Rode os testes do projeto e me dê um resumo curto (passaram/falharam). Argumentos: $ARGUMENTS

1. **Python:** `py -3.11 -m pytest -q $ARGUMENTS`
2. **C++:** se `cpp/build` existir, `ctest --test-dir cpp/build --output-on-failure`;
   senão configure antes: `cmake -S cpp -B cpp/build -G Ninja -DCMAKE_CXX_COMPILER=g++` e depois `cmake --build cpp/build`.

Se algo falhar, mostre só o essencial (nomes dos testes que falharam + a causa) e proponha a correção. Não altere código sem eu confirmar.
