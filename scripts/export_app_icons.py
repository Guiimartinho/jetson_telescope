#!/usr/bin/env python3
"""Exporta os ícones e o logo do `ui_kit` para o app do celular (app/).

    py -3.11 scripts/export_app_icons.py            # grava
    py -3.11 scripts/export_app_icons.py --check    # só confere (sai com 1 se algo mudou)

Os ícones têm UMA fonte: `src/server/ui_kit.py`. As páginas da Jetson e o app do celular saem
do mesmo desenho; nada em `app/assets/icons` é editado à mão. Gera:

  app/assets/icons/<nome>.svg      um SVG por ícone, com o estilo embutido (o app pinta a cor)
  app/assets/brand/mark.svg        o símbolo do produto
  app/lib/core/icons.g.dart        os nomes, para o Dart não errar um nome de arquivo
  android: mipmap-*/ic_launcher.png   o ícone do app (o mesmo PNG do console), se o projeto existir
  android: drawable/ic_stat_telescope.xml   o símbolo como ícone dos avisos (vetor, uma cor só)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.server import ui_kit as uik                                        # noqa: E402

APP = ROOT / "app"
_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {box}" fill="none" stroke="#000" '
        'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>\n')
_LAUNCHER = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def icon_svg(inner: str) -> str:
    """O ícone como arquivo independente: o que era classe CSS vira atributo. A cor é preta;
    o app aplica a cor do tema por cima."""
    return _SVG.format(box=24, width=1.6, inner=inner.replace('class="f"', 'fill="#000" stroke="none"'))


def mark_svg() -> str:
    inner = uik._MARK_INNER.replace('fill="currentColor"', 'fill="#000"')
    return _SVG.format(box=32, width=1.7, inner=inner)


def notification_icon_xml() -> str:
    """O símbolo do produto como ícone de aviso do Android: um vetor de uma cor só (o sistema
    usa apenas a forma). Cada peça do SVG vira um caminho; o círculo e a elipse, dois arcos."""
    stroke = ('android:strokeColor="#FFFFFFFF" android:strokeWidth="1.7" android:strokeLineCap="round" '
              'android:strokeLineJoin="round" android:fillColor="#00000000"')
    body = []
    for tag, attrs in re.findall(r"<(circle|ellipse|path)\b([^>]*)/>", uik._MARK_INNER):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        paint = 'android:fillColor="#FFFFFFFF"' if a.get("fill") == "currentColor" else stroke
        if tag == "path":
            data = a["d"]
        else:
            cx, cy = float(a["cx"]), float(a["cy"])
            rx, ry = float(a.get("rx", a.get("r"))), float(a.get("ry", a.get("r")))
            data = (f"M{cx - rx:g},{cy:g}a{rx:g},{ry:g} 0 1,0 {2 * rx:g},0"
                    f"a{rx:g},{ry:g} 0 1,0 {-2 * rx:g},0z")
        path = f'<path android:pathData="{data}" {paint}/>'
        turn = re.fullmatch(r"rotate\(([-\d.]+) ([\d.]+) ([\d.]+)\)", a.get("transform", ""))
        if turn:
            path = (f'<group android:rotation="{turn[1]}" android:pivotX="{turn[2]}" '
                    f'android:pivotY="{turn[3]}">{path}</group>')
        body.append("    " + path)
    head = ['<?xml version="1.0" encoding="utf-8"?>',
            "<!-- GERADO por scripts/export_app_icons.py a partir de src/server/ui_kit.py. Não edite. -->",
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
            '    android:width="24dp" android:height="24dp"',
            '    android:viewportWidth="32" android:viewportHeight="32">']
    return "\n".join(head + body + ["</vector>", ""])


def dart_names(names) -> str:
    lines = ["// GERADO por scripts/export_app_icons.py a partir de src/server/ui_kit.py.",
             "// Não edite: mude o desenho no ui_kit e rode o script.",
             "", "/// Nomes dos ícones do produto (arquivos em `assets/icons/<nome>.svg`).",
             "abstract final class AppIcons {"]
    lines += [f"  static const {n} = '{n}';" for n in names]
    # um nome por linha, com vírgula no fim: é como o `dart format` deixa, então formatar o
    # projeto não mexe neste arquivo
    lines += ["", "  static const all = <String>["] + [f"    {n}," for n in names] + ["  ];", "}", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, bytes]:
    names = sorted(uik._IC)
    out = {APP / "assets" / "icons" / f"{n}.svg": icon_svg(uik._IC[n]).encode("utf-8") for n in names}
    out[APP / "assets" / "brand" / "mark.svg"] = mark_svg().encode("utf-8")
    out[APP / "lib" / "core" / "icons.g.dart"] = dart_names(names).encode("utf-8")
    res = APP / "android" / "app" / "src" / "main" / "res"
    if res.exists():
        for density, size in _LAUNCHER.items():
            out[res / f"mipmap-{density}" / "ic_launcher.png"] = uik.app_icon_png(size)
        out[res / "drawable" / "ic_stat_telescope.xml"] = notification_icon_xml().encode("utf-8")
    return out


def same(path: Path, data: bytes) -> bool:
    """O arquivo no disco é o que o gerador produziria? Texto, byte a byte. PNG, pelo desenho:
    o compressor muda de um sistema para outro (os bytes diferem com a imagem idêntica), e uma
    borda suavizada pode variar um nível de cinza."""
    if not path.exists():
        return False
    current = path.read_bytes()
    if current == data:
        return True
    if path.suffix.lower() != ".png":
        return False
    import cv2
    import numpy as np
    a = cv2.imdecode(np.frombuffer(current, np.uint8), cv2.IMREAD_UNCHANGED)
    b = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if a is None or b is None or a.shape != b.shape:
        return False
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max()) <= 3


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="não grava; falha se algo estiver desatualizado")
    a = ap.parse_args(argv)
    stale = []
    for path, data in outputs().items():
        if same(path, data):
            continue
        stale.append(path)
        if not a.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    extra = [p for p in (APP / "assets" / "icons").glob("*.svg") if p.stem not in uik._IC]
    for p in extra:
        stale.append(p)
        if not a.check:
            p.unlink()
    verb = "desatualizado" if a.check else "gravado"
    for p in stale:
        print(f"{verb}: {p.relative_to(ROOT)}")
    print(f"{len(uik._IC)} ícones; {len(stale)} arquivo(s) {verb}(s)")
    return 1 if (a.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
