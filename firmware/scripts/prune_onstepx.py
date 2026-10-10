#!/usr/bin/env python3
"""Poda a árvore do OnStepX, deixando só o que é alcançável na FYSETC E4 v1.0 / ESP32.

O OnStepX suporta dezenas de placas e cinco famílias de MCU. Nada disso é alcançável no
nosso alvo — são `#if defined(...)` que nunca fecham. Remover esse peso torna a árvore
legível (pré-requisito para migrar aos poucos para IDF nativo), encurta o build e diminui
a superfície onde um erro pode se esconder.

A poda é **declarativa e em CAMADAS**, do provável-seguro ao mais invasivo:

    1  plataformas e placas       inalcançáveis por #ifdef — remoção segura por construção
    2  periféricos que não temos  desligados pela nossa Config (encoder, CAN, ethernet...)
    3  backends alternativos      variantes de armazenamento e fonte de tempo

Cada camada é aplicada e o build reconstruído. Nunca pule para a 3 sem a 1 e a 2 verdes.

    py -3.11 firmware/scripts/prune_onstepx.py            # camada 1 (padrão)
    py -3.11 firmware/scripts/prune_onstepx.py --tier 2   # camadas 1 e 2
    py -3.11 firmware/scripts/prune_onstepx.py --dry-run  # só mostra o que sairia
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
TREE = os.path.join(FW, "components", "onstepx", "onstepx-src")

# Nunca remover, aconteça o que acontecer. Rede de segurança contra um glob mal escrito.
PROTEGIDO = {
    "OnStepX.ino", "OnStepX.ino.cpp", "Config.h", "Extended.config.h",
    os.path.join("src", "HAL", "esp"),
    os.path.join("src", "HAL", "default"),
    os.path.join("src", "pinmaps", "Pins.FYSETC_E4.h"),
    os.path.join("src", "pinmaps", "Pins.defaults.h"),
    os.path.join("src", "pinmaps", "Models.h"),
    os.path.join("src", "pinmaps", "Validate.h"),
}

CAMADAS = {
    1: {
        "nome": "plataformas e placas que não são a nossa",
        "porque": "HAL/HAL.h escolhe a família de MCU por #if defined(...); com ESP32 + "
                  "arduino-esp32 3.x cai em esp/ESP32Libraries3.h. Os outros diretórios "
                  "são inalcançáveis. Idem para os pinmaps: PINMAP=FYSETC_E4.",
        "dirs": [
            "src/HAL/arduinoM0", "src/HAL/atmel", "src/HAL/mbed",
            "src/HAL/stm32", "src/HAL/teensy",
        ],
        # todos os Pins.*.h menos os protegidos
        "glob_dir": "src/pinmaps",
        "glob_prefixo": "Pins.",
    },
    2: {
        "nome": "periféricos que este telescópio não tem",
        "porque": "desligados pela nossa Config: sem encoders, sem CAN, sem expansor de "
                  "GPIO, sem ethernet cabeada (o link é WiFi) e sem Bluetooth.",
        "dirs": [
            "src/lib/encoder", "src/lib/canPlus", "src/lib/canTransport",
            "src/lib/gpioEx", "src/lib/ethernet", "src/lib/bluetooth",
        ],
    },
    3: {
        "nome": "backends alternativos de armazenamento e tempo",
        "porque": "TIME_LOCATION_SOURCE=OFF (hora e local vêm da Jetson por INDI) e o "
                  "ESP32 usa o backend NVS próprio. ATENÇÃO: mais invasivo — só depois "
                  "das camadas 1 e 2 com build verde.",
        "dirs": ["src/lib/tls", "src/lib/calendars"],
    },
}


def _stats(raiz):
    arq = linhas = 0
    for d, _sub, files in os.walk(raiz):
        for f in files:
            if f.endswith((".h", ".cpp", ".ino")):
                arq += 1
                try:
                    with open(os.path.join(d, f), "rb") as fh:
                        linhas += fh.read().count(b"\n")
                except OSError:
                    pass
    return arq, linhas


def _protegido(rel):
    rel = rel.replace("/", os.sep)
    return any(rel == p or rel.startswith(p + os.sep) for p in PROTEGIDO)


def _alvos(tier):
    """Lista de caminhos relativos a remover para uma camada."""
    c = CAMADAS[tier]
    out = []
    for d in c.get("dirs", []):
        if os.path.isdir(os.path.join(TREE, d.replace("/", os.sep))) and not _protegido(d):
            out.append(d)
    gd = c.get("glob_dir")
    if gd:
        full = os.path.join(TREE, gd.replace("/", os.sep))
        for f in sorted(os.listdir(full)) if os.path.isdir(full) else []:
            rel = f"{gd}/{f}"
            if f.startswith(c["glob_prefixo"]) and not _protegido(rel):
                out.append(rel)
    return out


def podar(ate_tier=1, dry_run=False):
    if not os.path.isdir(TREE):
        print(f"ERRO: arvore ausente em {TREE}\n"
              "      rode antes: py -3.11 firmware/scripts/fetch_onstepx.py", file=sys.stderr)
        return 1

    arq0, lin0 = _stats(TREE)
    print(f"antes:  {arq0} arquivos, {lin0} linhas\n")
    total = 0
    for tier in range(1, ate_tier + 1):
        c = CAMADAS[tier]
        alvos = _alvos(tier)
        print(f"[camada {tier}] {c['nome']}")
        print(f"            {c['porque']}")
        if not alvos:
            print("            (nada a remover — ja podado)\n")
            continue
        for rel in alvos:
            caminho = os.path.join(TREE, rel.replace("/", os.sep))
            marca = "removeria" if dry_run else "removido "
            print(f"            {marca} {rel}")
            if not dry_run:
                if os.path.isdir(caminho):
                    shutil.rmtree(caminho, ignore_errors=True)
                else:
                    os.remove(caminho)
            total += 1
        print()

    if dry_run:
        print(f"(dry-run) {total} itens seriam removidos — nada foi alterado")
        return 0

    arq1, lin1 = _stats(TREE)
    print(f"depois: {arq1} arquivos, {lin1} linhas")
    print(f"poda:   -{arq0 - arq1} arquivos, -{lin0 - lin1} linhas "
          f"({100.0 * (lin0 - lin1) / max(lin0, 1):.1f}% menor)")
    print("\nReconstrua e confirme que segue verde:  cd firmware && idf.py build")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Poda o OnStepX para a FYSETC E4 / ESP32")
    ap.add_argument("--tier", type=int, default=1, choices=sorted(CAMADAS),
                    help="aplica as camadas 1..N (padrao: 1)")
    ap.add_argument("--dry-run", action="store_true", help="mostra sem remover")
    a = ap.parse_args()
    return podar(ate_tier=a.tier, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
