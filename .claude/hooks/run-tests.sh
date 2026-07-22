#!/usr/bin/env bash
# Hook de Stop: roda o pytest SÓ quando código Python mudou desde a última execução.
# - verde ou sem mudanças  -> exit 0 (silencioso)
# - falhou                 -> exit 2 + saída do erro -> acorda o Claude para corrigir
# Roda em background (asyncRewake), então não bloqueia você. Ver docs/10.
M=".claude/.last-test"

# Nada mudou desde o último teste? sai rápido.
if [ -f "$M" ] && [ -z "$(find src tests -name '*.py' -newer "$M" 2>/dev/null)" ]; then
  exit 0
fi

out="$(py -3.11 -m pytest -q 2>&1)"; rc=$?
touch "$M"

if [ "$rc" -ne 0 ]; then
  echo "pytest FALHOU após mudança em src/ ou tests/ — corrija antes de finalizar:"
  echo "$out" | tail -30
  exit 2
fi
exit 0
