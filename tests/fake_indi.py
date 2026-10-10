"""Servidor INDI FALSO (test double) — fala um subconjunto do protocolo INDI sobre TCP.

Permite testar o `IndiClient` e os adapters INDI na CI (Windows, sem INDI instalado). Imita os
drivers `indi_simulator_*`: define as MESMAS propriedades (EQUATORIAL_EOD_COORD, ABS_FOCUS_POSITION,
FILTER_SLOT, CCD_EXPOSURE→BLOB FITS) e responde a newXxxVector com setXxxVector (Busy→Ok).
Não é o INDI real — é o suficiente para exercitar a fronteira. Ver docs/20.
"""
from __future__ import annotations

import base64
import io
import socket
import threading
import time
import xml.etree.ElementTree as ET

import numpy as np


def _tiny_fits(w=32, h=24, seed=0) -> bytes:
    """Um FITS mono minúsculo (16-bit) com uma 'estrela' — imita o BLOB do CCD Simulator."""
    from astropy.io import fits
    rng = np.random.default_rng(seed)
    img = rng.integers(80, 120, size=(h, w)).astype(np.uint16)
    img[h // 2, w // 2] = 60000
    buf = io.BytesIO()
    fits.PrimaryHDU(data=img).writeto(buf)
    return buf.getvalue()


# Catálogo de propriedades que o servidor "define" ao receber <getProperties>.
def _catalog() -> str:
    T = "Telescope Simulator"
    F = "Focuser Simulator"
    W = "Filter Simulator"
    C = "CCD Simulator"

    def conn(dev):
        return (f'<defSwitchVector device="{dev}" name="CONNECTION" state="Idle" perm="rw" '
                f'rule="OneOfMany">'
                f'<defSwitch name="CONNECT">Off</defSwitch>'
                f'<defSwitch name="DISCONNECT">On</defSwitch></defSwitchVector>')

    out = [conn(T), conn(F), conn(W), conn(C)]
    out.append(
        f'<defNumberVector device="{T}" name="EQUATORIAL_EOD_COORD" state="Idle" perm="rw">'
        f'<defNumber name="RA" format="%10.6m" min="0" max="24">0</defNumber>'
        f'<defNumber name="DEC" format="%10.6m" min="-90" max="90">0</defNumber>'
        f'</defNumberVector>')
    out.append(
        f'<defSwitchVector device="{T}" name="ON_COORD_SET" state="Idle" perm="rw" rule="OneOfMany">'
        f'<defSwitch name="TRACK">On</defSwitch>'
        f'<defSwitch name="SLEW">Off</defSwitch>'
        f'<defSwitch name="SYNC">Off</defSwitch></defSwitchVector>')
    out.append(
        f'<defSwitchVector device="{T}" name="TELESCOPE_ABORT_MOTION" state="Idle" perm="rw" '
        f'rule="AtMostOne"><defSwitch name="ABORT">Off</defSwitch></defSwitchVector>')
    out.append(
        f'<defNumberVector device="{F}" name="ABS_FOCUS_POSITION" state="Idle" perm="rw">'
        f'<defNumber name="FOCUS_ABSOLUTE_POSITION" format="%.0f" min="0" max="60000">'
        f'5000</defNumber></defNumberVector>')
    out.append(
        f'<defNumberVector device="{W}" name="FILTER_SLOT" state="Idle" perm="rw">'
        f'<defNumber name="FILTER_SLOT_VALUE" format="%.0f" min="1" max="3">1</defNumber>'
        f'</defNumberVector>')
    out.append(
        f'<defTextVector device="{W}" name="FILTER_NAME" state="Idle" perm="rw">'
        f'<defText name="FILTER_NAME_1">VIS</defText>'
        f'<defText name="FILTER_NAME_2">L-Pro</defText>'
        f'<defText name="FILTER_NAME_3">L-eXtreme</defText></defTextVector>')
    out.append(
        f'<defNumberVector device="{C}" name="CCD_EXPOSURE" state="Idle" perm="rw">'
        f'<defNumber name="CCD_EXPOSURE_VALUE" format="%.3f" min="0" max="3600">1</defNumber>'
        f'</defNumberVector>')
    out.append(
        f'<defBLOBVector device="{C}" name="CCD1" state="Idle" perm="ro">'
        f'<defBLOB name="CCD1"/></defBLOBVector>')
    return "".join(out)


# ---- montagem SERIAL (imita o indi_lx200_OnStep com a placa real) --------------------------
# Diferente dos simuladores: antes de conectar o driver só expõe a porta e o baud, e o CONNECT
# falha (Alert) se eles não baterem com a placa — é o handshake LX200 que não responde.
ONSTEP = "LX200 OnStep"
_BAUDS = ("9600", "19200", "38400", "57600", "115200", "230400")
_ONSTEP_POST = ("EQUATORIAL_EOD_COORD", "ON_COORD_SET", "TELESCOPE_ABORT_MOTION",
                "TIME_UTC", "GEOGRAPHIC_COORD")


def _onstep_connection(st, state=None) -> str:
    con, dis = ("On", "Off") if st["connected"] else ("Off", "On")
    state = state or ("Ok" if st["connected"] else "Idle")
    return f'state="{state}"><{{0}} name="CONNECT">{con}</{{0}}><{{0}} name="DISCONNECT">{dis}</{{0}}>'


def _onstep_pre(st) -> str:
    """O que o driver define ANTES de conectar: só a conexão serial."""
    bauds = "".join(f'<defSwitch name="{b}">{"On" if b == st["baud"] else "Off"}</defSwitch>'
                    for b in _BAUDS)
    return (f'<defSwitchVector device="{ONSTEP}" name="CONNECTION" perm="rw" rule="OneOfMany" '
            + _onstep_connection(st).format("defSwitch") + '</defSwitchVector>'
            f'<defTextVector device="{ONSTEP}" name="DEVICE_PORT" state="Idle" perm="rw">'
            f'<defText name="PORT">{st["port"]}</defText></defTextVector>'
            f'<defSwitchVector device="{ONSTEP}" name="DEVICE_BAUD_RATE" state="Idle" perm="rw" '
            f'rule="OneOfMany">{bauds}</defSwitchVector>')


def _onstep_post(st) -> str:
    """O que só aparece DEPOIS de conectar — como no driver real."""
    lat, lon, elev = st["site"]
    return (f'<defNumberVector device="{ONSTEP}" name="EQUATORIAL_EOD_COORD" state="Idle" perm="rw">'
            f'<defNumber name="RA">{st["ra"]}</defNumber>'
            f'<defNumber name="DEC">{st["dec"]}</defNumber></defNumberVector>'
            f'<defSwitchVector device="{ONSTEP}" name="ON_COORD_SET" state="Idle" perm="rw" '
            f'rule="OneOfMany"><defSwitch name="TRACK">On</defSwitch>'
            f'<defSwitch name="SLEW">Off</defSwitch><defSwitch name="SYNC">Off</defSwitch>'
            f'</defSwitchVector>'
            f'<defSwitchVector device="{ONSTEP}" name="TELESCOPE_ABORT_MOTION" state="Idle" '
            f'perm="rw" rule="AtMostOne"><defSwitch name="ABORT">Off</defSwitch></defSwitchVector>'
            f'<defTextVector device="{ONSTEP}" name="TIME_UTC" state="Idle" perm="rw">'
            f'<defText name="UTC">{st["utc"]}</defText><defText name="OFFSET">0</defText>'
            f'</defTextVector>'
            f'<defNumberVector device="{ONSTEP}" name="GEOGRAPHIC_COORD" state="Idle" perm="rw">'
            f'<defNumber name="LAT">{lat}</defNumber><defNumber name="LONG">{lon}</defNumber>'
            f'<defNumber name="ELEV">{elev}</defNumber></defNumberVector>')


class FakeIndiServer:
    """Servidor INDI falso para testes. `start()` abre a porta; use `.port`."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host, self.port = host, port
        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._conns: list[socket.socket] = []
        self.blob_seed = 0
        # A "placa": onde ela está plugada e a que baud o firmware fala...
        self.onstep_port, self.onstep_baud = "/dev/telescope-mount", "115200"
        # ...e o estado do driver/montagem. Como o OnStepX real sem GPS/RTC, acorda em
        # 2000-01-01 e lat/long 0, na casa da GEM (apontando o polo).
        self.onstep = {"port": "/dev/ttyUSB0", "baud": "9600", "connected": False,
                       "connects": 0, "utc": "2000-01-01T00:00:00", "time_pushes": 0,
                       "site": (0.0, 0.0, 0.0), "site_pushes": 0, "ra": 12.77, "dec": 90.0}

    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.host, self.port))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """Para de aceitar E derruba os clientes — é o indiserver morrendo (cabo tirado)."""
        self._running = False
        try:
            if self._srv:
                self._srv.close()
        except OSError:
            pass
        for c in self._conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                c.close()
            except OSError:
                pass
        self._conns.clear()
        # No Linux o socket de escuta só é liberado quando o accept() bloqueado retorna; sem
        # esperar a thread, reabrir a MESMA porta em seguida dá "Address already in use".
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3.0)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _accept(self):
        try:
            self._srv.settimeout(0.2)
            while self._running:
                try:
                    conn, _ = self._srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._conns.append(conn)           # antes da thread: stop() tem de enxergá-la
                threading.Thread(target=self._serve, args=(conn,), daemon=True).start()
        except OSError:
            pass

    def _serve(self, conn: socket.socket):
        try:
            self._serve_loop(conn)
        finally:                                   # servidor parado = conexão fechada (EOF no cliente)
            try:
                conn.close()
            except OSError:
                pass

    def _serve_loop(self, conn: socket.socket):
        conn.settimeout(1.0)
        parser = ET.XMLPullParser(events=("end",))
        parser.feed(b"<indi>")
        _TOP = {"getProperties", "enableBLOB", "newNumberVector", "newSwitchVector",
                "newTextVector"}
        while self._running:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            parser.feed(chunk)
            for _e, elem in parser.read_events():
                if elem.tag in _TOP:
                    try:
                        self._on(conn, elem)
                    except OSError:
                        return
                    finally:
                        elem.clear()

    # ------ respostas -------------------------------------------------------
    def _on(self, conn, elem):
        tag = elem.tag
        if tag == "getProperties":
            st = self.onstep
            self._send(conn, _catalog() + _onstep_pre(st)
                       + (_onstep_post(st) if st["connected"] else ""))
        elif tag == "enableBLOB":
            pass                                   # aceita e ignora
        elif tag == "newSwitchVector":
            dev, name = elem.get("device"), elem.get("name")
            ons = [c.get("name") for c in elem if (c.text or "").strip() == "On"]
            if dev == ONSTEP and name == "CONNECTION":
                self._onstep_connect(conn, want="CONNECT" in ons)
                return
            if dev == ONSTEP and name == "DEVICE_BAUD_RATE" and ons:
                self.onstep["baud"] = ons[0]
            body = "".join(f'<oneSwitch name="{c.get("name")}">{(c.text or "").strip()}'
                           f'</oneSwitch>' for c in elem)
            self._send(conn, f'<setSwitchVector device="{dev}" name="{name}" state="Ok">'
                             f'{body}</setSwitchVector>')
        elif tag == "newTextVector":
            self._echo_text(conn, elem)
        elif tag == "newNumberVector":
            self._on_number(conn, elem)

    def _onstep_connect(self, conn, want: bool):
        st = self.onstep
        head = f'<setSwitchVector device="{ONSTEP}" name="CONNECTION" '
        if not want:
            st["connected"] = False
            self._send(conn, head + _onstep_connection(st).format("oneSwitch") + '</setSwitchVector>')
            self._send(conn, "".join(f'<delProperty device="{ONSTEP}" name="{n}"/>'
                                     for n in _ONSTEP_POST))
        elif st["port"] == self.onstep_port and st["baud"] == self.onstep_baud:
            st["connected"] = True
            st["connects"] += 1
            self._send(conn, head + _onstep_connection(st).format("oneSwitch") + '</setSwitchVector>')
            self._send(conn, _onstep_post(st))
        else:
            # porta ou baud errados: o handshake LX200 não responde e o driver real fica em Alert
            self._send(conn, head + _onstep_connection(st, "Alert").format("oneSwitch")
                       + '</setSwitchVector>')

    def _on_number(self, conn, elem):
        dev, name = elem.get("device"), elem.get("name")
        vals = {c.get("name"): (c.text or "").strip() for c in elem}
        if dev == ONSTEP and name == "GEOGRAPHIC_COORD":
            self.onstep["site"] = (float(vals["LAT"]), float(vals["LONG"]), float(vals["ELEV"]))
            self.onstep["site_pushes"] += 1
        elif dev == ONSTEP and name == "EQUATORIAL_EOD_COORD":
            self.onstep["ra"], self.onstep["dec"] = float(vals["RA"]), float(vals["DEC"])
        if name == "CCD_EXPOSURE":
            # Busy -> (BLOB) -> Ok, como o driver real
            self._send(conn, f'<setNumberVector device="{dev}" name="CCD_EXPOSURE" state="Busy">'
                             f'<oneNumber name="CCD_EXPOSURE_VALUE">0</oneNumber></setNumberVector>')
            time.sleep(0.05)
            data = base64.b64encode(_tiny_fits(seed=self.blob_seed)).decode("ascii")
            self.blob_seed += 1
            self._send(conn, f'<setBLOBVector device="{dev}" name="CCD1" state="Ok">'
                             f'<oneBLOB name="CCD1" size="{len(data)}" format=".fits">{data}'
                             f'</oneBLOB></setBLOBVector>')
            self._send(conn, f'<setNumberVector device="{dev}" name="CCD_EXPOSURE" state="Ok">'
                             f'<oneNumber name="CCD_EXPOSURE_VALUE">0</oneNumber></setNumberVector>')
            return
        # eco genérico com estado Ok e os valores recebidos
        body = "".join(f'<oneNumber name="{k}">{v}</oneNumber>' for k, v in vals.items())
        state = "Ok"
        if name == "EQUATORIAL_EOD_COORD":
            # simula um slew curto: Busy e depois Ok
            self._send(conn, f'<setNumberVector device="{dev}" name="{name}" state="Busy">'
                             f'{body}</setNumberVector>')
            time.sleep(0.05)
        self._send(conn, f'<setNumberVector device="{dev}" name="{name}" state="{state}">'
                         f'{body}</setNumberVector>')

    def _echo_text(self, conn, elem):
        dev, name = elem.get("device"), elem.get("name")
        vals = {c.get("name"): (c.text or "") for c in elem}
        if dev == ONSTEP and name == "DEVICE_PORT":
            self.onstep["port"] = vals["PORT"]
        elif dev == ONSTEP and name == "TIME_UTC":
            self.onstep["utc"] = vals["UTC"]
            self.onstep["time_pushes"] += 1
        body = "".join(f'<oneText name="{c.get("name")}">{c.text or ""}</oneText>' for c in elem)
        self._send(conn, f'<setTextVector device="{dev}" name="{name}" state="Ok">'
                         f'{body}</setTextVector>')

    @staticmethod
    def _send(conn, xml: str):
        conn.sendall(xml.encode("utf-8"))
