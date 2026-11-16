import json

from fastapi.testclient import TestClient

from tech12000.hub import Hub
from tech12000.replay import replay
from tech12000.server.mobile import create_mobile_app
from tech12000.server.operator import create_operator_app
from tech12000.sources.wristband_serial import parse_imu_line

TOKEN = "secret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def mobile(rig):
    return TestClient(create_mobile_app(rig.eng, Hub(), lambda: TOKEN))


def test_mobile_requires_token(rig):
    c = mobile(rig)
    assert c.get("/api/v1/status").status_code == 401
    assert c.get("/api/v1/status", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/v1/status", headers=AUTH).status_code == 200


def test_mobile_has_no_control_routes(rig):
    app = create_mobile_app(rig.eng, Hub(), lambda: TOKEN)
    writes = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops
              if m not in ("get", "head")}
    assert writes == {("POST", "/api/v1/apns/token")}


def test_mobile_status_and_events(rig):
    rig.run(2.0)
    rig.inject("fall")
    rig.run(2.0)
    c = mobile(rig)
    s = c.get("/api/v1/status", headers=AUTH).json()
    assert s["state"] == "triggered" and s["deploy_outcome"] == "unknown_check_required"
    evs = c.get("/api/v1/events", headers=AUTH).json()["events"]
    assert len(evs) == 1 and evs[0]["is_test"] is True
    assert c.get(f"/api/v1/events/{evs[0]['event_id']}", headers=AUTH).json()["event_id"] == evs[0]["event_id"]


def test_mobile_ws_auth(rig):
    c = mobile(rig)
    with c.websocket_connect("/api/v1/ws", headers=AUTH) as ws:
        assert ws.receive_json()["type"] == "status"


def test_operator_controls_and_origin_check(rig):
    rig.run(2.0)
    app = create_operator_app(rig.eng, Hub(), lambda: TOKEN, lambda: TOKEN, 8000,
                              lambda k: rig.inject(k))
    c = TestClient(app, base_url="http://127.0.0.1")
    assert c.get("/").status_code == 200
    assert c.post("/api/mode", json={"mode": "demo"}).status_code == 200
    assert c.post("/api/mode", json={"mode": "armed", "confirm": "ARM"}).status_code == 409
    assert c.post("/api/reset", json={}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/reset", json={}).status_code == 200
    assert rig.eng.mode.value == "monitor"
    p = c.get("/api/pairing").json()
    assert p["token"] == TOKEN and "<svg" in p["qr_svg"]


def test_parse_receiver_imu_line():
    line = {"t": "imu", "dev": "a1b2", "ses": 7, "seq": 3, "tm": 123456, "ti": None, "trx": 99,
            "a": [0, 0, 9.8], "g": [1, 2, 3], "f": 0, "rssi": -40}
    s = parse_imu_line(line, 1.0, 2.0)
    assert s.seq == 3 and s.t_imu_us is None and s.accel == (0.0, 0.0, 9.8)


def test_record_and_replay_reproduces_trigger(tmp_path):
    from tech12000.config import Config
    from tech12000.recorder import Recorder
    from conftest import Rig

    cfg = Config()
    rig = Rig(cfg)
    rec = Recorder(tmp_path, cfg.model_dump(mode="json"), cfg.version_hash())
    rig.eng.rec = rec
    rig.run(2.0)
    rig.inject("fall")
    rig.run(2.0)
    rec.close()
    out = replay(rec.dir, cfg)
    assert [t["to"] for t in out["transitions"]] == rig.states
    assert len(out["events"]) == 1
    meta = json.loads((rec.dir / "meta.json").read_text())
    assert meta["config_version"] == cfg.version_hash()
