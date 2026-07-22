"""Autofoco por curva V/hipérbole de FWHM — o algoritmo que docs/08 manda REUSAR do Ekos.

Varre o focalizador em N posições, mede o FWHM (na GPU, via gpu/quality) em cada uma,
ajusta uma hipérbole  FWHM(x) = √(a² + (b·(x−c))²)  e move para o vértice c (foco crítico).
Fallback para parábola se o scipy não estiver disponível. Ver docs/03-pipeline-software.md §D.
"""
from __future__ import annotations
import numpy as np

from ..gpu.quality import detect_stars, measure_fwhm

try:
    from scipy.optimize import curve_fit
    HAS_SCIPY = True
except Exception:
    HAS_SCIPY = False


def _hyperbola(x, a, b, c):
    return np.sqrt(a * a + (b * (x - c)) ** 2)


def fit_critical_focus(positions, fwhms):
    """Devolve a posição de foco crítico a partir da curva (pos, FWHM)."""
    p = np.asarray(positions, float)
    f = np.asarray(fwhms, float)
    ok = np.isfinite(f)
    p, f = p[ok], f[ok]
    if len(p) < 3:
        return None
    c0 = float(p[np.argmin(f)])
    if HAS_SCIPY:
        try:
            popt, _ = curve_fit(_hyperbola, p, f,
                                p0=[max(f.min(), 1.0), 0.01, c0], maxfev=10000)
            return float(popt[2])
        except Exception:
            pass
    coef = np.polyfit(p, f, 2)            # fallback: vértice da parábola
    return c0 if coef[0] <= 0 else float(-coef[1] / (2 * coef[0]))


class AutoFocuser:
    def __init__(self, source, focuser, quality, span=4000, steps=9, max_expansions=4):
        self.source, self.focuser, self.q = source, focuser, quality
        self.span, self.steps, self.max_exp = span, steps, max_expansions

    def _measure(self, pos, progress):
        self.focuser.move_to(pos)
        frame, _ = self.source.read()
        stars, _ = detect_stars(frame, self.q)
        fwhm = measure_fwhm(frame, stars, self.q) if len(stars) >= 3 else float("inf")
        if progress:
            progress(self.focuser.position(), fwhm, frame)
        return self.focuser.position(), fwhm

    def _sweep(self, center, progress, should_stop):
        xs = np.linspace(center - self.span / 2, center + self.span / 2, self.steps)
        out = []
        for x in xs:
            if should_stop and should_stop():          # aborta na parada (troca de modo)
                break
            out.append(self._measure(x, progress))
        return out

    def run(self, progress=None, should_stop=None):
        """Varre, BRACKETA o mínimo (V-curve) e vai ao foco crítico (hipérbole).

        Se o menor FWHM cai na borda da varredura, re-centra sobre essa borda e varre
        de novo. Checa `should_stop()` para abortar prontamente (troca de modo/parada)."""
        curve = self._sweep(self.focuser.position(), progress, should_stop)
        for _ in range(self.max_exp):
            if (should_stop and should_stop()) or not curve:
                break
            fwhms = [c[1] for c in curve]
            imin = int(np.argmin(fwhms))
            if 0 < imin < len(curve) - 1:          # mínimo interior → bracketado
                break
            curve = self._sweep(curve[imin][0], progress, should_stop)   # re-centra na borda

        if not curve:                              # parou antes de medir algo
            return self.focuser.position(), float("inf"), []
        best = fit_critical_focus([c[0] for c in curve], [c[1] for c in curve])
        if best is None:
            best = min(curve, key=lambda c: c[1])[0]
        pos, achieved = self._measure(best, progress)
        return pos, achieved, curve
