#!/usr/bin/env bash
# Sobe o indiserver com os drivers SIMULADORES (sem hardware) para validar a camada INDI.
# Uso (WSL/Linux/Jetson):  bash scripts/run_indi_sim.sh
# Depois, do Windows/WSL:  INDI_HOST=127.0.0.1 py -3.11 -m pytest tests/test_indi_integration.py -m hardware -v
#
# Instalar o INDI antes (Ubuntu/WSL/Jetson):
#   sudo apt-add-repository ppa:mutlaqja/ppa -y   # (Ubuntu; na Jetson use os pacotes do JetPack/INDI)
#   sudo apt update && sudo apt install -y indi-bin
set -euo pipefail

if ! command -v indiserver >/dev/null 2>&1; then
  echo "ERRO: indiserver não encontrado. Instale o INDI (ex.: sudo apt install indi-bin)." >&2
  exit 1
fi

DRIVERS=(
  indi_simulator_telescope   # Telescope Simulator  (EQUATORIAL_EOD_COORD)
  indi_simulator_focus       # Focuser Simulator    (ABS_FOCUS_POSITION)
  indi_simulator_wheel       # Filter Simulator     (FILTER_SLOT/FILTER_NAME)
  indi_simulator_ccd         # CCD Simulator        (CCD_EXPOSURE -> BLOB FITS)
)

echo ">> indiserver na porta 7624 com: ${DRIVERS[*]}"
echo ">> Ctrl+C para parar."
exec indiserver -v "${DRIVERS[@]}"
