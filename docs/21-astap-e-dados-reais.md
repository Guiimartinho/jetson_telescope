# 21 — Plate solving real (ASTAP) + validação com dados reais (T14, T15)

Dois passos do Milestone D ("fechar a stack de software antes da câmera", ver `TASKS.md`): trocar
os dublês por ferramentas/dados REAIS, tudo no PC de dev e de graça.

## T14 — Plate solving real com ASTAP

Antes o `SimSolver` "resolvia" lendo a verdade do simulador. Agora o **`AstapSolver`** (`control/
solver.py`) chama o **ASTAP** de verdade (grátis; binário fechado grátis é ok pela regra do projeto):

```
frame ─► salva FITS temp ─► ASTAP CLI ─► lê o .ini gerado ─► parse_astap_result ─► WcsInfo(RA,DEC,scale,rot)
```

- `parse_astap_result(text)` — função **pura** que lê o `.ini` do ASTAP (`PLTSOLVD=T` + `CRVAL1/2`,
  `CDELT/CROTA` ou a matriz `CD`). Testável com saída enlatada, sem ASTAP instalado.
- `AstapSolver.solve_wcs(frame, hint)` → `WcsInfo`; `solve()` devolve `(RA°, DEC°, rot°)` p/ o port.
- `astap_bin` aceita str (caminho) **ou** list (argv-prefixo) — permite testar o fluxo completo com um
  **ASTAP falso** (`tests/fake_astap.py`, um script que gera um `.ini` enlatado). Sem ASTAP → `None` limpo.

**Unidades:** o ASTAP resolve o céu REAL → RA/DEC em graus. O `SimSolver` fala pixels do simulador. A
ponte pixel↔RA/DEC do laço de auto-find no céu real é do bring-up (Milestone F) — aqui provamos que o
solver resolve e parseia certo.

Testes: `tests/test_solver_astap.py` (parser resolvido/não-resolvido/matriz-CD, e2e com ASTAP falso,
hint roundtrip, binário ausente). Integração real: `tests/test_solver_integration.py` (marker
`hardware`, pulado; precisa do ASTAP + índice de estrelas + `ASTAP_TEST_FITS`).

## T15 — Validação do pipeline com DADOS REAIS

Até aqui o pipeline só tinha visto o **céu sintético**. O simulador esconde problemas: PSFs reais não
são gaussianas perfeitas, o ruído de leitura e o fundo do céu são estruturados. T15 roda o pipeline
sobre um **campo estelar REAL** — um recorte 512×512 de um CCD do aglomerado **M67** (`tests/data/
real_starfield_m67.fits`; fonte: `photutils.datasets.load_star_image`, dado público). Regenerável com
`scripts/fetch_real_data.py`.

Os 3 pilares, medidos no campo real (na GPU RTX 4070):

| Pilar | Resultado no campo real |
|---|---|
| **Detecção + FWHM** | 60 estrelas detectadas; FWHM real ~10 px (PSF grande desse CCD — plausível) |
| **Registro** (astroalign/cv2) | recupera uma transformação conhecida (dx=6,4 dy=−4,2 rot=0,6°): correlação **0,215 → 0,995** |
| **Empilhamento** (√N) | 16 frames com ruído σ=60 → resíduo **15,0** = σ/√16 exato (**ganho 4,0×**) |

Testes: `tests/test_real_pipeline.py` (5). Rodam offline (fixture versionada).

## O que isto fecha (e o que não)

- ✅ O solver real (ASTAP) resolve e parseia; a detecção, o registro e o empilhamento funcionam sobre
  **estrelas reais** (PSF/ruído/fundo reais), não só o simulador.
- ⚠️ **Não** substitui uma noite real: um teste com *várias subs* reais da mesma câmera (dark/flat
  reais, deriva de tracking real, gradiente de céu real) é do bring-up (Milestone F, com a câmera).
  Mas o risco de *algoritmo* — "será que quebra fora do simulador?" — está coberto.

Falta no Milestone D: **T7 (git + CI)**. Depois: Milestone E (bring-up na Orin) → F (câmera). Ver `TASKS.md`.
