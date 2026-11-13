import time

from fastapi.testclient import TestClient

from security_console.main import create_app


def test_run_lifecycle_and_restart(tmp_path):
    path = tmp_path / "test.sqlite3"
    app = create_app(path, serve_frontend=False, seed_demo=False)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/runs").json() == []
        assert len(client.get("/api/scenarios").json()) == 12
        assert len(client.get("/api/rules").json()) == 4

        response = client.post("/api/runs", json={"scenario_id": "tampering"})
        assert response.status_code == 201
        run = response.json()
        assert run["event_count"] == 9
        assert run["incidents"][0]["severity"] == "critical"
        assert run["passed"]
        assert client.get("/api/runs").json()[0]["id"] == run["id"]
        assert client.get("/api/evaluation").json()["passed"] == 12
        assert client.post("/api/runs", json={"scenario_id": "missing"}).status_code == 404
        assert client.get("/api/runs/missing").status_code == 404
        assert client.get("/api/runs?limit=0").status_code == 422

    with TestClient(create_app(path, serve_frontend=False)) as client:
        assert client.get(f"/api/runs/{run['id']}").json() == run
        assert len(client.get("/api/runs").json()) == 1


def test_demo_is_seeded_once_and_simulations_stay_isolated(tmp_path):
    path = tmp_path / "test.sqlite3"
    app = create_app(path, serve_frontend=False)
    for _ in range(2):
        with TestClient(app) as client:
            assert [run["id"] for run in client.get("/api/runs").json()] == ["demo"]

    with TestClient(app) as client:
        run = client.post("/api/runs", json={"scenario_id": "camera-outage"}).json()
        assert run["incidents"] == []
        assert len(run["events"]) == 2
        assert client.get("/api/runs/demo").json()["incident_count"] == 1


def test_live_session_correlates_custom_events_and_can_be_reset(tmp_path):
    app = create_app(tmp_path / "test.sqlite3", serve_frontend=False)
    with TestClient(app) as client:
        choices = client.get("/api/live/options").json()
        assert {zone["id"] for zone in choices["zones"]} == {"lobby", "server", "loading", "office"}
        assert len(choices["signals"]) == 10

        state = client.get("/api/live").json()
        assert state["version"] == 0 and state["run"]["event_count"] == 0

        first = client.post("/api/live/events", json={"location": "server", "system": "camera", "signal": "link_down"})
        assert first.status_code == 201 and first.json()["new_incident"] is None
        second = client.post("/api/live/events", json={"location": "server", "system": "door", "signal": "forced_contact"})
        assert second.json()["incident_count"] == 1
        assert second.json()["new_incident"]["severity"] == "high"
        assert second.json()["event"]["id"].startswith("LIVE-")

        state = client.get("/api/live").json()
        assert state["version"] == 2 and state["run"]["incident_count"] == 1
        assert client.post("/api/live/events", json={"location": "nowhere", "system": "camera", "signal": "link_down"}).status_code == 422
        assert client.post("/api/live/events", json={"location": "server", "system": "camera", "signal": "melt"}).status_code == 422

        saved = client.post("/api/live/save").json()
        assert saved["scenario_id"] == "live" and saved["incident_count"] == 1
        assert {run["id"] for run in client.get("/api/runs").json()} == {"demo", saved["id"]}

        assert client.delete("/api/live").json()["version"] == 3
        assert client.get("/api/live").json()["run"]["event_count"] == 0
        assert client.post("/api/live/save").status_code == 409

        assert client.delete("/api/runs").json()["deleted"] == 2
        assert client.get("/api/runs").json() == []


def wait_for_playback(client, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = client.get("/api/live").json()
        if state["playback"] and state["playback"]["done"]:
            return state
        time.sleep(0.05)
    raise AssertionError("playback did not finish")


def test_custom_rules_persist_and_rule_playback_raises_an_incident(tmp_path):
    path = tmp_path / "test.sqlite3"
    app = create_app(path, serve_frontend=False, seed_demo=False)
    draft = {
        "title": "Tailgating after denial", "severity": "medium",
        "sequence": ["access_denied", "door_open"], "window_seconds": 45,
    }
    with TestClient(app) as client:
        created = client.post("/api/rules", json=draft).json()
        assert created["custom"] and created["id"].startswith("tailgating-after-denial-")
        assert "within 45 seconds" in created["description"]
        assert len(client.get("/api/rules").json()) == 5
        assert client.post("/api/rules", json={**draft, "sequence": ["door_open"]}).status_code == 422
        assert client.delete("/api/rules/camera-door").status_code == 409

        started = client.post("/api/live/play", json={"rule_id": created["id"], "location": "lobby", "interval_seconds": 0})
        assert started.status_code == 202 and started.json()["total"] == 2
        state = wait_for_playback(client)
        assert state["playback"]["incident_id"] == "INC-001"
        assert state["run"]["incidents"][0]["rule_ids"] == [created["id"]]
        assert [event["kind"] for event in state["run"]["events"]] == ["access_denied", "door_open"]

        assert client.post("/api/live/play", json={"rule_id": "camera-door", "location": "lobby"}).status_code == 422
        assert client.post("/api/live/play", json={"rule_id": "missing"}).status_code == 404

        after_hours = client.post("/api/live/play", json={"rule_id": "after-hours-motion", "interval_seconds": 0}).json()
        assert after_hours["location"] == "server"
        assert wait_for_playback(client)["playback"]["incident_id"] == "INC-002"

        assert client.delete(f"/api/rules/{created['id']}").json() == {"deleted": created["id"]}
        assert client.delete("/api/rules/missing").status_code == 404

    with TestClient(app) as client:
        assert len(client.get("/api/rules").json()) == 4
        client.post("/api/rules", json=draft)
    with TestClient(create_app(path, serve_frontend=False, seed_demo=False)) as client:
        assert [rule["custom"] for rule in client.get("/api/rules").json()] == [False] * 4 + [True]
