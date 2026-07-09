"""Test dell'app web con TestClient e LLM finto: ciclo run completo
via API, snapshot serializzati, gating della chat."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from fusor_sim.app.server import create_app


def _fake_llm(messages):
    return json.dumps(
        {
            "reply": "Imposto la pressione a 0.8 Pa.",
            "intents": [
                {"action": "SET", "target": "physics.pressure_pa", "value": 0.8}
            ],
            "start_run": False,
        }
    )


@pytest.fixture()
def client():
    app = create_app(llm=_fake_llm)
    with TestClient(app) as c:
        yield c


def _wait_done(client, timeout_s=60.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = client.get("/api/status").json()["state"]
        if state == "done":
            return
        time.sleep(0.1)
    raise TimeoutError("il run non è terminato in tempo")


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "fusor-sim" in resp.text


def test_status_initial(client):
    data = client.get("/api/status").json()
    assert data["state"] == "idle"
    assert data["physics"]["cathode_voltage_v"] == -40000
    assert data["llm_available"] is True


def test_chat_applies_intent(client):
    resp = client.post("/api/chat", json={"message": "porta la pressione a 0.8"})
    data = resp.json()
    assert data["intents"][0]["accepted"] is True
    assert client.get("/api/status").json()["physics"]["pressure_pa"] == 0.8
    assert data["sources"]  # il RAG ha fornito estratti


def test_full_run_via_api(client):
    resp = client.post(
        "/api/run",
        json={"max_steps": 600, "n_particles": 1000, "snapshot_interval": 200, "probe": False},
    )
    assert resp.status_code == 200
    _wait_done(client)

    data = client.get("/api/snapshot").json()
    snap, series = data["snapshot"], data["series"]
    assert snap["meta"]["status"] == "done"
    assert len(series) == 3
    assert snap["verdict"]["honest_summary"]
    assert len(snap["fields"]["r_m"]) == len(snap["fields"]["potential_v"])
    assert snap["spectrum"]["counts"]

    # a run finito la chat torna disponibile (auto-reset a IDLE)
    resp = client.post("/api/chat", json={"message": "com'è andata?"})
    assert "stato DONE" not in resp.json()["reply"]
    assert client.get("/api/status").json()["state"] == "idle"


def test_pause_resume_cycle(client):
    client.post(
        "/api/run",
        json={"max_steps": 4000, "n_particles": 1000, "snapshot_interval": 100, "probe": False},
    )
    # attende che il run sia partito davvero
    deadline = time.time() + 10
    while client.get("/api/status").json()["state"] != "run":
        assert time.time() < deadline
        time.sleep(0.05)

    assert client.post("/api/pause").status_code == 200
    deadline = time.time() + 10
    while client.get("/api/status").json()["state"] != "paused":
        assert time.time() < deadline
        time.sleep(0.05)

    # in pausa la chat funziona
    resp = client.post("/api/chat", json={"message": "quanto vale la pressione?"})
    assert resp.status_code == 200

    assert client.post("/api/resume").status_code == 200
    _wait_done(client)


def test_run_conflict_while_running(client):
    client.post(
        "/api/run",
        json={"max_steps": 4000, "n_particles": 1000, "snapshot_interval": 100, "probe": False},
    )
    deadline = time.time() + 10
    while client.get("/api/status").json()["state"] != "run":
        assert time.time() < deadline
        time.sleep(0.05)
    # un secondo run durante RUN è un conflitto, non un crash
    resp = client.post(
        "/api/run",
        json={"max_steps": 400, "n_particles": 1000, "snapshot_interval": 200, "probe": False},
    )
    assert resp.status_code == 409
    # e la chat è esplicitamente gated
    resp = client.post("/api/chat", json={"message": "cambia qualcosa"})
    assert "RUN" in resp.json()["reply"]
    _wait_done(client)


def test_intent_endpoint_editor_path(client):
    """L'editor 3D passa dallo stesso percorso validato della chat."""
    resp = client.post(
        "/api/intent",
        json={"action": "SET", "target": "geometry.cathode_offset_x_m", "value": 0.03},
    )
    assert resp.json()["accepted"] is True

    status = client.get("/api/status").json()
    assert status["geometry"]["cathode_offset_x_m"] == 0.03
    assert status["judgeable"] is False
    assert "non concentrica" in status["judgeable_reason"]

    # un run su geometria non giudicabile è un conflitto dichiarato
    resp = client.post(
        "/api/run",
        json={"max_steps": 400, "n_particles": 1000, "snapshot_interval": 200, "probe": False},
    )
    assert resp.status_code == 409
    assert "non concentrica" in resp.json()["detail"]

    # intent fisicamente impossibile: rifiutato col motivo
    resp = client.post(
        "/api/intent",
        json={"action": "SET", "target": "geometry.cathode_offset_x_m", "value": 0.2},
    )
    data = resp.json()
    assert data["accepted"] is False
    # intent su campo non-utente: bloccato dal contratto
    resp = client.post(
        "/api/intent",
        json={"action": "SET", "target": "numerics.dt_s", "value": 1e-12},
    )
    assert resp.json()["accepted"] is False


def test_field_preview_endpoint(client):
    client.post(
        "/api/intent",
        json={"action": "SET", "target": "geometry.cathode_offset_x_m", "value": 0.03},
    )
    resp = client.post("/api/field_preview")
    assert resp.status_code == 200
    fp = resp.json()["field_preview"]
    assert fp["verdict"]["scope"] == "field_only"
    assert fp["verdict"]["produces_fusion"] is None
    assert len(fp["slice_z0_v"]) == fp["n_nodes"]
    assert fp["cathode_offset_m"] == [0.03, 0.0, 0.0]
    # l'anteprima resta disponibile nel payload snapshot
    assert client.get("/api/snapshot").json()["field_preview"] is not None


def test_reset(client):
    client.post(
        "/api/run",
        json={"max_steps": 400, "n_particles": 1000, "snapshot_interval": 200, "probe": False},
    )
    _wait_done(client)
    client.post("/api/reset")
    data = client.get("/api/status").json()
    assert data["state"] == "idle"
    assert client.get("/api/snapshot").json()["snapshot"] is None
