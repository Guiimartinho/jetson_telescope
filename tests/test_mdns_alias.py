"""Apelido na rede (`telescopio.local`) — deploy/jetson/telescope_mdns_alias.py.

A Jetson não muda de nome; registros de endereço (A) no avahi acrescentam o apelido, um por
interface. Estes testes cobrem o que é puro (validação, escolha de interfaces) e a conversa
com o avahi contra um D-Bus falso — o `python3-dbus` real só existe na Jetson.
"""
import importlib.util
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy", "jetson", "telescope_mdns_alias.py")

# o que a Orin devolve em `ip -j -4 addr show scope global` (WiFi no roteador + ponte do docker)
IP_JSON = json.dumps([
    {"ifindex": 4, "ifname": "wlP1p1s0",
     "addr_info": [{"family": "inet", "local": "192.168.3.221", "prefixlen": 24}]},
    {"ifindex": 5, "ifname": "docker0",
     "addr_info": [{"family": "inet", "local": "172.17.0.1", "prefixlen": 16}]},
])


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("telescope_mdns_alias", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_alias_becomes_a_dot_local_name(mod):
    assert mod.alias_fqdn("telescopio") == "telescopio.local"
    assert mod.alias_fqdn("Telescopio.local") == "telescopio.local"


@pytest.mark.parametrize("ruim", ["", "tele scopio", "a.b", "-x", "x-", "telescópio", "x" * 64])
def test_invalid_alias_is_rejected(mod, ruim):
    with pytest.raises(ValueError):
        mod.alias_fqdn(ruim)


def test_alias_is_announced_on_real_networks_only(mod):
    """Regressão do bring-up: o avahi anuncia o nome da máquina também na ponte do docker
    (172.17.0.1). Um celular que recebesse esse endereço não chegaria a lugar nenhum."""
    assert mod.pick_addresses(IP_JSON) == [(4, "192.168.3.221")]


def test_ethernet_and_hotspot_addresses_are_all_announced(mod):
    js = json.dumps([
        {"ifindex": 2, "ifname": "eno1", "addr_info": [{"family": "inet", "local": "10.0.0.5"}]},
        {"ifindex": 4, "ifname": "wlP1p1s0", "addr_info": [{"family": "inet", "local": "10.42.0.1"}]},
        {"ifindex": 1, "ifname": "lo", "addr_info": [{"family": "inet", "local": "127.0.0.1"}]},
    ])
    assert mod.pick_addresses(js) == [(2, "10.0.0.5"), (4, "10.42.0.1")]
    assert mod.pick_addresses("") == []                       # sem rede: nada a anunciar


class _FakeAvahi:
    """O bastante do avahi no D-Bus: registra cada publicação e, depois de `ok_checks`
    verificações, "falha" — para o laço de vigilância sair."""
    def __init__(self, hostname="jetson-super.local", ok_checks=0):
        self.hostname, self.ok_checks = hostname, ok_checks
        self.addresses, self.commits, self.resets = [], 0, 0

    def GetHostNameFqdn(self):
        return self.hostname

    def EntryGroupNew(self):
        return "/Client0/EntryGroup1"

    def Reset(self):
        self.resets += 1
        self.addresses = []

    def AddAddress(self, *args):
        self.addresses.append(args)

    def Commit(self):
        self.commits += 1

    def GetState(self):
        self.ok_checks -= 1
        return 2 if self.ok_checks >= 0 else 4      # ESTABLISHED ... depois FAILURE


def _fake_dbus(avahi):
    d = types.ModuleType("dbus")
    d.DBusException = type("DBusException", (Exception,), {"get_dbus_name": lambda self: "x"})
    d.SystemBus = lambda: types.SimpleNamespace(get_object=lambda name, path: avahi)
    d.Interface = lambda obj, iface: obj
    d.Int32 = d.UInt32 = int
    return d


def test_publishes_an_address_record_per_interface(mod, monkeypatch):
    avahi = _FakeAvahi()
    monkeypatch.setitem(sys.modules, "dbus", _fake_dbus(avahi))
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "current_addresses", lambda: mod.pick_addresses(IP_JSON))
    assert mod.main(["prog", "telescopio"]) == 1               # saiu pelo "FAILURE" do falso
    assert avahi.commits == 1
    ifindex, proto, flags, name, addr = avahi.addresses[0]
    assert (ifindex, name, addr) == (4, "telescopio.local", "192.168.3.221")
    assert flags == mod.PUBLISH_NO_REVERSE, "o IP já tem PTR reverso do nome real da máquina"


def test_republishes_when_the_address_changes(mod, monkeypatch):
    """DHCP novo, ou a Jetson virou hotspot no campo: o apelido tem de seguir o IP."""
    avahi = _FakeAvahi(ok_checks=2)
    respostas = iter([[(4, "192.168.3.221")], [(4, "192.168.3.221")], [(4, "10.42.0.1")]])
    monkeypatch.setitem(sys.modules, "dbus", _fake_dbus(avahi))
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "current_addresses", lambda: next(respostas))
    assert mod.main(["prog", "telescopio"]) == 1
    assert avahi.commits == 2, "publica na 1ª vez e de novo só quando o IP muda"
    assert avahi.addresses[-1][-1] == "10.42.0.1"


def test_nothing_to_publish_when_the_machine_already_has_that_name(mod, monkeypatch):
    avahi = _FakeAvahi(hostname="telescopio.local")
    monkeypatch.setitem(sys.modules, "dbus", _fake_dbus(avahi))
    assert mod.main(["prog", "telescopio"]) == 0
    assert avahi.addresses == []
