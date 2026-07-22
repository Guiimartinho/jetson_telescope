# 03 — Pipeline de Software (desenho dos módulos)

Desenho técnico de cada módulo crítico. Os trechos de código são **esboços de referência** (não finais):
mostram a estratégia de memória e os algoritmos, prontos para virar os arquivos de `gpu/` e `control/`.

---

## A. Live Stacking acelerado por GPU (`gpu/stacker.py`)

**Estratégia:** manter na VRAM um **acumulador de soma ponderada em float32** e um **mapa de pesos**.
Cada frame bom é alinhado, ponderado por sua qualidade e somado. A imagem exibida é `soma / peso`.
Nunca se recomputa a média do zero — é incremental, O(1) por frame.

```python
import cupy as cp

class LiveStacker:
    """Empilhamento incremental por média ponderada, 100% em VRAM (float32).

    Maximiza alcance dinâmico (float32) e mitiga ruído de leitura acumulando
    muitos subs curtos. Memória residente: 2 buffers do tamanho do frame.
    """
    def __init__(self, h, w, channels=3):
        # Acumuladores residentes na VRAM por toda a sessão.
        self._sum = cp.zeros((h, w, channels), dtype=cp.float32)   # Σ (peso_i · frame_i)
        self._wsum = cp.zeros((h, w, 1),      dtype=cp.float32)    # Σ peso_i
        self.n = 0

    def add(self, frame_f32: cp.ndarray, weight: float, mask: cp.ndarray = None):
        """frame_f32: já debayerizado, calibrado e ALINHADO ao referencial (em VRAM).
        weight: qualidade do frame (ex.: 1/FWHM² ou nitidez laplaciana normalizada).
        mask: 1 onde o pixel é válido após o warp (bordas viram 0), opcional.
        """
        w = cp.float32(weight)
        if mask is None:
            self._sum  += w * frame_f32
            self._wsum += w
        else:
            self._sum  += (w * mask) * frame_f32
            self._wsum += w * mask
        self.n += 1

    def result(self) -> cp.ndarray:
        """Imagem integrada atual (float32, ainda em VRAM). Evita divisão por zero."""
        return self._sum / cp.maximum(self._wsum, cp.float32(1e-6))

    def reset(self):
        self._sum.fill(0); self._wsum.fill(0); self.n = 0
```

**Ganhos-chave:**
- Ponderação por qualidade = *lucky imaging* embutido (frames melhores pesam mais, em vez de descarte binário).
- float32 preserva alcance dinâmico e permite subtrair ruído de leitura ao acumular.
- Tudo em VRAM: `add()` são poucas operações elementares que a GPU faz em ~ms para 4K.

---

## B. Portão de qualidade — FWHM & Variância Laplaciana (`gpu/quality.py`)

Responde ao **Entregável #2** (cálculo de FWHM para autofoco e rejeição). Dois sinais complementares:

- **Variância Laplaciana** — nitidez global barata; rejeita nuvens/desfoque de atmosfera. Triagem rápida.
- **FWHM médio das estrelas** — métrica física do tamanho da PSF; base do autofoco e do *lucky imaging*.

```python
import cupy as cp
import cv2  # compilado com CUDA

# --- Nitidez global: variância do Laplaciano na GPU (triagem rápida) ---
def laplacian_variance(gray_gpu: cv2.cuda.GpuMat) -> float:
    lap = cv2.cuda.Laplacian(gray_gpu, cv2.CV_32F, ksize=3)
    mean, stddev = cv2.cuda.meanStdDev(lap)
    return float(stddev[0]) ** 2   # variância = nitidez; cai com desfoque/nuvem

# --- FWHM: mede o diâmetro típico das estrelas ---
def measure_fwhm(gray: cp.ndarray, threshold_sigma=5.0, max_stars=50) -> float:
    """Estima o FWHM mediano (px) das estrelas mais brilhantes.
    Assume PSF ~gaussiana: FWHM = 2.3548 · sigma.

    Estratégia real de produção: detectar picos (estrelas) acima de
    fundo+Nσ, recortar janelas pequenas e ajustar gaussiana 2D (ou usar
    o 2º momento da intensidade). Aqui, a versão por 2º momento (barata):
    """
    bg = cp.median(gray)
    sigma_bg = cp.std(gray)
    thr = bg + threshold_sigma * sigma_bg

    # Localiza estrelas candidatas (picos acima do limiar).
    ys, xs = cp.where(gray > thr)
    if xs.size == 0:
        return float('inf')   # sem estrelas → frame inútil

    # (Produção: agrupar por conectividade e pegar os max_stars mais brilhantes.)
    fwhms = []
    half = 7  # janela 15×15 ao redor de cada estrela
    H, W = gray.shape
    # Amostra um subconjunto para manter custo baixo.
    idx = cp.linspace(0, xs.size - 1, num=min(max_stars, xs.size)).astype(cp.int32)
    for i in idx.tolist():
        y, x = int(ys[i]), int(xs[i])
        if y-half < 0 or y+half >= H or x-half < 0 or x+half >= W:
            continue
        win = gray[y-half:y+half+1, x-half:x+half+1] - bg
        win = cp.clip(win, 0, None)
        tot = cp.sum(win)
        if tot <= 0:
            continue
        yy, xx = cp.mgrid[-half:half+1, -half:half+1]
        # 2º momento (variância espacial ponderada pela intensidade) → sigma.
        cx = cp.sum(win * xx) / tot
        cy = cp.sum(win * yy) / tot
        var = cp.sum(win * ((xx - cx)**2 + (yy - cy)**2)) / (2 * tot)
        fwhms.append(2.3548 * cp.sqrt(var))
    if not fwhms:
        return float('inf')
    return float(cp.median(cp.asarray(fwhms)))

# --- Decisão do portão ---
def accept_frame(gray_gpu, gray_cp, cfg) -> tuple[bool, float, float]:
    sharp = laplacian_variance(gray_gpu)
    if sharp < cfg.min_sharpness:          # nuvem/desfoque grosseiro → corta cedo
        return False, sharp, float('inf')
    fwhm = measure_fwhm(gray_cp)
    if fwhm > cfg.max_fwhm_px:             # estrelas gordas → atmosfera ruim
        return False, sharp, fwhm
    weight = 1.0 / (fwhm * fwhm)           # peso p/ o stacker (lucky imaging)
    return True, sharp, weight
```

> O portão roda **antes** do alinhamento caro: se o frame é lixo (nuvem, rastro, borrão), descarta-se já na
> variância laplaciana, economizando o registro/warp.

---

## C. Detecção de estrelas-guia & registro (`gpu/registration.py`)

**Objetivo:** alinhar cada frame ao *frame de referência* (o primeiro bom) via translação+rotação.

1. **Detecção de estrelas** na GPU (limiar adaptativo + centroides, ou `cv2.cuda` ORB/FAST) → lista de pontos.
2. **Correspondência** com as estrelas de referência (por triângulos/padrões invariantes a rotação, à la
   *astroalign*, ou casamento de descritores ORB na GPU).
3. **Matriz de transformação:** `cv2.estimateAffinePartial2D` (translação+rotação+escala) com RANSAC — para
   altaz com derotação de campo, ou homografia se houver distorção. Poucos pontos → cálculo em µs na CPU;
   só a matriz volta ao host.
4. **Warp na GPU:** `cv2.cuda.warpAffine(frame, M, dsize)` — reprojeta o frame ao referencial. Gera também a
   `mask` de pixels válidos (para o `LiveStacker.add`).

```python
def register_and_warp(frame_gpu, stars, ref_stars, ref_shape):
    M = estimate_transform(stars, ref_stars)      # afim parcial + RANSAC (CPU, barato)
    if M is None:
        return None, None                         # falha de alinhamento → descarta
    warped = cv2.cuda.warpAffine(frame_gpu, M, (ref_shape[1], ref_shape[0]))
    mask   = cv2.cuda.warpAffine(ONES_GPU, M, (ref_shape[1], ref_shape[0]))
    return warped, mask
```

> **Derotação de campo (EQ por software):** numa montagem altaz, o campo gira. O passo de registro por
> rotação já corrige isso frame a frame — é assim que o DWARF faz "EQ mode" por software. Com a AM3N em
> modo EQ real, a rotação residual é mínima.

---

## D. Autofoco inteligente (`control/autofocus.py`)

Curva **V** (ou hipérbole) de FWHM vs posição do focalizador. A Zona Crítica de Foco (CFZ) é o mínimo.

**Algoritmo:**
1. Varrer o EAF em N posições ao redor do foco atual (passo grosso).
2. Em cada posição, capturar → `measure_fwhm()`.
3. Ajustar **hipérbole** `FWHM(x) = sqrt(a² + b²·(x−c)²)` (mais robusta que parábola longe do foco) por
   mínimos quadrados; o vértice `c` é a posição de foco crítico.
4. Refinar com passo fino perto de `c`; mover o EAF para `c`.
5. Reacionar quando a temperatura variar > limiar (foco desloca com dilatação térmica do tubo).

```python
import numpy as np
from scipy.optimize import curve_fit

def hyperbola(x, a, b, c):        # V suavizado; vértice em x=c
    return np.sqrt(a**2 + (b*(x - c))**2)

def find_critical_focus(positions, fwhms):
    p, f = np.asarray(positions), np.asarray(fwhms)
    c0 = p[np.argmin(f)]                                  # chute: menor FWHM medido
    popt, _ = curve_fit(hyperbola, p, f, p0=[f.min(), 1.0, c0], maxfev=10000)
    return float(popt[2])                                  # posição de foco crítico (c)
```

> A varredura roda no `control/`, chamando a câmera via captura e o EAF via INDI (`indi_asi_focuser`).
> O FWHM vem do módulo `gpu/quality.py` — mesma métrica do portão de qualidade, reaproveitada.

---

## E. Plate solving local sub-segundo (`control/platesolve.py`)

- **ASTAP** (recomendado) com índices (ex. D50/D20) no **NVMe** → resolve um campo em ~0,1–1s, offline.
- Fluxo: captura → salva FITS temporário (ou passa estrelas detectadas) → `astap_cli -f frame.fits -r 5 -fov X`
  → lê RA/DEC/rotação do `.wcs`/`.ini` de saída → alimenta GOTO/sincronização do mount via INDI.
- Chamada **assíncrona** (subprocess) para não travar o pipeline; usada em: alinhamento inicial, GOTO
  centrado, verificação de deriva, e recuperação ("lost in space").

```python
import asyncio

async def solve(fits_path, fov_deg, ra_hint=None, dec_hint=None):
    cmd = ["astap_cli", "-f", fits_path, "-fov", str(fov_deg), "-r", "5"]
    if ra_hint is not None:
        cmd += ["-ra", str(ra_hint), "-spd", str(dec_hint + 90)]  # dica acelera muito
    proc = await asyncio.create_subprocess_exec(*cmd,
              stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()
    return parse_wcs(fits_path.replace(".fits", ".wcs"))   # → (ra, dec, rot, escala)
```

---

## F. Rastreamento ativo de objetos (`control/tracking.py`)

Dois modos, conforme o alvo:

- **Fluxo óptico CUDA** (`cv2.cuda.FarnebackOpticalFlow` / `NvidiaOpticalFlow`) para deriva suave de campo
  e objetos previsíveis — barato, roda a cada frame.
- **YOLOv8-n exportado para TensorRT** para detectar silhuetas de satélites/ISS/meteoros contra o céu.
  Roda no **CUDA stream B**, em paralelo ao stacking. Alvo >60 FPS na Orin NX.

**Correção feed-forward:** a posição prevista do alvo no próximo frame vira um vetor de velocidade enviado
**antecipadamente** ao mount (INDI), compensando a latência do laço — em vez de só reagir ao erro atual.

```python
# Esboço do laço de rastreamento (thread IA)
def track_loop(ring, engine, mount):
    prev = None
    for frame in ring.stream():                 # frames da memória unificada
        det = engine.infer(frame)               # YOLOv8-TensorRT (CUDA stream B)
        if det is None:
            continue
        if prev is not None:
            v = predict_velocity(prev, det)     # px/frame → °/s
            mount.slew_feedforward(v)           # correção ANTECIPADA (INDI)
        prev = det
```

---

## Resumo dos entregáveis cobertos

| Entregável do briefing | Onde |
|---|---|
| #1 Desenho arquitetural (fluxo, min. cópias) | [`docs/02-arquitetura.md`](02-arquitetura.md) |
| #2 Live stacking acelerado (código) | Seção A (`LiveStacker`) |
| #2 Cálculo de FWHM (autofoco) | Seções B e D |
| #3 Setup de ambiente | [`docs/05-setup-ambiente.md`](05-setup-ambiente.md) |
