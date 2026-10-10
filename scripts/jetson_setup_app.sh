#!/usr/bin/env bash
# Deixa o console da Jetson com cara de app, sem ninguém digitar IP nem porta:
#   1. apelido na rede: http://telescopio.local (a máquina NÃO muda de nome);
#   2. console também na porta 80 (a 8080 continua) e canal em tempo real na 8081.
# O manifesto e os ícones para a tela inicial já são servidos pelo próprio console.
# Idempotente. Ver docs/33.
#
# Uso (na Jetson):  sudo bash scripts/jetson_setup_app.sh
# Desfazer:  sudo systemctl disable --now telescope-mdns
#            sudo rm /etc/systemd/system/telescope-mdns.service
#            sudo rm /etc/systemd/system/telescope-console.service.d/app.conf
#            sudo systemctl daemon-reload && sudo systemctl restart telescope-console
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: precisa de root (sudo bash $0)." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OWNER="${SUDO_USER:-$(id -un)}"

if ! systemctl is-active --quiet avahi-daemon; then
  echo "ERRO: avahi-daemon não está ativo (sudo apt install avahi-daemon)." >&2
  exit 1
fi
if ! sudo -u "$OWNER" python3 -c "import dbus" 2>/dev/null; then
  echo "ERRO: python3-dbus ausente (sudo apt install python3-dbus)." >&2
  exit 1
fi
if ! sudo -u "$OWNER" python3 -c "import websockets.sync.server" 2>/dev/null; then
  echo "AVISO: 'websockets' ausente — sem canal em tempo real (pip3 install --user websockets)."
fi

# 1. apelido mDNS
sed -e "s|__USER__|$OWNER|g" -e "s|__REPO__|$REPO|g" \
    "$REPO/deploy/jetson/telescope-mdns.service" > /etc/systemd/system/telescope-mdns.service
chmod 0644 /etc/systemd/system/telescope-mdns.service

# 2. console na porta 80
install -D -m 0644 "$REPO/deploy/jetson/telescope-console.app.conf" \
    /etc/systemd/system/telescope-console.service.d/app.conf

systemctl daemon-reload
systemctl enable --now telescope-mdns.service >/dev/null 2>&1
systemctl restart telescope-mdns.service telescope-console.service
sleep 3
echo ">> telescope-mdns:    $(systemctl is-active telescope-mdns.service || true)"
echo ">> telescope-console: $(systemctl is-active telescope-console.service || true)"
echo ">> abra no celular:   http://telescopio.local"
