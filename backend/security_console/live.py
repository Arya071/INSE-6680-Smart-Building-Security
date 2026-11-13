"""In-memory live session: custom events sent one at a time from the dashboard."""

import time
from datetime import UTC, datetime, timedelta
from threading import Lock, Thread
from uuid import uuid4

from pydantic import BaseModel, Field

from .correlation import correlate
from .models import BUILDING_TIME, Event, Incident, Kind, Rule, Run
from .sensors import SIGNALS, ZONES, normalize
from .simulation import ALERT_KINDS

SIGNAL_FOR_KIND = {kind: (system, signal) for system, codes in SIGNALS.items() for signal, kind in codes.items()}

LIVE_RUN_ID = "live"

LABELS = {
    ("camera", "link_down"): "Camera offline",
    ("camera", "link_up"): "Camera restored",
    ("controller", "no_response"): "Controller unavailable",
    ("access", "allow"): "Access granted",
    ("access", "deny"): "Access denied",
    ("door", "contact_open"): "Door opened",
    ("door", "forced_contact"): "Forced door opening",
    ("door", "unverified_open"): "Unverified door opening",
    ("motion", "occupied"): "Motion detected",
    ("environment", "temperature_high"): "Temperature warning",
}


class LiveEventRequest(BaseModel):
    location: str
    system: str
    signal: str
    occurred_at: datetime | None = None


class PlayRequest(BaseModel):
    rule_id: str
    location: str | None = None
    interval_seconds: float = Field(default=1.2, ge=0, le=30)


class Playback(BaseModel):
    rule_id: str
    title: str
    location: str
    zone: str
    step: int
    total: int
    done: bool
    after_hours_shift: bool
    incident_id: str | None = None


class LiveOptions(BaseModel):
    zones: list[dict]
    signals: list[dict]


def options() -> LiveOptions:
    return LiveOptions(
        zones=[{"id": key, "name": name, "restricted": restricted} for key, (name, restricted) in ZONES.items()],
        signals=[
            {"system": system, "signal": signal, "kind": kind, "label": LABELS[(system, signal)]}
            for system, codes in SIGNALS.items() for signal, kind in codes.items()
        ],
    )


class LiveSession:
    def __init__(self, rules: list[Rule]):
        self.rules = rules
        self.events: list[Event] = []
        self.incidents: list[Incident] = []
        self.started_at = datetime.now(UTC)
        self.version = 0
        self.playback: Playback | None = None
        self._lock = Lock()

    def add(self, request: LiveEventRequest) -> Event:
        if request.location not in ZONES:
            raise ValueError("Unknown zone.")
        if request.signal not in SIGNALS.get(request.system, {}):
            raise ValueError("Unknown event type for this device.")
        event = normalize({
            "message_id": "LIVE-" + uuid4().hex[:8].upper(),
            "system": request.system,
            "location": request.location,
            "signal": request.signal,
            "recorded_at": request.occurred_at or datetime.now(UTC),
        })
        with self._lock:
            self.events.append(event)
            self.incidents = correlate(self.events, self.rules)
            self.version += 1
        return event

    def clear(self) -> None:
        with self._lock:
            if self.playback and not self.playback.done:
                raise RuntimeError("A rule playback is in progress. Wait for it to finish.")
            self.events = []
            self.incidents = []
            self.playback = None
            self.started_at = datetime.now(UTC)
            self.version += 1

    def play(self, rule: Rule, location: str | None, interval: float) -> Playback:
        """Replay a rule's sequence into the live session one event at a time, in the background."""
        if location is None:
            location = "server" if rule.restricted_only else "lobby"
        if location not in ZONES:
            raise ValueError("Unknown zone.")
        zone, restricted = ZONES[location]
        if rule.restricted_only and not restricted:
            raise ValueError(f"{rule.title} applies to restricted areas only. Choose a restricted zone.")
        with self._lock:
            if self.playback and not self.playback.done:
                raise RuntimeError("A rule playback is already in progress.")
            now = datetime.now(UTC)
            local = now.astimezone(BUILDING_TIME)
            shift = rule.after_hours_only and local.weekday() < 5 and 7 <= local.hour < 19
            self.playback = Playback(
                rule_id=rule.id, title=rule.title, location=location, zone=zone,
                step=0, total=len(rule.sequence), done=False, after_hours_shift=shift,
            )
            self.version += 1
        # After-hours rules cannot match during staffed hours, so stamp those events at 22:00 building time.
        base = local.replace(hour=22, minute=0, second=0, microsecond=0).astimezone(UTC) if shift else None
        Thread(target=self._run_playback, args=(rule, location, interval, base), daemon=True).start()
        return self.playback

    def _run_playback(self, rule: Rule, location: str, interval: float, base: datetime | None) -> None:
        for index, kind in enumerate(rule.sequence):
            if index:
                time.sleep(interval)
            system, signal = SIGNAL_FOR_KIND[Kind(kind)]
            stamp = base + timedelta(seconds=index * max(interval, 1)) if base else None
            before = len(self.incidents)
            self.add(LiveEventRequest(location=location, system=system, signal=signal, occurred_at=stamp))
            with self._lock:
                raised = self.incidents[-1].id if len(self.incidents) > before else None
                self.playback = self.playback.model_copy(update={
                    "step": index + 1,
                    "done": index + 1 == len(rule.sequence),
                    "incident_id": raised or self.playback.incident_id,
                })
                self.version += 1

    def snapshot(self) -> Run:
        with self._lock:
            return Run(
                id=LIVE_RUN_ID,
                scenario_id=LIVE_RUN_ID,
                created_at=self.started_at,
                event_count=len(self.events),
                duplicate_count=0,
                raw_alert_count=sum(event.kind in ALERT_KINDS for event in self.events),
                incident_count=len(self.incidents),
                passed=True,
                events=list(self.events),
                incidents=list(self.incidents),
            )
