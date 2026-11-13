import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .correlation import load_rules
from .live import LiveEventRequest, LiveOptions, LiveSession, options as live_options
from .models import Event, Incident, Rule, Run, RunSummary, ScenarioInfo
from .simulation import SCENARIOS, Simulation, evaluate, simulate
from .storage import RunStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RunRequest(BaseModel):
    scenario_id: str


class LiveState(BaseModel):
    version: int
    run: Run


class LiveEventResponse(BaseModel):
    version: int
    event: Event
    incident_count: int
    new_incident: Incident | None


def create_app(
    database: Path | None = None,
    rule_file: Path | None = None,
    *,
    serve_frontend: bool = True,
    seed_demo: bool = True,
) -> FastAPI:
    database = database or Path(os.getenv("SECURITY_DB", PROJECT_ROOT / "data" / "security.sqlite3"))
    if rule_file is None and (configured_rules := os.getenv("SECURITY_RULES")):
        rule_file = Path(configured_rules)
    rules = load_rules(rule_file)
    store = RunStore(database)
    live = LiveSession(rules)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize()
        if seed_demo and not store.list(limit=1):
            store.save("tampering", simulate(SCENARIOS["tampering"], rules), seed=True)
        yield

    app = FastAPI(title="Smart Building Security", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/scenarios")
    def scenarios() -> list[ScenarioInfo]:
        return [scenario.info for scenario in SCENARIOS.values()]

    @app.get("/api/rules")
    def active_rules() -> list[Rule]:
        return rules

    @app.get("/api/evaluation")
    def evaluation() -> dict:
        return evaluate(rules)

    @app.get("/api/runs")
    def runs(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[RunSummary]:
        return store.list(limit)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Run:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "Simulation run not found.")
        return run

    @app.post("/api/runs", status_code=201)
    def create_run(request: RunRequest) -> Run:
        scenario = SCENARIOS.get(request.scenario_id)
        if scenario is None:
            raise HTTPException(404, "Simulation scenario not found.")
        return store.save(request.scenario_id, simulate(scenario, rules))

    @app.delete("/api/runs")
    def delete_runs() -> dict:
        return {"deleted": store.delete_all()}

    @app.get("/api/live")
    def live_state() -> LiveState:
        return LiveState(version=live.version, run=live.snapshot())

    @app.get("/api/live/options")
    def live_choices() -> LiveOptions:
        return live_options()

    @app.post("/api/live/events", status_code=201)
    def live_event(request: LiveEventRequest) -> LiveEventResponse:
        before = len(live.incidents)
        try:
            event = live.add(request)
        except ValueError as failure:
            raise HTTPException(422, str(failure)) from failure
        incidents = live.incidents
        return LiveEventResponse(
            version=live.version,
            event=event,
            incident_count=len(incidents),
            new_incident=incidents[-1] if len(incidents) > before else None,
        )

    @app.delete("/api/live")
    def live_clear() -> dict:
        live.clear()
        return {"version": live.version}

    @app.post("/api/live/save", status_code=201)
    def live_save() -> Run:
        snapshot = live.snapshot()
        if not snapshot.events:
            raise HTTPException(409, "The live session has no events to save.")
        return store.save("live", Simulation(
            events=snapshot.events,
            incidents=snapshot.incidents,
            duplicate_count=0,
            raw_alert_count=snapshot.raw_alert_count,
            passed=True,
        ))

    dist = PROJECT_ROOT / "frontend" / "dist"
    if serve_frontend and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
