#!/usr/bin/env python3
"""Baixa o OnStepX (pinado), instala a NOSSA Config.h e aplica os patches necessários.

Por que não versionar o OnStepX aqui: são 432 arquivos / ~66k linhas de terceiro. Pinamos
um commit (reprodutível) e mantemos no repositório só o que é decisão nossa: a Config e os
patches. Ver docs/35.

    py -3.11 firmware/scripts/fetch_onstepx.py            # baixa + configura
    py -3.11 firmware/scripts/fetch_onstepx.py --check    # só verifica (não altera nada)
"""
from __future__ import annotations
import argparse
import os
import secrets
import shutil
import subprocess
import sys

REPO = "https://github.com/hjd1964/OnStepX.git"
# Pinado: OnStepX 10.28x. Trocar conscientemente (e rodar os testes) ao atualizar.
PIN = "65a751825677a03a0b12b15546780b614a206435"

# Dependência EXTERNA do OnStepX: o driver dos TMC2209 não vem embutido — o código faz
# `#include <TMC2209.h>` e no Arduino IDE você instalaria pelo Library Manager. Aqui ela
# vira um componente do IDF (firmware/components/tmc2209/).
TMC_REPO = "https://github.com/hjd1964/TMC2209.git"

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
DEST = os.path.join(FW, "components", "onstepx", "onstepx-src")
TMC_DEST = os.path.join(FW, "components", "tmc2209", "tmc2209-src")
OUR_CONFIG = os.path.join(FW, "config", "Config.telescope.h")
# Segredos locais (senha do AP): incluído pela Config, NUNCA versionado (firmware/.gitignore).
OUR_LOCAL = os.path.join(FW, "config", "Config.local.h")

LOCAL_TEMPLATE = """\
// Segredos LOCAIS do firmware — este arquivo NAO e versionado (firmware/.gitignore).
// Gerado por scripts/fetch_onstepx.py na primeira vez; edite a vontade, ele nunca e
// sobrescrito. Depois de editar, rode o fetch de novo e regrave a placa COM erase-flash
// (o OnStepX guarda a senha na NVS no primeiro boot e ignoraria a nova).
#pragma once

// Senha do WiFi proprio da placa (ponto de acesso). WPA2: de 8 a 63 caracteres.
#define AP_PASSWORD "{senha}"
"""

PINMAP = os.path.join("src", "pinmaps", "Pins.FYSETC_E4.h")

# --- Patch da UART dos TMC ------------------------------------------------------------
# O pinmap define SERIAL_TMC_TX sem guarda, então o valor do pinmap (GPIO15 = Z-MIN)
# sobrescreveria o nosso (GPIO22, a fiação real da placa). Adicionamos a guarda `#ifndef`,
# exatamente como o próprio pinmap já faz para SERIAL_TMC_RX. Ver docs/35.
PATCH_OLD = """    #define SERIAL_TMC_TX       15               // Transmit data (Z-MIN)"""
PATCH_NEW = """    #ifndef SERIAL_TMC_TX
      #define SERIAL_TMC_TX     15               // Transmit data (Z-MIN)
    #endif"""


def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def fetch(force: bool = False) -> None:
    if os.path.isdir(DEST):
        if not force:
            print(f"[fetch] ja existe: {DEST} (use --force para rebaixar)")
            return
        shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    print(f"[fetch] clonando OnStepX @ {PIN[:10]} ...")
    _run(["git", "clone", "--quiet", REPO, DEST])
    _run(["git", "-c", "advice.detachedHead=false", "checkout", "--quiet", PIN], cwd=DEST)
    print(f"[fetch] OK -> {DEST}")


def fetch_tmc2209(force: bool = False) -> None:
    """Baixa a biblioteca Arduino TMC2209 (dependência externa do OnStepX)."""
    if os.path.isdir(TMC_DEST):
        if not force:
            print("[tmc]   ja existe (use --force para rebaixar)")
            return
        shutil.rmtree(TMC_DEST, ignore_errors=True)
    os.makedirs(os.path.dirname(TMC_DEST), exist_ok=True)
    print("[tmc]   clonando biblioteca TMC2209 ...")
    _run(["git", "clone", "--quiet", "--depth", "1", TMC_REPO, TMC_DEST])
    print(f"[tmc]   OK -> {TMC_DEST}")


def _nova_senha() -> str:
    """Senha aleatória digitável no celular: três grupos, sem l/1/i/o/0."""
    alfabeto = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(3))


def ensure_local_config(path: str = OUR_LOCAL) -> bool:
    """Garante o arquivo de segredos local. Devolve True se criou, False se já existia.

    Nunca sobrescreve: a senha que o usuário escolher sobrevive a qualquer novo fetch."""
    if os.path.isfile(path):
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(LOCAL_TEMPLATE.format(senha=_nova_senha()))
    return True


def install_config() -> None:
    """Instala a nossa Config.h na raiz da árvore (src/Common.h faz #include "../Config.h"),
    junto com o arquivo de segredos local que ela inclui."""
    dst = os.path.join(DEST, "Config.h")
    shutil.copyfile(OUR_CONFIG, dst)
    print(f"[config] instalado {os.path.basename(OUR_CONFIG)} -> Config.h")
    if ensure_local_config():
        print(f"[config] GERADO {OUR_LOCAL} com uma senha de AP aleatoria (fora do git) — "
              "abra o arquivo para ver ou trocar")
    shutil.copyfile(OUR_LOCAL, os.path.join(DEST, "Config.local.h"))
    print("[config] instalado Config.local.h (segredos locais)")


def make_ino_compilable() -> None:
    """O CMake não reconhece .ino; o OnStepX.ino é C++ comum (161 linhas) → copia como .cpp."""
    src = os.path.join(DEST, "OnStepX.ino")
    dst = os.path.join(DEST, "OnStepX.ino.cpp")
    shutil.copyfile(src, dst)
    print("[ino] OnStepX.ino -> OnStepX.ino.cpp (compilavel pelo CMake)")


def patch_tmc_uart(check_only: bool = False) -> bool:
    """Torna SERIAL_TMC_TX sobrescrevível. Devolve True se o patch está aplicado."""
    path = os.path.join(DEST, PINMAP)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if PATCH_NEW in text:
        print("[patch] UART dos TMC: ja aplicado")
        return True
    if PATCH_OLD not in text:
        print("[patch] ERRO: nao achei o trecho esperado no pinmap — o OnStepX mudou?\n"
              f"        confira {PINMAP} e atualize PATCH_OLD/PATCH_NEW.", file=sys.stderr)
        return False
    if check_only:
        print("[patch] UART dos TMC: PENDENTE")
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(PATCH_OLD, PATCH_NEW, 1))
    print("[patch] UART dos TMC: aplicado (SERIAL_TMC_TX agora respeita a Config)")
    return True


def check() -> int:
    """Verifica sem alterar: árvore presente, Config instalada, patch aplicado."""
    problems = []
    if not os.path.isfile(os.path.join(DEST, "OnStepX.ino")):
        problems.append("arvore do OnStepX ausente (rode sem --check)")
    if not os.path.isfile(os.path.join(TMC_DEST, "src", "TMC2209.cpp")):
        problems.append("biblioteca TMC2209 ausente")
    else:
        if not os.path.isfile(os.path.join(DEST, "Config.h")):
            problems.append("Config.h nao instalada")
        if not os.path.isfile(os.path.join(DEST, "Config.local.h")):
            problems.append("Config.local.h (segredos locais) nao instalada")
        if not os.path.isfile(os.path.join(DEST, "OnStepX.ino.cpp")):
            problems.append("OnStepX.ino.cpp ausente")
        if not patch_tmc_uart(check_only=True):
            problems.append("patch da UART dos TMC nao aplicado")
    for p in problems:
        print(f"  FALTA: {p}")
    print("OK — arvore pronta para o build" if not problems else "INCOMPLETO")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara a arvore do OnStepX para o build IDF")
    ap.add_argument("--check", action="store_true", help="só verifica, não altera")
    ap.add_argument("--force", action="store_true", help="rebaixa mesmo se já existir")
    ap.add_argument("--prune-tier", type=int, default=0, metavar="N",
                    help="poda a árvore até a camada N (0 = não podar). Ver prune_onstepx.py")
    a = ap.parse_args()

    if a.check:
        return check()

    fetch(force=a.force)
    fetch_tmc2209(force=a.force)
    install_config()
    make_ino_compilable()
    if not patch_tmc_uart():
        return 1
    if a.prune_tier:
        # a poda entra DEPOIS do patch: ela mexe em pinmaps, o patch mexe no nosso pinmap
        print()
        sys.path.insert(0, HERE)
        import prune_onstepx
        if prune_onstepx.podar(ate_tier=a.prune_tier) != 0:
            return 1
    print("\nPronto. Agora:")
    print("  cd firmware && idf.py set-target esp32 && idf.py build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
