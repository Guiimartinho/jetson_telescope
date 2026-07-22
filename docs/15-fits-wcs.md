# 15 — Saída FITS + WCS (astropy)

Salva o stack final como **FITS float32** com **coordenadas (WCS)** do plate solve e header de
equipamento — abrível no **Siril / PixInsight / ASTAP**. Reuso de `astropy` (docs/08). Também lê
FITS (para calibração/subs reais no futuro). Módulo: `src/io/fits_io.py`.

## API

```python
from src.io.fits_io import save_fits, load_fits, WcsInfo
save_fits("stack.fits", imagem,                       # mono HxW ou cor 3xHxW
          wcs=WcsInfo(ra_deg=10.68, dec_deg=41.27, pixscale_arcsec=2.9, rotation_deg=0.0),
          meta={"OBJECT": "M31", "NCOMBINE": 200})
data, header = load_fits("stack.fits")
```

- **WCS** construído com `astropy.wcs` (matriz CD): `CTYPE=RA---TAN/DEC--TAN`, `CRVAL`=centro,
  `CRPIX`=pixel central, escala em `arcsec/px`, rotação do campo.
- **Metadados** viram cards FITS (chave ≤ 8 chars, ASCII): `OBJECT`, `NCOMBINE`, `DATE-OBS`, etc.
- `BITPIX/NAXIS` são estruturais — o astropy os define a partir dos dados (não setar à mão).

## Integração no pipeline
`run_stack` salva `output/stack_<alvo>.fits` ao fim, com `NCOMBINE`=frames empilhados, `DATE-OBS`
e **WCS** quando há solução de plate solve (`Session.last_solution`, gravada pelo `auto_find`). No
simulador o WCS usa um mapeamento mundo→RA/DEC plausível; **no hardware o `AstapSolver` dá RA/DEC reais**
e o `WcsInfo` sai direto do solve — o resto não muda.

## Validação (PC de dev, 2026-07)
- `tests/test_fits.py`: round-trip salvar/ler (dados idênticos), **WCS parseável** pelo `astropy.wcs`
  (centro → RA/DEC dados), metadados presentes, cor salva como 3 planos.
- FITS real do pipeline: `stack_final.fits` float32, `OBJECT`, `NCOMBINE`, `DATE-OBS`,
  `CTYPE=RA---TAN/DEC--TAN`, WCS celestial ✓. **74 testes verdes.**

## Próximo (reuso)
Mosaico (Siril headless combina os painéis usando o WCS), depois denoise IA (GraXpert) e filtros.
