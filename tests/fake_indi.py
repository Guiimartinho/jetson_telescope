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


class FakeIndiServer:
    """Servidor de 1 cliente para testes. `start()` abre a porta; use `.port`."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host, self.port = host, port
        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.blob_seed = 0

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
        self._running = False
        try:
            if self._srv:
                self._srv.close()
        except OSError:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _accept(self):
        try:
            self._srv.settimeout(1.0)
            while self._running:
                try:
                    conn, _ = self._srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._serve, args=(conn,), daemon=True).start()
        except OSError:
            pass

    def _serve(self, conn: socket.socket):
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
            self._send(conn, _catalog())
        elif tag == "enableBLOB":
            pass                                   # aceita e ignora
        elif tag == "newSwitchVector":
            dev, name = elem.get("device"), elem.get("name")
            ons = [c.get("name") for c in elem if (c.text or "").strip() == "On"]
            body = "".join(f'<oneSwitch name="{c.get("name")}">{(c.text or "").strip()}'
                           f'</oneSwitch>' for c in elem)
            self._send(conn, f'<setSwitchVector device="{dev}" name="{name}" state="Ok">'
                             f'{body}</setSwitchVector>')
        elif tag == "newTextVector":
            self._echo_text(conn, elem)
        elif tag == "newNumberVector":
            self._on_number(conn, elem)

    def _on_number(self, conn, elem):
        dev, name = elem.get("device"), elem.get("name")
        vals = {c.get("name"): (c.text or "").strip() for c in elem}
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
        body = "".join(f'<oneText name="{c.get("name")}">{c.text or ""}</oneText>' for c in elem)
        self._send(conn, f'<setTextVector device="{dev}" name="{name}" state="Ok">'
                         f'{body}</setTextVector>')

    @staticmethod
    def _send(conn, xml: str):
        conn.sendall(xml.encode("utf-8"))
