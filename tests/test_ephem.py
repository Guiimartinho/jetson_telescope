"""Sol, Lua e planetas em baixa precisão (src/core/ephem.py).

As posições de referência vieram da efeméride embutida do astropy (`get_body`, geocêntrico) e
estão escritas aqui: o teste não depende do astropy nem de rede.
"""
import math
from datetime import datetime, timezone

import pytest

from src.core import ephem

REFERENCE = {
    datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc): {
        "sun": (195.106, -6.445), "moon": (187.105, -6.7), "mercury": (217.988, -17.792),
        "venus": (212.227, -21.055), "mars": (129.206, 19.781), "jupiter": (143.37, 15.157),
        "saturn": (10.711, 1.655), "uranus": (63.052, 20.971), "neptune": (2.62, -0.412)},
    datetime(2027, 3, 21, 12, 0, tzinfo=timezone.utc): {
        "sun": (0.24, 0.104), "moon": (167.809, 2.578), "mercury": (335.535, -11.792),
        "venus": (326.259, -14.009), "mars": (144.931, 17.858), "jupiter": (140.186, 16.629),
        "saturn": (14.802, 3.891), "uranus": (59.954, 20.445), "neptune": (3.812, 0.182)},
    datetime(2030, 7, 4, 6, 0, tzinfo=timezone.utc): {
        "sun": (102.946, 22.902), "moon": (141.067, 10.273), "mercury": (115.612, 23.249),
        "venus": (72.366, 21.23), "mars": (91.461, 24.079), "jupiter": (225.345, -16.064),
        "saturn": (61.956, 19.05), "uranus": (78.755, 23.094), "neptune": (12.469, 3.698)},
}


def _separation_deg(a, b):
    ra1, dec1, ra2, dec2 = (math.radians(v) for v in (*a, *b))
    cos = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


@pytest.mark.parametrize("when", list(REFERENCE))
def test_positions_match_the_reference_ephemeris(when):
    """Planetas e Sol dentro de 0,15 grau; a Lua (série curta) dentro de 0,6 grau."""
    for body, expected in REFERENCE[when].items():
        got = ephem.body_radec(body, when)
        limit = 0.6 if body == "moon" else 0.15
        assert _separation_deg(got, expected) < limit, (body, got, expected)


def test_unknown_body_is_none_and_earth_is_not_a_target():
    when = next(iter(REFERENCE))
    assert ephem.body_radec("plutao", when) is None
    assert ephem.body_radec("earth", when) is None


def test_moon_phase_goes_from_new_to_full():
    """2026-10-10: Lua a 8 graus do Sol (quase nova). 2026-10-26: cheia."""
    assert ephem.moon(datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc))["phase"] < 0.03
    assert ephem.moon(datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc))["phase"] > 0.97


def test_bodies_lists_what_is_up_for_the_observer():
    """São Paulo, 22h30 de 9 de outubro de 2026: Saturno alto no céu, o Sol bem abaixo do
    horizonte."""
    when = datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc)
    rows = {b["id"]: b for b in ephem.bodies(-23.55, -46.63, when)}
    assert list(rows) == ["moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "sun"]
    assert rows["saturn"]["up"] and rows["saturn"]["alt_deg"] > 40
    assert not rows["sun"]["up"] and rows["sun"]["alt_deg"] < -40
    assert rows["moon"]["phase"] is not None and rows["mars"]["phase"] is None
    assert rows["sun"]["kind"] == "sun" and rows["moon"]["name"] == "Lua"


def test_moon_altitude_includes_parallax():
    """Vista da superfície a Lua fica até 1 grau mais baixa que vista do centro da Terra."""
    from src.core.catalog import _alt_from_radec
    when = datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc)
    m = ephem.moon(when)
    geocentric = float(_alt_from_radec(m["ra_deg"], m["dec_deg"], -23.55, -46.63, when))
    seen = next(b for b in ephem.bodies(-23.55, -46.63, when) if b["id"] == "moon")["alt_deg"]
    assert 0.0 < geocentric - seen < 1.1
