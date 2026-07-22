"""T13 — cliente INDI puro-Python contra o servidor INDI falso (roda no Windows/CI)."""
import io

import numpy as np
import pytest

from src.io.indi_client import IndiClient, _sexagesimal
from tests.fake_indi import FakeIndiServer


@pytest.fixture
def server():
    srv = FakeIndiServer().start()
    yield srv
    srv.stop()


@pytest.fixture
def client(server):
    cli = IndiClient("127.0.0.1", server.port).connect()
    cli.get_properties()
    yield cli
    cli.close()


def test_defines_properties(client):
    p = client.wait_vector("Telescope Simulator", "EQUATORIAL_EOD_COORD", timeout=5)
    assert p.kind == "Number"
    assert set(p.elements) == {"RA", "DEC"}
    assert "Focuser Simulator" in client.devices()
    assert "CCD Simulator" in client.devices()


def test_connect_device_sets_state_ok(client):
    client.wait_vector("Telescope Simulator", "CONNECTION", timeout=5)
    client.send_switch("Telescope Simulator", "CONNECTION", on="CONNECT", off=["DISCONNECT"])
    p = client.wait_state("Telescope Simulator", "CONNECTION", "Ok", timeout=5)
    assert p.elements.get("CONNECT") == "On"


def test_send_number_slew_echoes_values(client):
    client.wait_vector("Telescope Simulator", "EQUATORIAL_EOD_COORD", timeout=5)
    client.send_number("Telescope Simulator", "EQUATORIAL_EOD_COORD", {"RA": 5.5, "DEC": -12.0})
    p = client.wait_state("Telescope Simulator", "EQUATORIAL_EOD_COORD", "Ok", timeout=5)
    assert p.elements["RA"] == pytest.approx(5.5)
    assert p.elements["DEC"] == pytest.approx(-12.0)


def test_blob_delivers_fits(client):
    from astropy.io import fits
    client.wait_vector("CCD Simulator", "CCD_EXPOSURE", timeout=5)
    client.enable_blob("CCD Simulator")
    client.clear_blob()
    client.send_number("CCD Simulator", "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1.0})
    blob = client.wait_blob(timeout=10)
    assert blob["format"] == ".fits" and len(blob["data"]) > 0
    with fits.open(io.BytesIO(blob["data"])) as hdul:
        arr = np.asarray(hdul[0].data)
    assert arr.max() > 50000                     # a "estrela" do FITS sintético


def test_sexagesimal_parser():
    assert _sexagesimal("12:30:00") == pytest.approx(12.5)
    assert _sexagesimal("-05:30:00") == pytest.approx(-5.5)
