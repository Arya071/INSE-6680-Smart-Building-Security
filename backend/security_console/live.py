"""In-memory live session: custom events sent one at a time from the dashboard."""

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel

from .correlation import correlate
from .models import Event, Incident, Rule, Run
from .sensors import SIGNALS, ZONES, normalize
from .simulation import ALERT_KINDS

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
            "recorded_at": datetime.now(UTC),
        })
        with self._lock:
            self.events.append(event)
            self.incidents = correlate(self.events, self.rules)
            self.version += 1
        return event

    def clear(self) -> None:
        with self._lock:
            self.events = []
            self.incidents = []
            self.started_at = datetime.now(UTC)
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
