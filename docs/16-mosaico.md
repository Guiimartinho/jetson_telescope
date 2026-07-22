# 16 — T1: Mosaico multi-painel

Divide um alvo grande (tipo Andrômeda, que não cabe num frame) numa **grade de painéis**, captura
cada painel autonomamente e costura. Compõe o agendador (cada painel = um alvo) — sem duplicar nada.

## Como funciona
1. `panel_centers(cx, cy, rows, cols, step_px)` → centros dos painéis (coords) numa grade centrada.
2. Cada painel vira um `Target`; o **`Scheduler`** percorre: auto-find → autofoco → stack → **FITS com WCS**.
3. `stitch_siril(fits, saida)` costura os painéis no **Siril headless** usando o WCS de cada FITS.

**Construído:** o planejamento da grade + a captura por painel. **Reuso:** agendador, FITS/WCS, Siril.

## Como rodar
```bash
python run_mosaic.py --rows 2 --cols 2 --frames 40     # mosaico 2x2 de Andrômeda, live em :8000
```
No live view, o alvo mostra `RxCy` e a barra da fila enche painel a painel.

## Stitch (Siril)
O `stitch_siril` detecta `siril-cli`/`siril`. **Sem Siril instalado**, ele pula com mensagem clara —
os painéis FITS (com WCS) ficam prontos para costurar no Siril (GUI ou CLI). Instalar: pacote Siril.
> TODO(bring-up): validar o script exato de mosaico do Siril quando o binário estiver disponível.

## Validação (PC de dev, 2026-07)
- `tests/test_mosaic.py`: grade de painéis correta; mosaico 2×2 percorre os 4 painéis e grava 4 FITS;
  stitch pula com elegância sem Siril. **77 testes verdes.**

## No hardware
`Target.xy` vira (RA, DEC); o passo entre painéis sai do FOV real da câmera/óptica (com overlap). O
Siril alinha por WCS. O `Mosaic` e o `Scheduler` **não mudam**.
