#!/usr/bin/env python3
"""Publica um APELIDO mDNS para esta máquina: `telescopio.local`, sem mudar o nome dela.

A Jetson continua se chamando como sempre; este serviço só acrescenta um segundo nome na rede,
para o console abrir por `http://telescopio.local` sem ninguém digitar IP.

O apelido é publicado como registros de ENDEREÇO (A), um por interface de rede, entregues ao
avahi-daemon pelo D-Bus — não como CNAME. Um CNAME seria mais simples (seguiria o nome da
máquina sozinho), mas foi testado e o resolvedor mDNS do Windows o ignora; registro A todo
aparelho entende. O preço é acompanhar os IPs: a cada poucos segundos o serviço confere os
endereços e republica se mudaram (DHCP novo, hotspot do campo, cabo de rede plugado).

    telescope_mdns_alias.py [apelido]          (padrão: telescopio)

Roda como serviço (deploy/jetson/telescope-mdns.service). Se o avahi reiniciar, o registro
some junto: o processo percebe, sai com erro e o systemd o sobe de novo.
"""
import json
import re
import subprocess
import sys
import time

PROTO_UNSPEC = -1                                # anuncia por mDNS IPv4 e IPv6
PUBLISH_NO_REVERSE = 16                          # sem PTR reverso: o IP já pertence ao nome real
GROUP_COLLISION, GROUP_FAILURE = 3, 4            # estados do EntryGroup do avahi
CHECK_EVERY_S = 10
# Interfaces que não são rede de verdade para um celular: laço, pontes e túneis virtuais.
SKIP_PREFIXES = ("lo", "docker", "veth", "br-", "virbr", "tailscale", "tun", "tap", "can")


def alias_fqdn(alias: str) -> str:
    """`telescopio` -> `telescopio.local`. Aceita só um rótulo DNS simples."""
    a = alias.strip().lower()
    if a.endswith(".local"):
        a = a[:-len(".local")]
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", a):
        raise ValueError(f"apelido inválido: {alias!r} (use letras, números e hífen)")
    return a + ".local"


def pick_addresses(ip_json: str) -> list:
    """Da saída de `ip -j -4 addr show scope global`, os pares (índice da interface, IPv4) em
    que o apelido deve ser anunciado. Cada endereço sai só na própria interface: quem pergunta
    pelo WiFi recebe o IP do WiFi."""
    out = []
    for itf in json.loads(ip_json or "[]"):
        name = itf.get("ifname", "")
        if name.startswith(SKIP_PREFIXES):
            continue
        for a in itf.get("addr_info", []):
            if a.get("family") == "inet" and a.get("local"):
                out.append((int(itf["ifindex"]), a["local"]))
    return sorted(out)


def current_addresses() -> list:
    r = subprocess.run(["ip", "-j", "-4", "addr", "show", "scope", "global"],
                       capture_output=True, text=True, timeout=10)
    return pick_addresses(r.stdout)


def publish(dbus, group, alias: str, addresses: list) -> None:
    """Troca o que está publicado por `addresses` (lista vazia = nada publicado)."""
    group.Reset()
    for ifindex, addr in addresses:
        group.AddAddress(dbus.Int32(ifindex), dbus.Int32(PROTO_UNSPEC),
                         dbus.UInt32(PUBLISH_NO_REVERSE), alias, addr)
    if addresses:
        group.Commit()


def main(argv) -> int:
    import dbus                                  # python3-dbus: só existe na Jetson

    alias = alias_fqdn(argv[1] if len(argv) > 1 else "telescopio")
    try:
        bus = dbus.SystemBus()
        server = dbus.Interface(bus.get_object("org.freedesktop.Avahi", "/"),
                                "org.freedesktop.Avahi.Server")
        if str(server.GetHostNameFqdn()) == alias:
            print(f"mDNS: a máquina já se chama {alias}; nada a publicar", flush=True)
            return 0
        group = dbus.Interface(bus.get_object("org.freedesktop.Avahi", server.EntryGroupNew()),
                               "org.freedesktop.Avahi.EntryGroup")
        published = None
        while True:
            addresses = current_addresses()
            if addresses != published:
                publish(dbus, group, alias, addresses)
                published = addresses
                print(f"mDNS: {alias} -> {[a for _, a in addresses] or 'sem rede'}", flush=True)
            time.sleep(CHECK_EVERY_S)
            if int(group.GetState()) in (GROUP_COLLISION, GROUP_FAILURE):
                print(f"mDNS: o avahi recusou {alias} (outro aparelho com esse nome na rede?)",
                      flush=True)
                return 1
    except dbus.DBusException as e:              # avahi reiniciou ou não está no ar
        print(f"mDNS: avahi indisponível ({e.get_dbus_name()}); o systemd tenta de novo",
              flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
