"""Mosaico multi-painel — divide um alvo grande (tipo Andrômeda) numa grade e captura
cada painel autonomamente, depois costura. Compõe o agendador; cada painel vira um alvo.

CONSTRUIR: planejamento da grade + captura por painel (reusa `Scheduler`).
REUSAR:    **Siril headless** para costurar os painéis usando o WCS de cada FITS.
Ver docs/16-mosaico.md.
"""
from __future__ import annotations
import os
import shutil
import subprocess

from .scheduler import Scheduler, Target


def panel_centers(cx, cy, rows, cols, step_px):
    """Centros dos painéis (coords de mundo) numa grade rows×cols centrada em (cx,cy)."""
    panels = []
    for r in range(rows):
        for c in range(cols):
            px = cx + (c - (cols - 1) / 2.0) * step_px
            py = cy + (r - (rows - 1) / 2.0) * step_px
            panels.append((f"R{r}C{c}", (px, py)))
    return panels


def panel_grid_radec(ra_deg, dec_deg, rows, cols, fov_deg, overlap=0.15):
    """A grade no CÉU: centro (RA/DEC, graus) de cada painel de um mosaico `rows`×`cols` sobre
    o alvo, com `overlap` (fração do campo) de sobreposição entre vizinhos — é ela que deixa
    costurar depois. A linha 0 é a do norte; a coluna 0, a do leste (RA maior).

    Devolve (painéis, cobertura): a cobertura é o tamanho total fotografado (largura, altura).
    """
    import math
    fov_w, fov_h = fov_deg
    step_w, step_h = fov_w * (1.0 - overlap), fov_h * (1.0 - overlap)
    cos_dec = max(math.cos(math.radians(dec_deg)), 1e-3)      # perto do polo o RA "estica"
    panels = []
    for r in range(rows):
        for c in range(cols):
            d_dec = ((rows - 1) / 2.0 - r) * step_h
            d_ra = ((cols - 1) / 2.0 - c) * step_w / cos_dec
            panels.append({"name": f"R{r}C{c}", "row": r, "col": c,
                           "ra_deg": round((ra_deg + d_ra) % 360.0, 4),
                           "dec_deg": round(max(-90.0, min(90.0, dec_deg + d_dec)), 4)})
    covers = (round(fov_w + (cols - 1) * step_w, 3), round(fov_h + (rows - 1) * step_h, 3))
    return panels, covers


def stitch_siril(fits_paths, out_path):
    """Costura os painéis com Siril headless (reuso). Sem Siril, pula com mensagem clara.

    Os FITS de cada painel já têm WCS — o Siril alinha por coordenadas e compõe o mosaico.
    TODO(bring-up): validar o script exato de mosaico do Siril quando o binário estiver disponível."""
    exe = shutil.which("siril-cli") or shutil.which("siril")
    if not exe or not fits_paths:
        print(f"[mosaico] Siril não encontrado — stitch pulado. "
              f"{len(fits_paths)} painéis FITS (com WCS) prontos para costurar no Siril.")
        return None
    script = "requires\n" + "".join(f"load {p}\n" for p in fits_paths) + "close\n"
    try:
        subprocess.run([exe, "-s", "-"], input=script.encode(),
                       capture_output=True, timeout=600)
        return out_path if os.path.exists(out_path) else None
    except Exception as e:
        print(f"[mosaico] stitch falhou: {e}")
        return None


class Mosaic:
    def __init__(self, session, do_autofocus: bool = True):
        self.session = session
        self.do_autofocus = do_autofocus

    def run(self, center_xy, rows=2, cols=2, step_px=300, frames_per_panel=40, stitch=True):
        cx, cy = center_xy
        panels = panel_centers(cx, cy, rows, cols, step_px)
        print(f"\n##### MOSAICO {rows}x{cols} ({len(panels)} painéis) em "
              f"({cx:.0f},{cy:.0f}) #####")
        targets = [Target(name, xy, frames=frames_per_panel, priority=0)
                   for name, xy in panels]
        res = Scheduler(self.session, do_autofocus=self.do_autofocus).run(targets)

        out_dir = self.session.cfg.out_dir
        fits = [os.path.join(out_dir, f"stack_{name}.fits") for name, _ in panels]
        fits = [p for p in fits if os.path.exists(p)]
        stitched = stitch_siril(fits, os.path.join(out_dir, "mosaico.fits")) if stitch else None
        return dict(panels=res["results"], fits=fits, stitched=stitched)
