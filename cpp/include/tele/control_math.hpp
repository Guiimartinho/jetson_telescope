// Utilitários numéricos do caminho de controle em C++ (hot path da Jetson).
// Header-only, sem dependências — testável isoladamente (ver cpp/tests).
// São as mesmas ideias do lado Python (auto-find, autofoco), na linguagem do
// laço de tempo real. Ver docs/10-arquitetura-e-testes.md.
#pragma once

#include <algorithm>
#include <cmath>

namespace tele {

// Erro de apontamento (px) — magnitude euclidiana do vetor de erro.
inline double pointing_error(double ex, double ey) { return std::hypot(ex, ey); }

// Satura um valor em [lo, hi] (ex.: limitar o comando enviado ao motor).
inline double clamp(double v, double lo, double hi) {
  return std::min(std::max(v, lo), hi);
}

// Passo de correção do auto-find: fração do erro, saturada para evitar overshoot.
inline double correction_step(double err, double gain, double max_step) {
  return clamp(err * gain, -max_step, max_step);
}

// Vértice (x do mínimo) da parábola que passa por 3 pontos — base do autofoco.
// Retorna NaN se os pontos forem degenerados (colineares/coincidentes).
inline double parabola_vertex(double x0, double y0, double x1, double y1,
                              double x2, double y2) {
  const double d = (x0 - x1) * (x0 - x2) * (x1 - x2);
  if (std::abs(d) < 1e-12) return std::nan("");
  const double a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / d;
  const double b =
      (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / d;
  if (std::abs(a) < 1e-12) return std::nan("");   // reta, sem vértice
  return -b / (2.0 * a);
}

}  // namespace tele
