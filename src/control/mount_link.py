"""Link automático com a montagem real — a Jetson mantém a placa conectada SOZINHA.

Papéis: a Jetson é o cérebro (vê, decide, sabe a hora e o lugar); a controladora (OnStepX na
FYSETC E4) é o músculo (pulsos de passo em tempo real). O cabo USB entre as duas é o link, e
este módulo é quem cuida dele sem operador:

  * conecta quando o indiserver aparece (o systemd o sobe quando a placa é plugada);
  * a cada (re)conexão envia local e hora UTC — o OnStepX acorda em 2000-01-01, lat/long 0;
  * reenvia quando o local e a hora mudam (é o celular quem os traz, pela API do app);
  * percebe quando o cabo sai (o indiserver cai, o socket fecha) e fica tentando de novo;
  * publica o estado para a UI.

O `MountLink` não conhece INDI: recebe uma fábrica de montagens (injeção de dependência), então
é testado contra o servidor falso. Ver docs/35 e tests/test_mount_link.py.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

# São Paulo (lat, lon leste-positivo, altitude em m). Mesmo local padrão do console.
DEFAULT_SITE = (-23.55, -46.63, 760.0)


class MountLink:
    def __init__(self, factory, site=DEFAULT_SITE, period_s=2.0, now=None):
        self._factory = factory                       # () -> montagem conectada (ou levanta)
        site = tuple(float(v) for v in site)
        self.site = site if len(site) == 3 else (site[0], site[1], 0.0)
        self.period_s = period_s
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._mount = None
        self._lock = threading.Lock()                 # protege _status, site e a versão do local
        self._status = {"connected": False, "ra_deg": None, "dec_deg": None,
                        "connections": 0, "since": None, "error": "ainda não tentou"}
        # O local/hora têm versão: `update_site` só anota o que há para mandar; quem manda é o
        # laço. Assim nada se perde se o pedido chegar no meio de uma conexão, e só UMA thread
        # fala com a montagem (duas falando INDI ao mesmo tempo embaralhariam as mensagens).
        self._site_version = 0
        self._pushed_version = -1                     # a última versão tentada na montagem atual
        self._site_ok = False                         # ...e se ela foi aceita
        self._stop = threading.Event()
        self._kick = threading.Event()                # acorda o laço antes do fim do período
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ estado
    @property
    def mount(self):
        """A montagem conectada, ou None enquanto o link está caído."""
        return self._mount

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _set(self, **kw) -> dict:
        with self._lock:
            self._status.update(kw)
            return dict(self._status)

    def _site_now(self):
        with self._lock:
            return self.site, self._now, self._site_version

    # ------------------------------------------------------------------- laço
    def poll_once(self) -> dict:
        """Um passo: conecta se preciso; senão confere o link, reenvia local/hora se mudaram e
        lê a posição. Nunca levanta."""
        if self._mount is None:
            m = None
            try:
                m = self._factory()
                site, now, version = self._site_now()
                m.set_site_and_time(*site, when=now())
            except Exception as e:                    # sem placa, sem indiserver, baud errado...
                self._close(m)
                return self._set(connected=False, ra_deg=None, dec_deg=None,
                                 error=f"{type(e).__name__}: {e}")
            self._mount = m
            self._pushed_version, self._site_ok = version, True
            self._set(connections=self._status["connections"] + 1, since=time.time())
        try:
            if not self._mount.is_connected():
                raise ConnectionError("a montagem parou de responder (cabo? energia?)")
            ra, dec = self._mount.position()
        except Exception as e:
            self._close(self._mount)
            self._mount = None
            return self._set(connected=False, ra_deg=None, dec_deg=None, since=None,
                             error=f"{type(e).__name__}: {e}")
        error = None
        if self._pushed_version != self._site_now()[2]:      # chegou local/hora novos
            error = self._push_site()
        return self._set(connected=True, ra_deg=ra, dec_deg=dec, error=error)

    def _push_site(self) -> str | None:
        """Manda o local/hora atuais à montagem conectada. Um local recusado NÃO derruba o link:
        fica anotado como erro e não é tentado de novo até mudar. Devolve o erro, ou None."""
        site, now, version = self._site_now()
        error = None
        try:
            self._mount.set_site_and_time(*site, when=now())
        except Exception as e:
            error = f"local/hora recusados: {type(e).__name__}: {e}"
        self._pushed_version, self._site_ok = version, error is None
        return error

    def update_site(self, site, now=None, wait_s=3.0) -> bool:
        """Novo local e novo relógio — é o celular quem os traz (GPS e hora), pela API.

        Valem para as próximas conexões e, se a montagem estiver conectada, são enviados já.
        Devolve True quando a montagem recebeu. Com o laço rodando, quem envia é ele (esta
        chamada só o acorda e espera até `wait_s`); sem laço, envia daqui mesmo."""
        site = tuple(float(v) for v in site)
        with self._lock:
            self.site = site if len(site) == 3 else (site[0], site[1], 0.0)
            if now is not None:
                self._now = now
            self._site_version += 1
            version = self._site_version
        if self._thread and self._thread.is_alive():
            self._kick.set()
            if self._mount is None:                   # sem montagem agora: vai na próxima conexão,
                return False                          # e a API não fica esperando à toa
            end = time.monotonic() + wait_s
            while time.monotonic() < end and self._pushed_version < version:
                time.sleep(0.02)
        elif self._mount is not None:
            error = self._push_site()
            if error:
                self._set(error=error)
        return self._pushed_version >= version and self._site_ok

    def start(self):
        if not (self._thread and self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="mount-link", daemon=True)
            self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            self.poll_once()
            self._kick.wait(self.period_s)
            self._kick.clear()

    def stop(self):
        self._stop.set()
        self._kick.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5.0)
        self._close(self._mount)
        self._mount = None

    @staticmethod
    def _close(mount):
        try:
            if mount is not None:
                mount.close()
        except Exception:
            pass


# --------------------------------------------------------------- configuração
def _parse_site(text):
    if not text:
        return DEFAULT_SITE
    try:
        v = [float(p) for p in text.split(",")]
        if len(v) not in (2, 3):
            raise ValueError
    except ValueError:
        raise ValueError(f"TELE_SITE inválido ({text!r}): use 'lat,lon' ou 'lat,lon,altitude_m'") from None
    return (v[0], v[1], v[2] if len(v) == 3 else 0.0)


def _indi_factory(device, host, port, serial_port, baud, timeout=10.0):
    def make():
        from .mount import IndiMount
        m = IndiMount(device=device, host=host, port=port, serial_port=serial_port, baud=baud,
                      connect_timeout=timeout)
        try:
            return m.connect()
        except Exception:
            m.close()                                 # não deixa socket pendurado a cada tentativa
            raise
    return make


def mount_link_from_env(env=None):
    """Liga o link real só quando pedido: `TELE_MOUNT=indi` (é o serviço da Jetson que define).
    Sem isso — PC de dev, CI — devolve None e tudo segue nos simuladores.

    Variáveis: TELE_MOUNT_DEVICE ("LX200 OnStep"), TELE_MOUNT_PORT (/dev/telescope-mount, o nome
    fixo da regra udev), TELE_MOUNT_BAUD (115200, o do firmware), TELE_INDI_HOST/TELE_INDI_PORT
    (localhost:7624) e TELE_SITE ("lat,lon[,altitude_m]", leste positivo).
    """
    env = os.environ if env is None else env
    if env.get("TELE_MOUNT", "sim").strip().lower() != "indi":
        return None
    return MountLink(
        _indi_factory(device=env.get("TELE_MOUNT_DEVICE", "LX200 OnStep"),
                      host=env.get("TELE_INDI_HOST", "localhost"),
                      port=int(env.get("TELE_INDI_PORT", "7624")),
                      serial_port=env.get("TELE_MOUNT_PORT", "/dev/telescope-mount"),
                      baud=int(env.get("TELE_MOUNT_BAUD", "115200"))),
        site=_parse_site(env.get("TELE_SITE")))
