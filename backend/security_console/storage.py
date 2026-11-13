import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import Run, RunSummary
from .simulation import Simulation


class RunStore:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL,
                    raw_alert_count INTEGER NOT NULL,
                    incident_count INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    snapshot TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS runs_by_time ON runs (created_at DESC)")

    def save(self, scenario_id: str, result: Simulation, seed: bool = False) -> Run:
        run = Run(
            id="demo" if seed else uuid4().hex,
            scenario_id=scenario_id,
            created_at=datetime.now(UTC),
            event_count=len(result.events),
            duplicate_count=result.duplicate_count,
            raw_alert_count=result.raw_alert_count,
            incident_count=len(result.incidents),
            passed=result.passed,
            events=result.events,
            incidents=result.incidents,
        )
        summary = RunSummary.model_validate(run.model_dump()).model_dump(mode="json")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""
                INSERT INTO runs VALUES (
                    :id, :scenario_id, :created_at, :event_count, :duplicate_count,
                    :raw_alert_count, :incident_count, :passed, :snapshot
                ) ON CONFLICT(id) DO NOTHING
            """, {**summary, "snapshot": run.model_dump_json()})
        return run

    def list(self, limit: int) -> list[RunSummary]:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""
                SELECT id, scenario_id, created_at, event_count, duplicate_count,
                       raw_alert_count, incident_count, passed
                FROM runs ORDER BY created_at DESC, id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [RunSummary.model_validate(dict(row)) for row in rows]

    def delete_all(self) -> int:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute("DELETE FROM runs").rowcount

    def get(self, run_id: str) -> Run | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT snapshot FROM runs WHERE id = ?", (run_id,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None
