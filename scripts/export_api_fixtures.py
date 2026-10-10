#!/usr/bin/env python3
"""Grava respostas REAIS da API v1 como arquivos de teste do app (app/test/fixtures).

    py -3.11 scripts/export_api_fixtures.py            # grava
    py -3.11 scripts/export_api_fixtures.py --check    # só confere (sai com 1 se algo mudou)

É o que mantém os dois lados em sincronia: os testes do app (Dart) leem estes arquivos, e um
teste da Jetson (`tests/test_app_contract.py`) falha se a API passar a responder diferente
sem que eles sejam regravados. Tudo aqui é determinístico: relógio fixo, identidade fixa (de
mentira — não é o certificado de aparelho nenhum) e estado montado à mão.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "app" / "test" / "fixtures"
WHEN = datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc)      # 22h30 em São Paulo
SECRET = bytes(range(16))
NAME = "Pixel de teste"


def build() -> dict[str, object]:
    from fastapi.testclient import TestClient

    from src import backend
    from src.api import app as api
    from src.api.identity import DeviceIdentity, b64u, b64u_decode
    from src.api.pairing import PairingService, pairing_proof
    from src.core import catalog as cat
    from src.server.webview import FrameHub

    real_backend, real_cache = backend.backend_name, dict(api._SYS_CACHE)
    backend.backend_name = lambda: "CuPy/GPU (Orin)"
    api._SYS_CACHE.update(t=float("inf"), v={"temp_c": 41.5, "disk_free_gb": 200.1})
    try:
        return _build(api, DeviceIdentity, PairingService, FrameHub, TestClient, b64u, b64u_decode,
                      pairing_proof, cat)
    finally:                                      # este script também roda dentro dos testes
        backend.backend_name = real_backend
        api._SYS_CACHE.clear()
        api._SYS_CACHE.update(real_cache)


def _build(api, DeviceIdentity, PairingService, FrameHub, TestClient, b64u, b64u_decode,
           pairing_proof, cat) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        identity = DeviceIdentity(Path(tmp), cert_der=b"certificado de mentira, so para os testes",
                                  pairing_secret=SECRET)
        hub = FrameHub()
        hub.update(b"", {"state": "IDLE", "phase": "pronto", "backend": "CuPy/GPU (Orin)",
                         "job": None, "outcome": "", "focus_pos": 6300})

        class Link:
            def status(self):
                return {"connected": True, "ra_deg": 83.82, "dec_deg": -5.39, "error": None}

            def update_site(self, site, now=None):
                return True

        ctx = api.ApiContext(identity=identity, pairing=PairingService(identity), hub=hub,
                             submit=lambda cmd, tag=None: None, mount_link=Link())
        ctx.site.now = lambda: WHEN
        ctx.jobs._boot = "0000"
        ctx.sessions = lambda: [
            {"id": "lagoon_trifid", "target": "M8 Lagoa + M20 Trifida", "type": "nebula", "frames": 15,
             "integration_s": 2700, "integration_approx": False, "camera": "ASI2600MC (dado real)",
             "source": "reference", "has_fits": True}]
        from src.api.server import render_presets
        ctx.presets = render_presets
        out: dict[str, object] = {}
        with TestClient(api.create_app(ctx)) as http:
            out["info"] = http.get("/api/v1/info").json()
            out["error_unauthorized"] = http.get("/api/v1/state").json()
            ctx.pairing.open_window()
            nonce = http.post("/api/v1/pair/start", json={"client_name": NAME}).json()["nonce"]
            proof = b64u(pairing_proof(SECRET, b64u_decode(nonce), identity.fingerprint_bytes, NAME))
            token = http.post("/api/v1/pair/finish", json={"client_name": NAME, "proof": proof}).json()["token"]
            http.headers["Authorization"] = f"Bearer {token}"
            out["state_idle"] = http.get("/api/v1/state").json()
            out["site"] = http.post("/api/v1/site", json={"utc": "2026-10-10T01:30:00Z", "lat": -23.55,
                                                           "lon": -46.63, "elev_m": 760}).json()
            out["site"]["clock_offset_s"] = 0.0                      # depende do relógio de quem roda
            out["presets"] = http.get("/api/v1/render/presets").json()
            out["sessions"] = http.get("/api/v1/sessions").json()
            out["system"] = http.get("/api/v1/system").json()
            if cat.HAS_ONGC:
                out["targets"] = http.get("/api/v1/targets?visible=1&fits=1&limit=4").json()
                out["target_detail"] = http.get("/api/v1/targets/M42").json()
            job = http.post("/api/v1/observe/stack", json={"id": "c-1", "exposure_s": 30}).json()
            out["job_stack"] = job
            hub.update(b"", {"state": "STACKING", "phase": "empilhando", "backend": "CuPy/GPU (Orin)",
                             "job": job["job"], "outcome": "", "accepted": 12, "rejected": 2,
                             "snr": 9.7, "fwhm": 2.9, "target": "M31", "focus_pos": 6300})
            running = http.get("/api/v1/state").json()
            out["state_stacking"] = running
            # as mensagens do canal em tempo real, na ordem em que chegariam
            more = dict(running, stack=dict(running["stack"], accepted=13, snr=10.1))
            done = dict(more, job=dict(more["job"], state="stopped",
                                       steps=[{"name": "stack", "state": "stopped"}]))
            messages, last, seq = [], None, 0
            for snapshot in (out["state_idle"], running, more, done):
                for kind, payload in api.state_messages(last, snapshot):
                    seq += 1
                    messages.append({"seq": seq, "type": kind, "data": payload})
                last = snapshot
            out["ws_messages"] = messages
            # ---- fase 3: equipamento, plano, mosaico, Lua e planetas ----
            out["system"]["uptime_s"] = 0                            # depende de quem roda
            out["solar"] = http.get("/api/v1/solar").json()
            network = http.get("/api/v1/network").json()
            out["network"] = dict(network, hostname="telescopio", address="192.168.3.221", port=8443)
            clients = http.get("/api/v1/clients").json()
            for n, c in enumerate(clients["items"]):                 # ids e horas são sorteados
                c.update(id=f"c-{n:04d}", created=1791595800.0, last_used=1791595800.0)
            out["clients"] = clients
            ctx.pairing.invite = lambda seconds=300.0, role="operator": bytes(range(50, 66))
            ctx.qr_svg = lambda uri: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 3"><path d="M0 0h1v1H0z"/></svg>'
            out["invite"] = http.post("/api/v1/clients/invite", json={"role": "operator", "minutes": 5}).json()
            if cat.HAS_ONGC:
                out["plan"] = http.put("/api/v1/plan", json={"items": [
                    {"target": "NGC253", "frames": 40}, {"target": "M42", "frames": 20, "mosaic": [1, 2]},
                    {"target": "NGC188", "frames": 30}]}).json()
                out["mosaic"] = http.post("/api/v1/mosaic", json={"target": "M31", "rows": 2, "cols": 2}).json()
            # o mesmo aparelho com a montagem SIMULADA: aí dá para mexer nela à mão; e uma
            # noite autônoma em andamento, com a curva do último autofoco
            ctx.mount_link = None
            night = http.post("/api/v1/plan/start", json={"id": "c-9"}).json() if cat.HAS_ONGC else None
            hub.update(b"", {"state": "STACKING", "phase": "empilhando", "backend": "CuPy/GPU (Orin)",
                             "job": night["job"] if night else None, "outcome": "", "accepted": 7,
                             "rejected": 1, "snr": 4.2, "fwhm": 2.6, "target": "M42",
                             "focus_pos": 6290, "focus_range": [0, 10000], "focus_best": 6290,
                             "focus_curve": [[4200, 8.4], [5250, 5.1], [6300, 2.5], [7350, 5.3], [8400, None]],
                             "mount_ctl": {"parked": False, "tracking": True, "jog": None},
                             "queue_done": 1, "queue_total": 3,
                             "plan": [{"id": "p-1", "target": "NGC253", "status": "done", "accepted": 40,
                                       "snr": 6.1, "reason": ""},
                                      {"id": "p-2", "target": "M42", "status": "running", "accepted": 7,
                                       "snr": 4.2, "reason": ""},
                                      {"id": "p-3", "target": "NGC188", "status": "pending", "accepted": 0,
                                       "snr": 0.0, "reason": ""}]})
            out["state_night"] = http.get("/api/v1/state").json()
            out["focuser"] = http.get("/api/v1/focuser").json()
            out["camera"] = http.post("/api/v1/camera", json={"exposure_s": 60, "gain": 200}).json()
            # ---- o que faltava: rede (casa e campo), atualização, polar e planetária ----
            from src.api.network import SimNetwork
            from src.api.updates import SimUpdater
            tick = [0.0]
            ctx.network = SimNetwork(hotspot_ssid="Telescopio-6465", clock=lambda: tick[0])
            where = {"hostname": "telescopio", "port": 8443}
            out["network_field"] = dict(http.get("/api/v1/network").json(), address="192.168.4.1", **where)
            out["network_scan"] = http.get("/api/v1/network/scan").json()
            out["network_join"] = http.post("/api/v1/network/join",
                                            json={"ssid": "Casa", "psk": "senha-de-casa"}).json()
            tick[0] += 10
            out["network_home"] = dict(http.get("/api/v1/network").json(), address="192.168.3.221", **where)
            idle = {"state": "IDLE", "phase": "pronto", "backend": "CuPy/GPU (Orin)", "job": None,
                    "outcome": "", "focus_pos": 6290, "focus_range": [0, 10000],
                    "mount_ctl": {"parked": False, "tracking": True, "jog": None}}
            hub.update(b"", idle)
            ctx.updater = SimUpdater(current="0.1.0", newer="0.2.0", clock=lambda: tick[0])
            http.post("/api/v1/system/update/check")
            tick[0] += 2
            out["update_available"] = http.get("/api/v1/system/update").json()
            http.post("/api/v1/system/update/install")
            tick[0] += 3
            out["update_installing"] = http.get("/api/v1/system/update").json()
            capture = http.post("/api/v1/observe/planetary", json={"id": "c-10", "body": "saturn"}).json()
            out["job_planetary"] = capture
            hub.update(b"", dict(idle, state="CAPTURING", phase="capturando", job=capture["job"],
                                 target="saturn",
                                 planet={"body": "saturn", "frames": 120, "total": 300, "kept": 45,
                                         "keep": 0.15, "done": False},
                                 polar={"alt_arcmin": 38.2, "az_arcmin": -51.6, "total_arcmin": 64.2,
                                        "aligned": False, "step": 3, "points": 3, "measured": True,
                                        "stale": False, "lat": -23.55}))
            out["state_capture"] = http.get("/api/v1/state").json()
    # o vetor da prova de pareamento: a MESMA conta tem de dar o MESMO resultado em Dart
    fingerprint, nonce_bytes = bytes(range(100, 132)), bytes(range(200, 232))
    out["pairing_vector"] = {
        "secret": b64u(SECRET), "nonce": b64u(nonce_bytes), "fingerprint": b64u(fingerprint),
        "client_name": "Pixel do Guilherme — ação",
        "proof": b64u(pairing_proof(SECRET, nonce_bytes, fingerprint, "Pixel do Guilherme — ação")),
        "uri": ("tele://pair?v=1&id=tele-6465&fp=" + b64u(fingerprint) + "&s=" + b64u(SECRET)
                + "&port=8443&host=192.168.3.221&ssid=Telescopio-6465&psk=senha-do-wifi"),
    }
    return out


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="não grava; falha se algo estiver desatualizado")
    a = ap.parse_args(argv)
    stale = []
    for name, data in build().items():
        path = OUT / f"{name}.json"
        text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        stale.append(path)
        if not a.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    verb = "desatualizado" if a.check else "gravado"
    for p in stale:
        print(f"{verb}: {p.relative_to(ROOT)}")
    print(f"{len(stale)} arquivo(s) {verb}(s)")
    return 1 if (a.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
