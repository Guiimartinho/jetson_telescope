# 05 — Setup do Ambiente na Jetson

Comandos de preparação (Entregável #3). Base: **JetPack 6.2.x** (CUDA 12.6, TensorRT 10.3, cuDNN 9.3),
Jetson Orin Nano Super / Orin NX. Rodar como usuário com `sudo`. Ajustar versões conforme o `nvcc --version`.

> ⚠️ Valores como `CUDA_ARCH_BIN=8.7` são específicos da arquitetura **Ampere da Orin**. Em Thor/Blackwell
> mudam — mas Thor está fora do escopo (ver [`docs/01-hardware.md`](01-hardware.md)).

---

## 1. Flash & performance máxima

```bash
# JetPack via SDK Manager (host) ou apt (na placa). Confirmar versão:
sudo apt-cache show nvidia-jetpack | grep Version
nvcc --version                      # esperado: CUDA 12.6 (JetPack 6.2)

# Modo de máxima performance (MAXN / Super Mode) + travar clocks no topo.
sudo nvpmodel -q                    # lista modos disponíveis
sudo nvpmodel -m 0                  # modo 0 = MAXN (máx. performance)
sudo jetson_clocks                  # trava CPU/GPU/EMC no clock máximo
sudo jetson_clocks --show           # conferir

# Monitor de recursos (instalar jetson-stats):
sudo pip3 install -U jetson-stats && sudo reboot
# depois: jtop   (mostra GPU%, VRAM, temperatura, modo nvpmodel)
```

## 2. Swap (necessário para compilar OpenCV no Nano 8GB)

```bash
sudo fallocate -l 8G /var/swapfile
sudo chmod 600 /var/swapfile
sudo mkswap /var/swapfile
sudo swapon /var/swapfile
echo '/var/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
```

## 3. SSD NVMe (índices ASTAP + captura RAW)

```bash
lsblk                               # identificar o NVMe (ex.: nvme0n1)
sudo mkfs.ext4 /dev/nvme0n1
sudo mkdir -p /mnt/ssd
sudo mount /dev/nvme0n1 /mnt/ssd
echo '/dev/nvme0n1 /mnt/ssd ext4 defaults 0 2' | sudo tee -a /etc/fstab
sudo chown -R $USER:$USER /mnt/ssd
```

## 4. OpenCV compilado com CUDA (o do sistema é CPU-only!)

```bash
# Remover qualquer OpenCV CPU-only pré-existente.
sudo apt remove -y '*opencv*' || true
pip3 uninstall -y opencv-python opencv-contrib-python || true

sudo apt update && sudo apt install -y build-essential cmake git pkg-config \
  libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
  libjpeg-dev libpng-dev libtiff-dev gfortran python3-dev python3-numpy

git clone --depth 1 -b 4.10.0 https://github.com/opencv/opencv.git
git clone --depth 1 -b 4.10.0 https://github.com/opencv/opencv_contrib.git
cd opencv && mkdir build && cd build

cmake -D CMAKE_BUILD_TYPE=RELEASE \
      -D CMAKE_INSTALL_PREFIX=/usr/local \
      -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules \
      -D WITH_CUDA=ON \
      -D CUDA_ARCH_BIN=8.7 \                # Orin (Ampere). AGX Orin também 8.7
      -D CUDA_ARCH_PTX= \
      -D WITH_CUDNN=ON -D OPENCV_DNN_CUDA=ON \
      -D ENABLE_FAST_MATH=ON -D CUDA_FAST_MATH=ON \
      -D WITH_CUBLAS=ON \
      -D WITH_V4L=ON -D WITH_GSTREAMER=ON \  # V4L2/GStreamer p/ o caminho MIPI
      -D BUILD_opencv_python3=ON \
      -D BUILD_EXAMPLES=OFF -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF ..

make -j$(nproc)          # Nano: ~1–2 h. AGX: ~20 min.
sudo make install && sudo ldconfig

# Verificar:
python3 -c "import cv2; print(cv2.__version__, cv2.cuda.getCudaEnabledDeviceCount())"
# esperado: 4.10.0 1   (contagem > 0 = CUDA ativo)
```

## 5. CuPy (wheel aarch64 pronta — sem compilar)

```bash
pip3 install cupy-cuda12x            # JetPack 6 / CUDA 12.x
python3 -c "import cupy as cp; a=cp.arange(10); print(a.sum(), cp.cuda.runtime.getDeviceCount())"
```

## 6. INDI + drivers (câmera, mount, focalizador)

```bash
sudo apt-add-repository ppa:mutlaqja/ppa -y
sudo apt update
sudo apt install -y indi-full indi-bin \
     indi-asi indi-playerone          # câmeras; mount AM5/AM3 = indi_lx200am5 (no indi-full)
# Focalizador EAF: driver indi_asi_focuser (vem no indi-asi)

# Cliente Python para o orquestrador:
pip3 install pyindi-client            # (ou build a partir do fonte se a wheel faltar em aarch64)

# Testar o servidor local:
indiserver -v indi_asi_ccd indi_lx200am5 indi_asi_focuser &
# conectar um cliente (KStars/Ekos como referência, ou o nosso orquestrador)
```

## 7. ASTAP (plate solving local)

```bash
# Binário CLI + índice de estrelas (D50 cobre a maioria dos FOVs; guardar no NVMe).
cd /mnt/ssd && mkdir -p astap && cd astap
# Baixar astap_cli (aarch64) e o índice D50 do site oficial do ASTAP.
# wget <astap_cli aarch64> ; wget <índice D50> ; unzip ...
sudo ln -s /mnt/ssd/astap/astap_cli /usr/local/bin/astap_cli
astap_cli -h                          # sanity check
```

## 8. TensorRT (rastreamento — Fase 4)

```bash
# TensorRT já vem no JetPack. Exportar YOLOv8-n para engine .trt na PRÓPRIA Jetson:
pip3 install ultralytics
yolo export model=yolov8n.pt format=engine device=0 half=True   # FP16 na Orin
# gera yolov8n.engine → mover para models/ (usar via TensorRT runtime no control/tracking.py)
```

---

## Checklist de validação do ambiente

| Verificação | Comando | Esperado |
|---|---|---|
| Modo de performance | `sudo nvpmodel -q` | MAXN / modo 0 |
| CUDA | `nvcc --version` | 12.6 |
| OpenCV CUDA | `python3 -c "import cv2; print(cv2.cuda.getCudaEnabledDeviceCount())"` | `> 0` |
| CuPy | `python3 -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"` | `1` |
| Câmera INDI | `indiserver ... indi_asi_ccd` + cliente | frame RAW |
| ASTAP | `astap_cli -h` | ajuda impressa |
| jtop | `jtop` | GPU/VRAM/temperatura |
