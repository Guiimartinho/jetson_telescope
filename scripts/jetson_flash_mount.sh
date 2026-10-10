#!/usr/bin/env bash
# Grava o firmware da controladora A PARTIR DA JETSON, pelo mesmo cabo USB do link.
#
# A placa não precisa voltar ao PC: o PC compila (ESP-IDF), os 4 binários são copiados para
# a Jetson, e ela grava com o esptool. O telescope-indi.service é parado durante a gravação
# (o driver INDI segura a porta) e religado no fim; o link do console reconecta sozinho.
#
# Uso (na Jetson):  sudo bash scripts/jetson_flash_mount.sh <pasta_dos_bins> [opções]
#   <pasta_dos_bins>      bootloader.bin  partition-table.bin  ota_data_initial.bin  onstepx_telescope.bin
#   --erase               apaga a flash antes (necessário para trocar a senha do WiFi: fica na NVS)
#   --keep-indi-stopped   não religa o INDI no fim (para ler o log de boot: scripts/mount_bootlog.py)
# Pré-requisito:  pip3 install --user esptool
set -euo pipefail

DIR="${1:?uso: sudo bash $0 <pasta_dos_bins> [--erase] [--keep-indi-stopped]}"
ERASE=0
KEEP_STOPPED=0
for a in "${@:2}"; do
  case "$a" in
    --erase)             ERASE=1 ;;
    --keep-indi-stopped) KEEP_STOPPED=1 ;;
    *) echo "opção desconhecida: $a" >&2; exit 2 ;;
  esac
done

PORT=/dev/telescope-mount
OWNER="${SUDO_USER:-$(id -un)}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: precisa de root (para parar e religar o serviço INDI)." >&2
  exit 1
fi
if [ ! -e "$PORT" ]; then
  echo "ERRO: $PORT não existe — a placa está plugada e ligada na fonte?" >&2
  exit 1
fi
for f in bootloader.bin partition-table.bin ota_data_initial.bin onstepx_telescope.bin; do
  if [ ! -f "$DIR/$f" ]; then
    echo "ERRO: falta $DIR/$f" >&2
    exit 1
  fi
done
if ! sudo -u "$OWNER" python3 -c "import esptool" 2>/dev/null; then
  echo "ERRO: esptool ausente para o usuário $OWNER (pip3 install --user esptool)." >&2
  exit 1
fi
ESPTOOL=(sudo -u "$OWNER" python3 -m esptool --chip esp32 --port "$PORT" --baud 460800)

systemctl stop telescope-indi.service
restore() {                                   # religa mesmo se a gravação falhar no meio
  if [ "$KEEP_STOPPED" -eq 0 ]; then
    systemctl start telescope-indi.service
  fi
}
trap restore EXIT

if [ "$ERASE" -eq 1 ]; then
  "${ESPTOOL[@]}" erase-flash
fi
# mesmos endereços e parâmetros do build (firmware/build/flash_args)
"${ESPTOOL[@]}" --before default-reset --after hard-reset write-flash \
    --flash-mode dio --flash-size 16MB --flash-freq 80m \
    0x1000  "$DIR/bootloader.bin" \
    0x8000  "$DIR/partition-table.bin" \
    0xe000  "$DIR/ota_data_initial.bin" \
    0x10000 "$DIR/onstepx_telescope.bin"
echo ">> gravado; a placa reiniciou."
