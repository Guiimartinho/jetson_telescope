# 20 — Camada INDI validada sem hardware (T13)

**Objetivo:** provar toda a fronteira de hardware (câmera, montagem, foco, roda de filtros)
**antes de comprar a câmera** — usando só software grátis. Este é o maior de-risk do projeto:
até aqui o sistema só tinha visto adapters *simulados internos* (`Sim*`); agora ele fala o
**protocolo INDI de verdade**, o mesmo que roda na Jetson com os drivers reais.

## O problema com o `pyindi-client`

O caminho "oficial" (PyIndi) exige compilar as libs C++ do INDI e **não roda no Windows** (PC de
dev). Ou seja: os antigos `IndiMount/IndiFocuser/IndiFilterWheel/IndiCameraSource` eram escafolds que
levantavam `NotImplementedError` — nunca tinham conectado nem num simulador. Risco escondido.

## A solução: cliente INDI puro-Python

`src/io/indi_client.py` — um cliente que fala o protocolo INDI **direto** (XML sobre TCP na porta
7624), usando só a stdlib. Roda em qualquer plataforma e é **testável na CI**.

```
        ┌──────────────── PC de dev (Windows) ─────────────┐   ┌── Jetson / WSL ──┐
adapters │ IndiCameraSource  IndiMount  IndiFocuser  ...   │   │  (mesmo código)  │
   │     │        └──────────┬───────────┘                 │   │        │         │
IndiClient (socket + XML, stdlib) ──── TCP 7624 ───────────┼───┼── indiserver ────┤
   │     │        │                                        │   │  indi_simulator_*│
teste    │  FakeIndiServer (tests/fake_indi.py)            │   │  OU drivers reais│
         └──────────────────────────────────────────────────┘   └──────────────────┘
```

Detalhes de protocolo tratados: fluxo de elementos XML de topo concatenados (parse incremental via
`XMLPullParser` semeado com raiz sintética), `def*Vector`/`set*Vector`, `newNumber/Switch/Text`,
`enableBLOB`, BLOB em base64 (imagem CCD → FITS), estados `Idle/Ok/Busy/Alert` (para esperar o fim
de um slew), e números sexagesimais.

## Os adapters (mesmos ports de sempre)

| Adapter | Vetor INDI | Port |
|---|---|---|
| `IndiCameraSource` | `CCD_EXPOSURE` → BLOB `CCD1` (FITS) | `FrameSource.read()` |
| `IndiMount` | `EQUATORIAL_EOD_COORD` + `ON_COORD_SET` | RA/DEC nativo¹ |
| `IndiFocuser` | `ABS_FOCUS_POSITION` | `Focuser.move_to/position` |
| `IndiFilterWheel` | `FILTER_SLOT` + `FILTER_NAME` | `FilterWheel.names/current/set` |

¹ **Nota arquitetural:** a montagem real trabalha em RA(h)/DEC(°), não nos *pixels* do simulador. Por
isso `IndiMount` expõe `slew_radec/sync_radec/get_radec` e **rejeita** os métodos em pixels do port
(`slew/nudge/pointing`). No céu real quem fecha a malha do auto-find é o plate solve em RA/DEC —
essa fiação fica no bring-up de hardware (Milestone F).

## Como validar

**Na CI / PC de dev (sem INDI, automático):** os testes usam o `FakeIndiServer`.
```
py -3.11 -m pytest tests/test_indi_client.py tests/test_indi_adapters.py -v   # 13 testes
```

**Contra o indiserver REAL (WSL/Linux/Jetson):** valida que os MESMOS adapters falam com o driver.
```
# 1) suba os simuladores do INDI (precisa de indi-bin instalado):
bash scripts/run_indi_sim.sh
# 2) rode os testes de integração (marcados `hardware`, pulados por padrão):
INDI_HOST=127.0.0.1 py -3.11 -m pytest tests/test_indi_integration.py -m hardware -v
```

## O que isto garante (e o que não)

- ✅ O protocolo INDI, o parse de BLOB/FITS, a espera de estados e os 4 adapters estão corretos.
- ✅ Cross-platform: o mesmo código no Windows, no WSL e na Jetson.
- ⚠️ **Não** substitui o bring-up físico: nomes de propriedade de drivers reais (ex.: `CCD_GAIN` vs
  `CCD_CONTROLS`), Bayer/ROI da IMX585, e o mapa RA/DEC↔plate-solve são ajustados com a câmera na mão
  (Milestone F). Mas o risco de *arquitetura de software* da fronteira INDI está zerado.

Ver `docs/08` (reusar vs construir) e `TASKS.md` (Milestones D/E/F).
