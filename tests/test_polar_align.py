"""Alinhamento polar por três pontos (src/control/polar_align.py): geometria pura."""
import math

import pytest

from src.control import polar_align as pa


def _measure(sim, rotations=(0.0, 30.0, 60.0)):
    return pa.polar_error([sim.solve(r) for r in rotations], sim.lat)


@pytest.mark.parametrize("lat", [-23.55, 40.4, -51.0, 12.0])
@pytest.mark.parametrize("alt_err,az_err", [(38.0, -52.0), (-15.0, 22.0), (0.0, 90.0), (120.0, 0.0)])
def test_recovers_the_error_in_both_hemispheres(lat, alt_err, az_err):
    """Monta um eixo desalinhado, "fotografa" três posições e confere que a conta devolve o
    erro que foi posto — ao norte e ao sul do equador."""
    sim = pa.SimPolarAxis(lat_deg=lat, alt_err_arcmin=alt_err, az_err_arcmin=az_err, noise_arcmin=0.0)
    error = _measure(sim)
    assert error.alt_arcmin == pytest.approx(alt_err, abs=0.05)
    assert error.az_arcmin == pytest.approx(az_err, abs=0.05)
    assert error.total_arcmin == pytest.approx(math.hypot(alt_err, az_err), abs=0.05)


@pytest.mark.parametrize("lat", [-23.55, 40.4])
def test_the_side_it_names_is_the_side_on_the_ground(lat):
    """O lado tem de ser o da bússola, nos DOIS hemisférios. O azimute cresce do norte para o
    leste; por isso, ao sul (polo em 180 graus), um eixo em 179 está a LESTE do polo, e ao norte
    (polo em 0) quem está a leste é o eixo em 1 grau. O eixo aqui é posto direto no céu do
    observador, sem passar pela convenção do simulador."""
    pole_alt, pole_az = pa.pole_altaz(lat)
    toward_east = -1.0 if lat < 0 else 1.0            # para que lado do azimute fica o leste

    def measure(alt_deg, az_deg):
        sim = pa.SimPolarAxis(lat_deg=lat, noise_arcmin=0.0)
        sim.axis = lambda: pa.from_horizontal(alt_deg, az_deg, lat)
        return _measure(sim)

    east = measure(pole_alt, pole_az + toward_east * 1.0)
    assert east.az_arcmin == pytest.approx(60.0 * math.cos(math.radians(pole_alt)), abs=0.05), "a leste: positivo"
    assert east.alt_arcmin == pytest.approx(0.0, abs=0.6)
    west = measure(pole_alt, pole_az - toward_east * 1.0)
    assert west.az_arcmin == pytest.approx(-60.0 * math.cos(math.radians(pole_alt)), abs=0.05), "a oeste: negativo"
    high = measure(pole_alt + 0.5, pole_az)
    assert high.alt_arcmin == pytest.approx(30.0, abs=0.05) and abs(high.az_arcmin) < 0.05, "alto demais: positivo"
    low = measure(pole_alt - 0.5, pole_az)
    assert low.alt_arcmin == pytest.approx(-30.0, abs=0.05)


@pytest.mark.parametrize("lat", [-23.55, 40.4])
def test_the_simulated_screws_turn_the_way_the_app_says(lat):
    """"Mais azimute gira para leste; mais altitude sobe o eixo": é o que a tela do app diz dos
    parafusos da montagem simulada, e tem de ser verdade no céu."""
    sim = pa.SimPolarAxis(lat_deg=lat, alt_err_arcmin=0.0, az_err_arcmin=0.0, noise_arcmin=0.0)
    sim.rng = type("Firme", (), {"uniform": staticmethod(lambda a, b: 1.0)})()   # sem a folga da mão
    sim.adjust(0.0, 30.0)
    alt, az = pa._to_horizontal(sim.axis(), lat)
    pole_alt, pole_az = pa.pole_altaz(lat)
    # ao sul o polo está em 180 graus, e o leste fica do lado do azimute menor
    assert (az < pole_az) if lat < 0 else (az > pole_az), "mais azimute: para leste"
    assert alt == pytest.approx(pole_alt, abs=0.01)
    sim.adjust(20.0, 0.0)
    assert pa._to_horizontal(sim.axis(), lat)[0] == pytest.approx(pole_alt + 20.0 / 60.0, abs=0.01)


def test_an_aligned_mount_reads_zero_and_says_so():
    error = _measure(pa.SimPolarAxis(alt_err_arcmin=0.0, az_err_arcmin=0.0, noise_arcmin=0.0))
    assert error.total_arcmin < 0.01 and error.aligned
    assert error.as_dict() == {"alt_arcmin": 0.0, "az_arcmin": 0.0, "total_arcmin": 0.0, "aligned": True}
    assert not _measure(pa.SimPolarAxis(noise_arcmin=0.0)).aligned


def test_measurement_noise_costs_about_an_arcminute_not_more():
    """Com o ruído de um plate solve de verdade (0,15') e 90 graus de giro, o erro medido fica
    a ~1' do real. Com menos giro o círculo fica mal definido e o ruído pesa mais: por isso o
    Controller gira 45 graus entre os pontos."""
    worst_wide, worst_narrow = 0.0, 0.0
    for seed in range(12):
        for rotations, is_wide in (((0.0, 45.0, 90.0), True), ((0.0, 15.0, 30.0), False)):
            sim = pa.SimPolarAxis(noise_arcmin=0.15, seed=seed)
            error = _measure(sim, rotations)
            miss = max(abs(error.alt_arcmin - sim.alt_err), abs(error.az_arcmin - sim.az_err))
            if is_wide:
                worst_wide = max(worst_wide, miss)
            else:
                worst_narrow = max(worst_narrow, miss)
    assert worst_wide < 1.5, worst_wide
    assert worst_narrow > worst_wide, "girar pouco mede pior"


def test_adjusting_the_screws_converges():
    """O uso de verdade: mede, corrige o que a conta mandou, mede de novo — até alinhar."""
    sim = pa.SimPolarAxis(seed=3)
    error = _measure(sim)
    assert error.total_arcmin > 60
    for _ in range(4):
        if error.aligned:
            break
        sim.adjust(-error.alt_arcmin, -error.az_arcmin)
        error = _measure(sim)
    assert error.aligned, error


def test_points_too_close_do_not_pretend_to_measure():
    sim = pa.SimPolarAxis(noise_arcmin=0.0)
    assert _measure(sim, rotations=(0.0, 1.0, 2.0)) is None
    assert pa.polar_error([sim.solve(0.0), sim.solve(30.0)], sim.lat) is None
    same = sim.solve(10.0)
    assert pa.polar_error([same, same, same], sim.lat) is None


def test_the_visible_pole_is_south_below_the_equator():
    assert pa.pole_altaz(-23.55) == (23.55, 180.0)
    assert pa.pole_altaz(40.0) == (40.0, 0.0)
    # o vetor do polo no referencial preso à Terra é o eixo z, com o sinal do hemisfério
    north = pa.from_horizontal(40.0, 0.0, 40.0)
    south = pa.from_horizontal(23.55, 180.0, -23.55)
    assert north == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)
    assert south == pytest.approx([0.0, 0.0, -1.0], abs=1e-9)
