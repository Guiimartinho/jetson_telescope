"""A rede do telescópio: em casa pelo roteador, no campo pelo WiFi dele mesmo.

A API fala com uma PORTA (`status`, `scan`, `join`, `set_mode`, `set_hotspot_psk`, `forget`); o
`status` leva o nome, o endereço e (só para o dono) a senha do WiFi próprio — é com isso que o
celular reencontra o aparelho no campo.

Aqui está o adapter de MENTIRA, `SimNetwork`: é com ele que as telas de rede do app são
desenvolvidas e testadas no PC. O adapter de verdade (NetworkManager, na Jetson) é um arquivo
novo no dia em que isso for testado na bancada — trocar de rede à distância corta o acesso se
der errado, e por isso não é ligado antes.

Três regras que qualquer adapter tem de cumprir, porque é delas que o app depende (e é o que
`tests/test_api_phase4.py::test_network_adapter_contract` confere em cada um):

  * a troca acontece DEPOIS da resposta (o celular precisa ouvir "aceito" antes de a rede cair),
    e `reconnect_s` diz quanto esperar para procurar o aparelho de novo;
  * um pedido aceito limpa o `last_error` anterior, e `switching` fica verdadeiro até a troca
    acabar — é por ele que o app sabe que ainda não dá para julgar o resultado;
  * se a rede nova não der certo (senha errada, sumiu), o aparelho VOLTA para onde estava e
    conta o motivo em `last_error` — ele nunca fica mudo.
"""
from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

MODES = ("home", "field")


class NetworkError(Exception):
    """Pedido de rede que não dá para atender, com um código que o app sabe traduzir."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@runtime_checkable
class NetworkControl(Protocol):
    """A porta: o que a API pede à rede do aparelho. Os pedidos que não dão para atender
    levantam `NetworkError`."""

    def status(self, owner: bool = False) -> dict: ...
    def scan(self) -> list[dict]: ...
    def join(self, ssid: str, psk: str | None) -> dict: ...
    def set_mode(self, mode: str) -> dict: ...
    def set_hotspot_psk(self, psk: str) -> dict: ...
    def forget(self, ssid: str) -> dict: ...


class SimNetwork:
    """Uma vizinhança de mentira: redes com sinal e senha, e o WiFi próprio do aparelho."""

    def __init__(self, hotspot_ssid: str = "Telescopio-sim", hotspot_psk: str = "ceu-estrelado",
                 switch_s: float = 3.0, clock=time.monotonic, hotspot_address: str = "10.42.0.1"):
        self._lock = threading.Lock()
        self._clock = clock
        self.switch_s = float(switch_s)
        # onde o aparelho atende no WiFi próprio: o app guarda, para achá-lo no campo
        self.hotspot_address = hotspot_address
        # nome -> (senha, ou None se aberta; sinal de 0 a 100)
        self.nearby: dict[str, tuple[str | None, int]] = {
            "Casa": ("senha-de-casa", 78), "Vizinho 5G": ("outra-senha", 41),
            "Visitantes": (None, 55)}
        self.mode = "field"                      # começa no campo: é de onde o primeiro uso parte
        self.wifi: str | None = None
        self.known: dict[str, str | None] = {}   # redes de casa guardadas -> senha
        self.hotspot_ssid, self.hotspot_psk = hotspot_ssid, hotspot_psk
        self.last_error: str | None = None
        self._pending: tuple[float, str, str | None, str | None] | None = None   # (quando, modo, rede, senha)

    # ------------------------------------------------------------------ estado
    def _tick(self) -> None:
        """Conclui a troca marcada, se já deu a hora."""
        if self._pending is None or self._clock() < self._pending[0]:
            return
        _, mode, ssid, psk = self._pending
        self._pending = None
        if mode == "field":
            self.mode, self.wifi, self.last_error = "field", None, None
            return
        real = self.nearby.get(ssid)
        if real is None:                                    # a rede sumiu: fica onde estava
            self.last_error = "not_found"
        elif real[0] is not None and real[0] != psk:
            self.last_error = "wrong_password"
        else:
            self.mode, self.wifi, self.last_error = "home", ssid, None
            self.known[ssid] = psk

    def status(self, owner: bool = False) -> dict:
        with self._lock:
            self._tick()
            hotspot = {"ssid": self.hotspot_ssid, "active": self.mode == "field",
                       "address": self.hotspot_address}
            if owner:                                       # a senha do WiFi próprio é só do dono
                hotspot["psk"] = self.hotspot_psk
            wifi = None
            if self.wifi is not None:
                wifi = {"ssid": self.wifi, "signal": self.nearby.get(self.wifi, (None, 0))[1]}
            return {"enabled": True, "mode": self.mode, "wifi": wifi, "hotspot": hotspot,
                    "known": sorted(self.known), "last_error": self.last_error,
                    "switching": self._pending is not None}

    def scan(self) -> list[dict]:
        with self._lock:
            self._tick()
            rows = [{"ssid": ssid, "signal": signal, "secure": psk is not None,
                     "known": ssid in self.known}
                    for ssid, (psk, signal) in self.nearby.items()]
            return sorted(rows, key=lambda r: -r["signal"])

    # ----------------------------------------------------------------- pedidos
    def _schedule(self, mode: str, ssid: str | None = None, psk: str | None = None) -> dict:
        self._pending = (self._clock() + self.switch_s, mode, ssid, psk)
        self.last_error = None
        return {"accepted": True, "reconnect_s": int(self.switch_s) + 5}

    def join(self, ssid: str, psk: str | None) -> dict:
        """Entrar numa rede de casa. A resposta sai antes da troca; se a senha estiver errada,
        o aparelho fica onde estava e `last_error` conta. Rede já guardada dispensa a senha."""
        with self._lock:
            self._tick()
            if ssid not in self.nearby:
                raise NetworkError("not_found", "esta rede não está ao alcance do telescópio")
            if not psk:
                psk = self.known.get(ssid)
            if self.nearby[ssid][0] is not None and not psk:
                raise NetworkError("invalid_argument", "psk: esta rede pede senha")
            return self._schedule("home", ssid, psk)

    def set_mode(self, mode: str) -> dict:
        with self._lock:
            self._tick()
            if mode not in MODES:
                raise NetworkError("invalid_argument", f"mode: use um de {', '.join(MODES)}")
            if mode == self.mode and self._pending is None:
                self.last_error = None               # aceito (sem nada a trocar): o erro antigo não é dele
                return {"accepted": True, "reconnect_s": 0}
            if mode == "field":
                return self._schedule("field")
            reachable = [s for s in self.known if s in self.nearby]
            if not reachable:
                raise NetworkError("no_known_network", "nenhuma rede de casa guardada está ao alcance")
            best = max(reachable, key=lambda s: self.nearby[s][1])
            return self._schedule("home", best, self.known[best])

    def set_hotspot_psk(self, psk: str) -> dict:
        with self._lock:
            self._tick()
            if not (8 <= len(psk) <= 63) or not psk.isprintable():
                raise NetworkError("invalid_argument", "psk: a senha do WiFi tem de 8 a 63 caracteres")
            self.hotspot_psk = psk
            return {"ssid": self.hotspot_ssid, "changed": True}

    def forget(self, ssid: str) -> dict:
        with self._lock:
            self._tick()
            if ssid not in self.known:
                raise NetworkError("not_found", "esta rede não está guardada")
            if ssid == self.wifi:
                raise NetworkError("in_use", "o telescópio está nesta rede: troque para o WiFi próprio antes")
            del self.known[ssid]
            return {"forgotten": ssid}
