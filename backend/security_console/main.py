import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .live import LiveEventRequest, LiveOptions, LiveSession, PlayRequest, Playback, options as live_options
from .rulebook import RuleBook, RuleDraft
from .models import Event, Incident, Rule, Run, RunSummary, ScenarioInfo
from .simulation import SCENARIOS, Simulation, evaluate, simulate
from .storage import RunStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RunRequest(BaseModel):
    scenario_id: str


class LiveState(BaseModel):
    version: int
    run: Run
    playback: Playback | None = None


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
    book = RuleBook(rule_file, database.parent / "custom_rules.json")
    rules = book.rules
    store = RunStore(database)
    live = LiveSession(rules)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize()
        book.load()
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

    @app.post("/api/rules", status_code=201)
    def create_rule(draft: RuleDraft) -> Rule:
        return book.add(draft)

    @app.delete("/api/rules/{rule_id}")
    def delete_rule(rule_id: str) -> dict:
        if any(rule.id == rule_id for rule in book.builtin):
            raise HTTPException(409, "Built-in rules are edited in rules.json, not deleted here.")
        if not book.remove(rule_id):
            raise HTTPException(404, "Custom rule not found.")
        return {"deleted": rule_id}

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
        return LiveState(version=live.version, run=live.snapshot(), playback=live.playback)

    @app.post("/api/live/play", status_code=202)
    def live_play(request: PlayRequest) -> Playback:
        rule = next((item for item in rules if item.id == request.rule_id), None)
        if rule is None:
            raise HTTPException(404, "Rule not found.")
        try:
            return live.play(rule, request.location, request.interval_seconds)
        except ValueError as failure:
            raise HTTPException(422, str(failure)) from failure
        except RuntimeError as failure:
            raise HTTPException(409, str(failure)) from failure

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
        try:
            live.clear()
        except RuntimeError as failure:
            raise HTTPException(409, str(failure)) from failure
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
