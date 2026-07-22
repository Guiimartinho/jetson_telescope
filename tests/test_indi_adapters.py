"""T13 — adapters INDI (câmera/montagem/foco/filtro) contra o servidor INDI falso.

Exercita a FRONTEIRA de hardware inteira sem nada de INDI instalado (roda no Windows/CI). Os mesmos
adapters, na Jetson, conectam ao indiserver real (drivers reais OU indi_simulator_*). Ver docs/20.
"""
import numpy as np
import pytest

from src.capture.indi_source import IndiCameraSource
from src.control.mount import IndiMount
from src.control.focuser import IndiFocuser
from src.control.filterwheel import IndiFilterWheel
from src.io.indi_client import IndiClient
from tests.fake_indi import FakeIndiServer


@pytest.fixture
def server():
    srv = FakeIndiServer().start()
    yield srv
    srv.stop()


@pytest.fixture
def client(server):
    cli = IndiClient("127.0.0.1", server.port).connect()
    yield cli
    cli.close()


def test_camera_reads_frame(client):
    cam = IndiCameraSource(device="CCD Simulator", exposure_s=0.1, client=client)
    frame, meta = cam.read()
    assert frame.dtype == np.float32 and frame.ndim == 2
    assert frame.max() > 50000                    # a "estrela" do FITS
    assert meta["kind"] == "camera"


def test_camera_reuses_out_buffer(client):
    cam = IndiCameraSource(device="CCD Simulator", exposure_s=0.1, client=client)
    f1, _ = cam.read()
    out = np.empty_like(f1)
    f2, _ = cam.read(out=out)
    assert f2 is out                               # escreveu no buffer fornecido


def test_mount_slew_sets_radec(client):
    m = IndiMount(device="Telescope Simulator", client=client).connect()
    ra, dec = m.slew_radec(5.5, -12.0)
    assert ra == pytest.approx(5.5) and dec == pytest.approx(-12.0)


def test_mount_pixel_api_is_rejected(client):
    m = IndiMount(device="Telescope Simulator", client=client).connect()
    with pytest.raises(NotImplementedError):
        m.slew(100, 100)                           # pixels são conceito do simulador


def test_focuser_moves(client):
    f = IndiFocuser(device="Focuser Simulator", client=client).connect()
    assert f.move_to(7200) == 7200
    assert f.position() == 7200


def test_filterwheel_lists_and_switches(client):
    w = IndiFilterWheel(device="Filter Simulator", client=client).connect()
    assert w.names() == ["VIS", "L-Pro", "L-eXtreme"]
    w.set("L-eXtreme")
    assert w.current() == "L-eXtreme"


def test_filterwheel_rejects_unknown(client):
    w = IndiFilterWheel(device="Filter Simulator", client=client).connect()
    with pytest.raises(ValueError):
        w.set("Ha-3nm")


def test_own_client_lifecycle(server):
    """Adapter que cria o próprio cliente (host/port) e o fecha em close()."""
    f = IndiFocuser(device="Focuser Simulator", host="127.0.0.1", port=server.port).connect()
    assert f.move_to(3000) == 3000
    f.close()
