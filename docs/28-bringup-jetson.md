# 28 — Bring-up na Jetson Orin Nano Super (Milestone E)

Port do software (validado no PC) para a Jetson real. Feito via SSH (paramiko). Data: 2026-07-22.

## Ambiente encontrado

| | |
|---|---|
| Modelo | Jetson Orin Nano **Super** Dev Kit (aarch64) |
| JetPack / L4T | 6.2 / R36.5.0 · **CUDA 12.6** · **TensorRT 10.3** |
| Python | 3.10.12 · Energia: **MAXN_SUPER** já ativo |
| RAM / Disco | 7,4 GB · 201 GB livres (NVMe) |

## Passos executados

1. **Transferência**: `git archive HEAD | tar` (~392 KB) → SFTP → `~/telescope` (149 arquivos).
2. **Dependências** (`pip3 install --user`): opencv-python-headless, scipy, astropy, scikit-image,
   astroalign, pyongc, pytest — **wheels aarch64 prontas** (~1 min). numpy/tensorrt já vinham do JetPack.
3. **CuPy (GPU)**: `pip3 install --user cupy-cuda12x` → wheel aarch64 (143 MB). Backend passou a
   **CuPy/GPU (Orin)**.
4. **Testes**: `pytest -m "not hardware"` → **164 passam** (33 s) — pipeline inteiro roda no Orin.
5. **Painel** (`run_app.py`, host 0.0.0.0:8000) e **Estúdio** (`run_studio.py --host 0.0.0.0`, porta 8010)
   rodando na Jetson, **acessíveis pelo celular na rede**. Estúdio renderiza M51/Roseta/Lagoa (0,5–1,3 s/imagem).
6. **INDI real**: `sudo apt install indi-bin`; `indiserver -v indi_simulator_{telescope,focus,wheel,ccd}`;
   `pytest tests/test_indi_integration.py -m hardware` → **4/4 passam** (contra os drivers reais).

## Benchmark GPU real (Orin)

| Operação (4K) | GPU | speedup vs CPU |
|---|---|---|
| stack add (coração do empilhamento) | 2,86 ms | **4,3×** |
| warp afim (registro) | 3,07 ms | 2,8× |
| laplaciano | 24 ms | 1,4× |

Frame 4K completo ~30 ms → **classe 30 FPS** de live stacking. Modesto vs RTX 4070 (o Orin é bem menor),
mas a GPU ganha do CPU no que importa; 8 GB deu conta.

## Bugs REAIS achados e corrigidos no bring-up (o valor de testar no hardware)

- **IndiFocuser.move_to**: confiava no `state=='Ok'`, mas o driver move gradual e o estado **pisca Ok
  antes de ir a Busy** → retornava com a posição antiga. Corrigido: **espera a posição chegar** no alvo.
- **IndiCameraSource**: a exposição ia a **Alert** e o BLOB não chegava — faltava setar
  **`UPLOAD_MODE=UPLOAD_CLIENT`** (senão o driver salva em disco). Corrigido no `_setup`.

Ambos passam agora contra o `indi_simulator_*` real (e valem para o hardware).

## Como reconectar / rodar (referência)

```bash
# do PC (paramiko/ssh):  jetson-nano-super@192.168.3.221
cd ~/telescope
python3 run_app.py --port 8000                    # painel  -> http://<ip>:8000
python3 run_studio.py --host 0.0.0.0 --port 8010  # estudio -> http://<ip>:8010
indiserver -v indi_simulator_telescope indi_simulator_focus indi_simulator_wheel indi_simulator_ccd &
INDI_HOST=127.0.0.1 python3 -m pytest tests/test_indi_integration.py -m hardware -v
```

## Falta (futuro)

- **OpenCV com CUDA** (`cv2.cuda`): compilação de **horas** no Orin; baixo ROI agora (o CuPy já faz o
  pesado). Fazer com `jetson-containers` ou build dedicado quando for otimizar debayer/laplaciano na GPU.
- **Engine TensorRT do YOLO**: precisa do torch da Jetson + ultralytics (instalação pesada, ~GB). O
  tracking já funciona com o detector CV de fallback; converter para TensorRT é otimização de FPS.
- **Milestone F** (câmera física): captura zero-copy (Argus/USB), foco/solve/tracking no céu real.
