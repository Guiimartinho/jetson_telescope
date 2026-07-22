#!/usr/bin/env python3
"""Benchmark CPU vs GPU das operações pesadas por pixel do pipeline.

Mede warp afim, variância do Laplaciano e o 'stack add' (soma ponderada) a 1080p e 4K.
No PC de dev usa CuPy/cupyx (RTX 4070); na Jetson o mesmo vale (cupy-cuda12x), e com
OpenCV-CUDA compilado dá para comparar também o cv2.cuda.

Uso:  python scripts/benchmark_gpu.py
"""
from __future__ import annotations
import sys
import time
import numpy as np
import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import cupy as cp
    import cupyx.scipy.ndimage as cndi
    HAS_GPU = True
except Exception:
    HAS_GPU = False


def _time(fn, k, gpu=False):
    fn()                                     # warmup (compila kernels)
    if gpu:
        cp.cuda.runtime.deviceSynchronize()
    t = time.perf_counter()
    for _ in range(k):
        fn()
    if gpu:
        cp.cuda.runtime.deviceSynchronize()
    return (time.perf_counter() - t) / k * 1000.0    # ms/op


def bench(h, w, k=30):
    rng = np.random.default_rng(0)
    img = rng.uniform(0, 3000, (h, w)).astype(np.float32)
    th = np.deg2rad(2.0)
    M = np.array([[np.cos(th), -np.sin(th), 8.0],
                  [np.sin(th), np.cos(th), -5.0]], np.float32)
    fwd = np.array([[M[1, 1], M[1, 0], M[1, 2]],
                    [M[0, 1], M[0, 0], M[0, 2]], [0, 0, 1]])
    inv = np.linalg.inv(fwd)

    g = cp.asarray(img)
    mat = cp.asarray(inv, cp.float32)
    acc_c = np.zeros((h, w), np.float32)
    acc_g = cp.zeros((h, w), cp.float32)

    ops = [
        ("warp afim",
         lambda: cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR),
         lambda: cndi.affine_transform(g, mat, output_shape=(h, w), order=1)),
        ("laplaciano+var",
         lambda: float(cv2.Laplacian(img, cv2.CV_32F, ksize=3).var()),
         lambda: float(cp.var(cndi.laplace(g)))),
        ("stack add",
         lambda: np.add(acc_c, 0.5 * img, out=acc_c),
         lambda: acc_g.__iadd__(cp.float32(0.5) * g)),
    ]
    rows = []
    for name, cpu_fn, gpu_fn in ops:
        cpu = _time(cpu_fn, k)
        gpu = _time(gpu_fn, k, gpu=True)
        rows.append((name, cpu, gpu))
    return rows


def main():
    if not HAS_GPU:
        print("CuPy ausente — sem GPU para comparar (rodaria só em CPU).")
        return
    print(f"GPU: {cp.cuda.runtime.getDeviceProperties(0)['name'].decode()}")
    print("(CPU = OpenCV/NumPy  ·  GPU = cupyx/CuPy)\n")
    for h, w, label in [(1080, 1920, "1080p"), (2160, 3840, "4K")]:
        print(f"=== {label}  ({w}x{h}) ===")
        print(f"{'operação':16s} {'CPU (ms)':>10s} {'GPU (ms)':>10s} {'speedup':>9s}")
        for name, cpu, gpu in bench(h, w):
            print(f"{name:16s} {cpu:10.2f} {gpu:10.2f} {cpu/gpu:7.1f}x")
        print()


if __name__ == "__main__":
    main()
