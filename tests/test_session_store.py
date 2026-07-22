"""T6 — persistência de sessão + telemetria."""
from src.core.session_store import save_session, load_session, Telemetry


def test_save_and_load_session(tmp_path):
    p = str(tmp_path / "s.json")
    save_session(p, {"target": "M31", "accepted": 42, "snr": 6.1})
    d = load_session(p)
    assert d["target"] == "M31" and d["accepted"] == 42 and d["snr"] == 6.1


def test_telemetry_append_and_read(tmp_path):
    t = Telemetry(str(tmp_path / "log.jsonl"))
    t.log(event="start", target="M31")
    t.log(event="frame", n=1, fwhm=3.2)
    rows = t.read()
    assert len(rows) == 2
    assert rows[0]["event"] == "start" and rows[1]["n"] == 1
