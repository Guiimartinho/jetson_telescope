"""Link automático Jetson -> controladora da montagem (OnStepX pela serial USB, via INDI).

Papéis: a Jetson é o cérebro (vê, decide, sabe a hora e o lugar); a placa é o músculo (pulsos
de passo em tempo real). Estes testes cobrem o que faz o link funcionar SOZINHO: configurar a
serial, conectar, enviar hora e local, e reconectar quando o cabo sai e volta. Rodam contra o
servidor INDI falso (tests/fake_indi.py), que imita o `indi_lx200_OnStep`. Ver docs/35.
"""
import time
from datetime import datetime, timezone

import pytest

from src.control.mount import IndiMount
from src.control.mount_link import MountLink, mount_link_from_env
from src.io.indi_client import IndiClient
from tests.fake_indi import ONSTEP, FakeIndiServer

SP = (-23.55, -46.63, 760.0)                                   # São Paulo
T0 = datetime(2026, 10, 9, 19, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def server():
    srv = FakeIndiServer().start()
    yield srv
    srv.stop()


def _wait(cond, timeout=2.0):
    """Espera `cond()` virar verdade (eventos de socket não são instantâneos)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _mount(server, **kw):
    kw.setdefault("serial_port", "/dev/telescope-mount")
    kw.setdefault("baud", 115200)
    return IndiMount(device=ONSTEP, host="127.0.0.1", port=server.port, connect_timeout=3.0, **kw)


# ---- IndiClient: o que o link precisa saber -------------------------------
def test_client_knows_when_the_server_is_gone(server):
    cli = IndiClient("127.0.0.1", server.port).connect()
    assert cli.alive
    server.stop()
    assert _wait(lambda: not cli.alive), "o cliente tem de perceber o socket fechado (indiserver caiu)"
    cli.close()


# ---- IndiMount: a serial tem de ser configurada antes do CONNECT -----------
def test_mount_configures_serial_port_and_baud_then_connects(server):
    """O INDI abre a serial a 9600 em /dev/ttyUSB0 por padrão; o firmware fala a 115200 e a
    placa tem nome fixo. Sem configurar os dois, não conecta."""
    m = _mount(server).connect()
    assert server.onstep["port"] == "/dev/telescope-mount"
    assert server.onstep["baud"] == "115200"
    assert m.is_connected()
    ra_h, dec = m.get_radec()
    assert ra_h == pytest.approx(12.77) and dec == pytest.approx(90.0)     # casa da GEM
    m.close()


def test_mount_with_wrong_baud_fails_loudly(server):
    """Regressão do bring-up: a 9600 o handshake LX200 não responde. Tem de virar um erro
    claro, na hora — não um timeout mudo nem uma montagem "conectada" que não obedece."""
    m = _mount(server, baud=9600)
    with pytest.raises(ConnectionError, match="9600"):
        m.connect()
    assert not m.is_connected()
    m.close()


def test_mount_rejects_a_baud_the_driver_does_not_offer(server):
    m = _mount(server, baud=12345)
    with pytest.raises(ValueError, match="12345"):
        m.connect()
    m.close()


def test_mount_recovers_after_a_failed_attempt(server):
    """Um Alert antigo não pode envenenar a tentativa seguinte."""
    ruim = _mount(server, baud=9600)
    with pytest.raises(ConnectionError):
        ruim.connect()
    ruim.close()
    bom = _mount(server).connect()
    assert bom.is_connected()
    bom.close()


def test_second_client_reuses_a_device_already_connected(server):
    """Dois processos (console e painel) falam com o mesmo indiserver: o segundo encontra o
    dispositivo já conectado e não pode derrubá-lo nem reconectá-lo."""
    a = _mount(server).connect()
    b = _mount(server).connect()
    assert server.onstep["connects"] == 1
    assert b.get_radec()[1] == pytest.approx(90.0)
    a.close()
    b.close()


# ---- hora e local: quem sabe é a Jetson -----------------------------------
def test_mount_receives_site_and_utc_time(server):
    """O OnStepX acorda em 2000-01-01, lat/long 0 (sem GPS/RTC). Sem hora e local um goto
    por RA/DEC aponta para o lugar errado."""
    m = _mount(server).connect()
    assert server.onstep["utc"].startswith("2000-01-01")
    m.set_site_and_time(*SP, when=T0)
    lat, lon, elev = server.onstep["site"]
    assert lat == pytest.approx(-23.55) and elev == pytest.approx(760.0)
    assert lon == pytest.approx(313.37), "o INDI quer longitude 0..360 a LESTE"
    assert server.onstep["utc"] == "2026-10-09T19:30:00"
    m.close()


def test_time_must_be_timezone_aware(server):
    """Hora ingênua é ambígua (local ou UTC?) e erraria o tempo sideral em horas."""
    m = _mount(server).connect()
    with pytest.raises(ValueError, match="UTC"):
        m.set_site_and_time(*SP, when=datetime(2026, 10, 9, 16, 30, 0))
    m.close()


# ---- MountLink: o link que se mantém sozinho ------------------------------
def _link(server, port=None, **kw):
    port = port or server.port
    return MountLink(lambda: IndiMount(device=ONSTEP, host="127.0.0.1", port=port,
                                       connect_timeout=3.0, serial_port="/dev/telescope-mount",
                                       baud=115200).connect(),
                     site=SP, now=lambda: T0, **kw)


def test_link_connects_and_pushes_site_and_time_by_itself(server):
    link = _link(server)
    st = link.poll_once()
    assert st["connected"] is True and st["error"] is None
    assert st["ra_deg"] == pytest.approx(12.77 * 15.0) and st["dec_deg"] == pytest.approx(90.0)
    assert server.onstep["utc"] == "2026-10-09T19:30:00"
    assert server.onstep["site"][0] == pytest.approx(-23.55)
    link.stop()


def test_link_without_server_reports_and_never_raises():
    """Placa desplugada = indiserver parado. O link fica tentando; a UI mostra o motivo."""
    link = MountLink(lambda: IndiMount(device=ONSTEP, host="127.0.0.1", port=1,
                                       connect_timeout=0.5).connect(), site=SP)
    st = link.poll_once()
    assert st["connected"] is False
    assert st["error"]
    assert link.mount is None
    link.stop()


def test_link_survives_unplug_and_replug():
    """O cabo sai (indiserver morre), o cabo volta (indiserver novo, placa sem hora de novo):
    o link percebe, reconecta e reenvia hora e local, sem ninguém pedir."""
    srv = FakeIndiServer().start()
    port = srv.port
    link = _link(srv)
    assert link.poll_once()["connected"] is True

    srv.stop()                                               # cabo tirado
    assert _wait(lambda: link.poll_once()["connected"] is False), (
        "o link tem de perceber que a montagem sumiu")

    srv2 = FakeIndiServer(port=port).start()                 # cabo de volta
    try:
        assert srv2.onstep["utc"].startswith("2000-01-01")
        st = link.poll_once()
        assert st["connected"] is True and st["connections"] == 2
        assert srv2.onstep["utc"] == "2026-10-09T19:30:00"   # hora reenviada
        assert srv2.onstep["site_pushes"] == 1               # local reenviado
    finally:
        link.stop()
        srv2.stop()


def test_link_thread_connects_in_background(server):
    link = _link(server, period_s=0.05)
    link.start()
    try:
        assert _wait(lambda: link.status()["connected"], timeout=3.0)
    finally:
        link.stop()


# ---- configuração por ambiente (o serviço da Jetson liga; PC e CI ficam no simulador) ----
def test_link_is_off_unless_explicitly_enabled():
    assert mount_link_from_env({}) is None
    assert mount_link_from_env({"TELE_MOUNT": "sim"}) is None


def test_link_from_env_uses_the_fixed_device_name(server):
    link = mount_link_from_env({"TELE_MOUNT": "indi", "TELE_INDI_HOST": "127.0.0.1",
                                "TELE_INDI_PORT": str(server.port),
                                "TELE_SITE": "-23.55,-46.63,760"})
    assert link is not None and link.site == pytest.approx(SP)
    assert link.poll_once()["connected"] is True
    assert server.onstep["port"] == "/dev/telescope-mount"   # padrão: o nome fixo do udev
    assert server.onstep["baud"] == "115200"                 # padrão: o baud do firmware
    link.stop()


def test_link_from_env_rejects_a_bad_site():
    with pytest.raises(ValueError, match="TELE_SITE"):
        mount_link_from_env({"TELE_MOUNT": "indi", "TELE_SITE": "aqui"})
