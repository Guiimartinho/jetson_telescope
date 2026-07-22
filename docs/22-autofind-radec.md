# 22 — Auto-find celeste em malha fechada (T16): o "apontar sozinho"

O cérebro do apontamento automático — o que faz a DWARF **achar o alvo sozinha**. Fecha o laço em
**coordenadas celestes (RA/DEC)**, não nos pixels do simulador. Amarra o T13 (INDI) e o T14 (ASTAP):
prova, em software, que "temos os adapters" vira "o telescópio aponta sozinho".

## O laço (`control/autofind_radec.py`)

```
alvo (RA°,DEC°) ─► slew ─► captura ─► PLATE SOLVE (RA°,DEC° reais) ─► erro angular (haversine)
                    ▲                                                       │
                    └──────────── sync (corrige o modelo) ◄─────────────────┘   repete até < tolerância
```

`close_loop_goto(mount, solver, target_deg, ...)` roda esse ciclo. Por que converge: um GOTO real cai
**deslocado** (erro de cone/mecânica). O plate solve revela onde a montagem REALMENTE aponta; o `sync`
ensina esse offset à montagem, e o próximo GOTO acerta — **~2 iterações**, igual ao auto-find de pixels
da Fase 2, mas agora em RA/DEC.

Interface mínima (duck-typed), a MESMA no simulador e no hardware:
- `mount`: `goto(ra°, dec°)`, `sync(ra°, dec°)`, `position() -> (ra°, dec°)`.
- `solver`: `solve_wcs(frame) -> WcsInfo` (RA/DEC em graus).

## Dublês (validação sem hardware)

- **`SimRaDecMount`** (`control/mount.py`): montagem em graus com **erro de apontamento sistemático** +
  ruído. `goto` cai deslocado; `sync` corrige o offset. Análogo celeste da `SimMount`.
- **`SimRaDecSolver`** (`control/solver.py`): revela o apontamento REAL da montagem + ruído — como um
  plate solve. Análogo celeste do `SimSolver`.

Na Jetson, os MESMOS argumentos viram **`IndiMount` + `AstapSolver`** sem tocar no laço. O `IndiMount`
ganhou `goto/sync/position` em GRAUS (converte para as HORAS que o INDI usa em `EQUATORIAL_EOD_COORD`),
então a fronteira de unidades fica num só lugar.

## No painel (modo GOTO)

Botão **GOTO (RA/DEC)** no `run_app.py`: escolhe o alvo (M31/M42/M45, com RA/DEC reais), roda o laço ao
vivo e mostra o **erro em arcmin caindo** com o estado `apontando`→`procurando alvo` até centralizar.
Validado via HTTP: M42 convergiu de **19,4 arcmin → 0,36 arcmin**.

## O que fecha (e o que não)

- ✅ A LÓGICA do apontamento automático em coordenadas celestes está provada ponta a ponta: slew→solve→
  sync→centralizar, com a mesma interface que o hardware usará.
- ⚠️ No céu real, o `solve` vem do ASTAP sobre a imagem da câmera (não de um dublê), e o campo estelar
  do live view passa a corresponder de fato ao RA/DEC — isso é o bring-up (Milestone F). Aqui o campo do
  live view é ilustrativo; a malha RA/DEC é o que está sendo validada.

Testes: `tests/test_autofind_radec.py` (6: haversine, convergência, começa-longe/termina-perto, estados,
should_stop, interface deg do IndiMount contra o INDI falso) + `test_controller.py::..goto_mode_centers`.
Ver `docs/20` (INDI), `docs/21` (ASTAP) e `TASKS.md`.
