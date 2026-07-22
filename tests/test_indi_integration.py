"""T13 — integração com o indiserver REAL + drivers indi_simulator_* (WSL/Jetson).

NÃO roda no CI/Windows (marcado `hardware`): exige um indiserver de verdade no ar. Para rodar:

    # no WSL/Linux/Jetson (ver scripts/run_indi_sim.sh):
    indiserver -v indi_simulator_telescope indi_simulator_focus \\
                  indi_simulator_wheel indi_simulator_ccd &
    # depois, apontando o cliente para ele:
    INDI_HOST=127.0.0.1 py -3.11 -m pytest tests/test_indi_integration.py -m hardware -v

Valida que os MESMOS adapters do CI falam com o driver real — a ponte final antes da câmera.
"""
import os
import socket

import numpy as np
import pytest

from src.io.indi_client import IndiClient
from src.capture.indi_source import IndiCameraSource
from src.control.mount import IndiMount
from src.control.focuser import IndiFocuser
from src.control.filterwheel import IndiFilterWheel

HOST = os.environ.get("INDI_HOST", "127.0.0.1")
PORT = int(os.environ.get("INDI_PORT", "7624"))


def _reachable(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _reachable(HOST, PORT),
                       reason=f"indiserver não acessível em {HOST}:{PORT} (suba os simuladores)"),
]


@pytest.fixture
def client():
    cli = IndiClient(HOST, PORT).connect()
    cli.get_properties()
    yield cli
    cli.close()


def test_real_ccd_delivers_frame(client):
    cam = IndiCameraSource(device="CCD Simulator", host=HOST, port=PORT,
                           exposure_s=1.0, client=client)
    frame, meta = cam.read()
    assert frame.ndim >= 2 and np.isfinite(frame).all()


def test_real_mount_slew(client):
    m = IndiMount(device="Telescope Simulator", client=client).connect()
    ra, dec = m.slew_radec(3.0, 20.0, timeout=90)
    assert abs(ra - 3.0) < 0.2 and abs(dec - 20.0) < 0.5


def test_real_focuser_move(client):
    f = IndiFocuser(device="Focuser Simulator", client=client).connect()
    f.move_to(15000, timeout=60)
    assert abs(f.position() - 15000) < 200


def test_real_filterwheel(client):
    w = IndiFilterWheel(device="Filter Simulator", client=client).connect()
    names = w.names()
    assert names
    w.set(names[-1])
    assert w.current() == names[-1]
