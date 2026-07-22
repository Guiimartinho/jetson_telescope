"""Cliente INDI puro-Python (socket + XML) — SEM dependências nativas.

Por que existir: o `pyindi-client` (PyIndi) exige compilar as libs C++ do INDI e NÃO roda no
PC de dev (Windows). Este cliente fala o protocolo INDI direto (XML sobre TCP na porta 7624),
então roda em QUALQUER plataforma e — o mais importante — é **testável na CI** contra um
servidor INDI falso (ver tests/fake_indi.py), sem nada de INDI instalado. Na Jetson, o MESMO
código conecta ao `indiserver` real (drivers reais OU os simuladores indi_simulator_*).

Protocolo (resumo — https://www.indilib.org/developer/protocol.html):
  * O servidor manda um FLUXO de elementos XML de topo concatenados (não é 1 doc só):
      <defNumberVector .../> <setNumberVector .../> <setBLOBVector .../> <message .../> ...
    Por isso parseamos incrementalmente com XMLPullParser semeado com uma raiz sintética.
  * Cliente -> servidor: <getProperties>, <newNumberVector>, <newSwitchVector>, <enableBLOB>.
  * BLOBs (imagem CCD) vêm em base64 dentro de <oneBLOB>.

Uso:
    cli = IndiClient("localhost", 7624); cli.connect()
    cli.get_properties()                       # pede o catálogo de propriedades
    cli.wait_vector("Telescope Simulator", "EQUATORIAL_EOD_COORD", timeout=5)
    cli.send_number("Telescope Simulator", "EQUATORIAL_EOD_COORD", {"RA": 5.5, "DEC": -5.0})
Ver docs/20.
"""
from __future__ import annotations

import base64
import socket
import threading
import time
import xml.etree.ElementTree as ET

# Vetores de topo que o servidor define/atualiza (o resto — defNumber, oneBLOB... — é aninhado).
_DEF = {"defNumberVector", "defSwitchVector", "defTextVector", "defLightVector", "defBLOBVector"}
_SET = {"setNumberVector", "setSwitchVector", "setTextVector", "setLightVector", "setBLOBVector"}
_TOP = _DEF | _SET | {"message", "delProperty"}
# tag do vetor -> tag do elemento-filho (para ler os valores)
_CHILD = {"Number": "defNumber", "Switch": "defSwitch", "Text": "defText",
          "Light": "defLight", "BLOB": "defBLOB"}


class IndiProperty:
    """Snapshot de um vetor de propriedade (thread-safe via cópia no acesso)."""
    __slots__ = ("device", "name", "kind", "state", "perm", "elements")

    def __init__(self, device, name, kind, state="Idle", perm="rw"):
        self.device = device
        self.name = name
        self.kind = kind                 # "Number" | "Switch" | "Text" | "Light" | "BLOB"
        self.state = state               # "Idle" | "Ok" | "Busy" | "Alert"
        self.perm = perm
        self.elements: dict[str, object] = {}   # nome_do_elemento -> valor

    def __repr__(self):
        return (f"IndiProperty({self.device!r}, {self.name!r}, {self.kind}, "
                f"state={self.state}, {self.elements})")


class IndiClient:
    """Conexão a um indiserver. Um thread de leitura mantém o cache de propriedades vivo."""

    def __init__(self, host="localhost", port=7624, connect_timeout=5.0):
        self.host, self.port = host, port
        self.connect_timeout = connect_timeout
        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._running = False
        self._lock = threading.Condition()          # protege _props e acorda quem espera
        self._props: dict[tuple[str, str], IndiProperty] = {}
        self._blobs: dict[tuple[str, str], list[dict]] = {}   # (dev,name) -> lista de BLOBs
        self._blob_event = threading.Event()
        self._last_blob_key: tuple[str, str] | None = None

    # ------------------------------------------------------------------ conexão
    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), self.connect_timeout)
        self._sock.settimeout(1.0)
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return self

    def close(self):
        self._running = False
        try:
            if self._sock:
                self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            if self._sock:
                self._sock.close()
        finally:
            self._sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # --------------------------------------------------------------- envio (TX)
    def _send(self, xml: str):
        if not self._sock:
            raise RuntimeError("INDI: não conectado (chame connect())")
        self._sock.sendall(xml.encode("utf-8"))

    def get_properties(self, device: str | None = None, name: str | None = None):
        attrs = ' version="1.7"'
        if device:
            attrs += f' device="{_esc(device)}"'
        if name:
            attrs += f' name="{_esc(name)}"'
        self._send(f"<getProperties{attrs}/>")

    def enable_blob(self, device: str, name: str | None = None, mode="Also"):
        """Habilita recepção de BLOBs (Never|Also|Only). Sem isso, o CCD não manda imagem."""
        n = f' name="{_esc(name)}"' if name else ""
        self._send(f'<enableBLOB device="{_esc(device)}"{n}>{mode}</enableBLOB>')

    def send_number(self, device: str, name: str, values: dict[str, float]):
        body = "".join(f'<oneNumber name="{_esc(k)}">{_fmt(v)}</oneNumber>'
                       for k, v in values.items())
        self._send(f'<newNumberVector device="{_esc(device)}" name="{_esc(name)}">'
                   f'{body}</newNumberVector>')

    def send_switch(self, device: str, name: str, on: str, off: list[str] | None = None):
        """Liga o switch `on` (e desliga os `off`) — cobre a regra OneOfMany."""
        parts = [f'<oneSwitch name="{_esc(on)}">On</oneSwitch>']
        for k in off or []:
            parts.append(f'<oneSwitch name="{_esc(k)}">Off</oneSwitch>')
        self._send(f'<newSwitchVector device="{_esc(device)}" name="{_esc(name)}">'
                   f'{"".join(parts)}</newSwitchVector>')

    def send_text(self, device: str, name: str, values: dict[str, str]):
        body = "".join(f'<oneText name="{_esc(k)}">{_esc(str(v))}</oneText>'
                       for k, v in values.items())
        self._send(f'<newTextVector device="{_esc(device)}" name="{_esc(name)}">'
                   f'{body}</newTextVector>')

    # ------------------------------------------------------------ leitura (cache)
    def get(self, device: str, name: str) -> IndiProperty | None:
        with self._lock:
            return self._props.get((device, name))

    def value(self, device: str, name: str, element: str, default=None):
        p = self.get(device, name)
        return default if p is None else p.elements.get(element, default)

    def devices(self) -> set[str]:
        with self._lock:
            return {d for (d, _) in self._props}

    def wait_vector(self, device: str, name: str, timeout=5.0) -> IndiProperty:
        """Espera a propriedade APARECER no cache (após getProperties)."""
        end = time.monotonic() + timeout
        with self._lock:
            while (device, name) not in self._props:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"INDI: propriedade {device!r}/{name!r} não apareceu")
                self._lock.wait(remaining)
            return self._props[(device, name)]

    def wait_state(self, device: str, name: str, state="Ok", timeout=30.0) -> IndiProperty:
        """Espera o `state` do vetor (ex.: slew termina quando EQUATORIAL_EOD_COORD vira Ok)."""
        end = time.monotonic() + timeout
        with self._lock:
            while True:
                p = self._props.get((device, name))
                if p is not None and p.state == state:
                    return p
                if p is not None and p.state == "Alert":
                    raise RuntimeError(f"INDI: {device}/{name} em ALERT")
                remaining = end - time.monotonic()
                if remaining <= 0:
                    cur = p.state if p else "ausente"
                    raise TimeoutError(f"INDI: {device}/{name} não chegou a {state} (está {cur})")
                self._lock.wait(remaining)

    # -------------------------------------------------------------------- BLOBs
    def wait_blob(self, timeout=30.0) -> dict:
        """Bloqueia até chegar um BLOB novo; devolve {'data':bytes,'format':str,'device','name'}."""
        if not self._blob_event.wait(timeout):
            raise TimeoutError("INDI: timeout esperando BLOB (habilitou enable_blob?)")
        self._blob_event.clear()
        with self._lock:
            key = self._last_blob_key
            return self._blobs[key][-1]

    def clear_blob(self):
        self._blob_event.clear()

    # ----------------------------------------------------------- device helper
    def connect_device(self, device: str, timeout=5.0):
        """Liga o dispositivo (CONNECTION=CONNECT) e espera ele responder."""
        self.wait_vector(device, "CONNECTION", timeout=timeout)
        self.send_switch(device, "CONNECTION", on="CONNECT", off=["DISCONNECT"])

    # ------------------------------------------------------------- thread de RX
    def _read_loop(self):
        parser = ET.XMLPullParser(events=("end",))
        parser.feed(b"<indi>")            # raiz sintética: o fluxo é uma sequência de irmãos
        buf = self._sock
        while self._running:
            try:
                chunk = buf.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            parser.feed(chunk)
            for _event, elem in parser.read_events():
                if elem.tag in _TOP:
                    try:
                        self._handle(elem)
                    finally:
                        elem.clear()      # libera memória (BLOBs são grandes)

    def _handle(self, elem: ET.Element):
        tag = elem.tag
        if tag == "message" or tag == "delProperty":
            if tag == "delProperty":
                dev, name = elem.get("device"), elem.get("name")
                with self._lock:
                    if name:
                        self._props.pop((dev, name), None)
                    else:
                        for k in [k for k in self._props if k[0] == dev]:
                            self._props.pop(k, None)
                    self._lock.notify_all()
            return

        device, name = elem.get("device"), elem.get("name")
        state = elem.get("state", "Idle")
        if tag in _DEF:
            kind = tag[len("def"):-len("Vector")]      # defNumberVector -> "Number"
            prop = IndiProperty(device, name, kind, state, elem.get("perm", "rw"))
            child = _CHILD[kind]
            for c in elem:
                if c.tag == child:
                    prop.elements[c.get("name")] = _parse_value(kind, c.text)
            with self._lock:
                self._props[(device, name)] = prop
                self._lock.notify_all()
        elif tag in _SET:
            kind = tag[len("set"):-len("Vector")]
            if kind == "BLOB":
                self._handle_blob(device, name, elem)
            child = "one" + kind
            with self._lock:
                prop = self._props.get((device, name))
                if prop is None:
                    prop = IndiProperty(device, name, kind, state)
                    self._props[(device, name)] = prop
                prop.state = state
                if kind != "BLOB":
                    for c in elem:
                        if c.tag == child:
                            prop.elements[c.get("name")] = _parse_value(kind, c.text)
                self._lock.notify_all()

    def _handle_blob(self, device, name, elem):
        for c in elem:
            if c.tag != "oneBLOB":
                continue
            raw = base64.b64decode((c.text or "").strip()) if c.text else b""
            blob = {"device": device, "name": name, "element": c.get("name"),
                    "format": c.get("format", ""), "size": int(c.get("size", len(raw))),
                    "data": raw}
            with self._lock:
                self._blobs.setdefault((device, name), []).append(blob)
                self._last_blob_key = (device, name)
            self._blob_event.set()


# --------------------------------------------------------------------- helpers
def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _fmt(v) -> str:
    return repr(float(v)) if isinstance(v, float) else str(v)


def _parse_value(kind: str, text: str | None):
    t = (text or "").strip()
    if kind == "Number":
        try:
            return float(t)
        except ValueError:
            return _sexagesimal(t)
    if kind == "Switch" or kind == "Light":
        return t                       # "On"/"Off" | "Idle"/"Ok"/"Busy"/"Alert"
    return t                            # Text


def _sexagesimal(t: str) -> float:
    """INDI às vezes manda número sexagesimal ('12:30:00'). Converte para decimal."""
    parts = t.replace(";", ":").split(":")
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return float("nan")
    sign = -1.0 if (vals and str(parts[0]).strip().startswith("-")) else 1.0
    acc, scale = 0.0, 1.0
    for v in vals:
        acc += abs(v) * scale
        scale /= 60.0
    return sign * acc
