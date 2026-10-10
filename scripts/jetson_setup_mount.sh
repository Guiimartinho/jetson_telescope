#!/usr/bin/env bash
# Deixa a Jetson pronta para a controladora da montagem, sem passo manual depois:
#   1. módulo ch341 (o kernel do JetPack 6 não traz) — scripts/jetson_install_ch341.sh;
#   2. regra udev: /dev/telescope-mount em QUALQUER porta USB;
#   3. telescope-indi.service: o INDI sobe quando a placa aparece e cai quando ela sai;
#   4. telescope-console: passa a usar a montagem real (TELE_MOUNT=indi).
# Idempotente. Ver docs/35.
#
# Uso (na Jetson):  sudo bash scripts/jetson_setup_mount.sh
# Desfazer:  sudo systemctl stop telescope-indi
#            sudo rm /etc/udev/rules.d/99-telescope-mount.rules /etc/systemd/system/telescope-indi.service
#            sudo rm /etc/systemd/system/telescope-console.service.d/mount.conf
#            sudo systemctl daemon-reload && sudo udevadm control --reload-rules
#            sudo systemctl restart telescope-console
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: precisa de root (sudo bash $0)." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OWNER="${SUDO_USER:-$(id -un)}"
OWNER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"

if ! command -v indiserver >/dev/null 2>&1 || [ ! -x /usr/bin/indi_lx200_OnStep ]; then
  echo "ERRO: INDI ausente (sudo apt install indi-bin)." >&2
  exit 1
fi

# 1. driver da ponte CH340
if ! modinfo ch341 >/dev/null 2>&1; then
  echo ">> módulo ch341 ausente: compilando"
  sudo -u "$OWNER" bash "$HERE/jetson_install_ch341.sh" build
  bash "$HERE/jetson_install_ch341.sh" install
fi

# 2 e 3. nome fixo + serviço amarrado ao dispositivo
install -m 0644 "$REPO/deploy/jetson/99-telescope-mount.rules" /etc/udev/rules.d/99-telescope-mount.rules
sed -e "s|__USER__|$OWNER|g" -e "s|__HOME__|$OWNER_HOME|g" \
    "$REPO/deploy/jetson/telescope-indi.service" > /etc/systemd/system/telescope-indi.service
chmod 0644 /etc/systemd/system/telescope-indi.service

# 4. o console passa a usar a montagem real (link automático: conecta, envia hora/local, reconecta)
if [ -f /etc/systemd/system/telescope-console.service ]; then
  install -D -m 0644 "$REPO/deploy/jetson/telescope-console.mount.conf" \
      /etc/systemd/system/telescope-console.service.d/mount.conf
  RESTART_CONSOLE=1
fi
systemctl daemon-reload
[ "${RESTART_CONSOLE:-0}" = 1 ] && systemctl restart telescope-console.service
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty --action=add    # aplica à placa que já estiver plugada
udevadm settle

if [ -e /dev/telescope-mount ]; then
  echo ">> placa presente: /dev/telescope-mount -> $(readlink -f /dev/telescope-mount)"
  sleep 2
  echo ">> telescope-indi.service: $(systemctl is-active telescope-indi.service || true)"
else
  echo ">> regra e serviço instalados; a placa não está plugada agora (sobem quando plugar)."
fi
