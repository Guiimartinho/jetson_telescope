#!/usr/bin/env bash
# Compila e instala o módulo `ch341` (ponte USB-serial CH340/CH341) para o kernel da Jetson.
#
# Por quê: o kernel do JetPack 6 vem com CONFIG_USB_SERIAL_CH341 desligado. A controladora
# da montagem (FYSETC E4, ponte CH340, USB 1a86:7523) aparece no `lsusb`, mas não vira
# /dev/ttyUSB* — e é por essa serial que o indi_lx200_OnStep conversa com o OnStepX.
# O módulo é o driver do próprio kernel mainline, na versão EXATA do kernel em execução,
# compilado fora da árvore contra os headers que o JetPack já instala. Ver docs/34.
#
# Segunda armadilha (Ubuntu 22.04): a regra udev do `brltty` (leitor braille) reivindica o
# ID 1a86:7523 e derruba o ttyUSB0 segundos depois de ele aparecer. A regra é mascarada.
#
# Uso (na Jetson):  bash scripts/jetson_install_ch341.sh            # compila e instala
#                   bash scripts/jetson_install_ch341.sh build      # só compila (sem root)
#                   sudo bash scripts/jetson_install_ch341.sh install
# Refazer depois de atualizar o kernel (apt upgrade do nvidia-l4t-kernel): rodar de novo.
# Desfazer:  sudo rm /lib/modules/$(uname -r)/updates/ch341.ko && sudo depmod -a
#            sudo rm /etc/udev/rules.d/85-brltty.rules && sudo udevadm control --reload-rules
set -euo pipefail

KVER="$(uname -r)"                        # ex.: 5.15.185-tegra
KBASE="${KVER%%-*}"                       # ex.: 5.15.185 -> tag v5.15.185 do kernel.org
KBUILD="/lib/modules/${KVER}/build"
OWNER="${SUDO_USER:-$(id -un)}"           # sob sudo, o build fica no home de quem chamou
WORK="$(getent passwd "$OWNER" | cut -d: -f6)/.cache/telescope/ch341-${KVER}"
SRC_URL="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/drivers/usb/serial/ch341.c?h=v${KBASE}"
BRLTTY_RULE="/usr/lib/udev/rules.d/85-brltty.rules"

build() {
  if [ ! -d "$KBUILD" ]; then
    echo "ERRO: headers do kernel ausentes em $KBUILD (sudo apt install nvidia-l4t-kernel-headers)." >&2
    exit 1
  fi
  rm -rf "$WORK"
  mkdir -p "$WORK"
  echo ">> baixando ch341.c do kernel v${KBASE}"
  curl -fsSL --max-time 60 "$SRC_URL" -o "$WORK/ch341.c"
  if ! grep -q 'USB_DEVICE(0x1a86, 0x7523)' "$WORK/ch341.c"; then
    echo "ERRO: o arquivo baixado não é o driver ch341 esperado." >&2
    exit 1
  fi
  echo 'obj-m := ch341.o' > "$WORK/Makefile"
  echo ">> compilando contra $KBUILD"
  make -C "$KBUILD" M="$WORK" modules
  echo ">> ok: $WORK/ch341.ko [$(modinfo -F vermagic "$WORK/ch341.ko")]"
}

install_mod() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "ERRO: a etapa install precisa de root (sudo)." >&2
    exit 1
  fi
  if [ ! -f "$WORK/ch341.ko" ]; then
    echo "ERRO: $WORK/ch341.ko não existe — rode a etapa build antes." >&2
    exit 1
  fi
  install -D -m 0644 "$WORK/ch341.ko" "/lib/modules/${KVER}/updates/ch341.ko"
  depmod -a
  if grep -qs '1a86/7523' "$BRLTTY_RULE"; then
    ln -sfn /dev/null /etc/udev/rules.d/85-brltty.rules   # mesmo nome em /etc vence o de /usr/lib
    udevadm control --reload-rules
    echo ">> regra udev do brltty mascarada (ela sequestrava o CH340)"
  fi
  modprobe ch341
  echo ">> ch341 carregado [$(modinfo -F vermagic ch341)]"
}

case "${1:-all}" in
  build)   build ;;
  install) install_mod ;;
  all)     build; sudo bash "$0" install ;;
  *)       echo "uso: $0 [build|install]" >&2; exit 2 ;;
esac
