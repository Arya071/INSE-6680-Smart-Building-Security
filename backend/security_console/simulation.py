from dataclasses import dataclass
from datetime import datetime, timedelta

from .correlation import correlate, deduplicate
from .models import BUILDING_TIME, Event, Incident, Kind, Rule, ScenarioInfo
from .sensors import normalize


@dataclass(frozen=True)
class Signal:
    seconds: int
    zone: str
    source: str
    code: str


@dataclass(frozen=True)
class Scenario:
    info: ScenarioInfo
    signals: tuple[Signal, ...]
    hour: int = 10
    replay: bool = False


def scenario(id, name, description, expected, *signals, hour=10, replay=False):
    return Scenario(
        ScenarioInfo(id=id, name=name, description=description, expected_rules=expected),
        tuple(Signal(*signal) for signal in signals),
        hour,
        replay,
    )


CAMERA = (0, "server", "camera", "link_down")
FORCED = (30, "server", "door", "forced_contact")
DENIALS = tuple((offset, "server", "access", "deny") for offset in (0, 8, 16))
AFTER_HOURS = (
    (0, "loading", "door", "unverified_open"),
    (22, "loading", "motion", "occupied"),
)

SCENARIOS = {item.info.id: item for item in (
    scenario("tampering", "Camera and controller tampering",
             "A camera and controller go offline before an independently monitored door is forced open.",
             ["camera-controller-door"],
             (-80, "lobby", "access", "allow"),
             (-72, "lobby", "door", "contact_open"),
             (-56, "office", "motion", "occupied"),
             CAMERA,
             (12, "server", "controller", "no_response"),
             FORCED,
             (42, "server", "motion", "occupied"),
             (54, "loading", "environment", "temperature_high"),
             (72, "server", "camera", "link_up")),
    scenario("camera-door", "Camera outage and forced entry",
             "A restricted-area door is forced open 30 seconds after a camera outage.",
             ["camera-door"], CAMERA, FORCED),
    scenario("repeated-denials", "Repeated denied access",
             "Three denied badge attempts are followed by a forced opening.",
             ["denials-door"], *DENIALS, FORCED),
    scenario("after-hours", "After-hours entry",
             "An unverified loading bay door opening is followed by motion after staffed hours.",
             ["after-hours-motion"], *AFTER_HOURS, hour=22),
    scenario("authorized-entry", "Authorized entry",
             "A valid badge and a routine door opening occur in the main lobby.",
             [], (0, "lobby", "access", "allow"), (4, "lobby", "door", "contact_open")),
    scenario("camera-outage", "Isolated camera outage",
             "One camera loses its connection and later comes back online.",
             [], CAMERA, (42, "server", "camera", "link_up")),
    scenario("different-zones", "Events in different zones",
             "A camera outage and a forced opening occur close together in different zones.",
             [], CAMERA, (30, "loading", "door", "forced_contact")),
    scenario("outside-window", "Outside the rule window",
             "A camera outage precedes a forced opening by ten minutes.",
             [], CAMERA, (600, "server", "door", "forced_contact")),
    scenario("duplicate-events", "Duplicate sensor messages",
             "The camera and door each retransmit the same message ID.",
             ["camera-door"], CAMERA, FORCED, replay=True),
    scenario("staffed-hours", "Motion during staffed hours",
             "The same door-and-motion sequence takes place during staffed hours.",
             [], *AFTER_HOURS),
    scenario("reverse-order", "Events in reverse order",
             "The forced opening occurs before the camera outage.",
             [], (0, "server", "door", "forced_contact"), (30, "server", "camera", "link_down")),
    scenario("public-zone", "Events in a public zone",
             "A camera outage and a forced opening take place in the main lobby.",
             [], (0, "lobby", "camera", "link_down"), (30, "lobby", "door", "forced_contact")),
)}


ALERT_KINDS = {
    Kind.CAMERA_OFFLINE, Kind.CONTROLLER_OFFLINE, Kind.ACCESS_DENIED,
    Kind.FORCED_DOOR, Kind.UNAUTHORIZED_OPEN, Kind.MOTION, Kind.TEMPERATURE,
}


@dataclass(frozen=True)
class Simulation:
    events: list[Event]
    incidents: list[Incident]
    duplicate_count: int
    raw_alert_count: int
    passed: bool


def simulate(item: Scenario, rules: list[Rule]) -> Simulation:
    base = datetime(2026, 11, 12, item.hour, tzinfo=BUILDING_TIME)
    payloads = [
        {"message_id": f"EVT-{index:03}", "system": signal.source,
         "location": signal.zone, "signal": signal.code,
         "recorded_at": base + timedelta(seconds=signal.seconds)}
        for index, signal in enumerate(item.signals, 1)
    ]
    if item.replay:
        payloads.extend(payloads[:])
    events = deduplicate(normalize(payload) for payload in payloads)
    incidents = correlate(events, rules)
    return Simulation(
        events=events,
        incidents=incidents,
        duplicate_count=len(payloads) - len(events),
        raw_alert_count=sum(event.kind in ALERT_KINDS for event in events),
        passed=[incident.rule_ids[0] for incident in incidents] == item.info.expected_rules,
    )


def evaluate(rules: list[Rule]) -> dict:
    rows = []
    for item in SCENARIOS.values():
        result = simulate(item, rules)
        rows.append({
            "scenario": item.info,
            "actual_rules": [incident.rule_ids[0] for incident in result.incidents],
            "events": len(result.events),
            "raw_alerts": result.raw_alert_count,
            "incidents": len(result.incidents),
            "passed": result.passed,
        })

    tp = sum(bool(row["scenario"].expected_rules) and row["incidents"] > 0 for row in rows)
    fp = sum(not row["scenario"].expected_rules and row["incidents"] > 0 for row in rows)
    tn = sum(not row["scenario"].expected_rules and row["incidents"] == 0 for row in rows)
    fn = sum(bool(row["scenario"].expected_rules) and row["incidents"] == 0 for row in rows)
    raw = sum(row["raw_alerts"] for row in rows)
    incidents = sum(row["incidents"] for row in rows)
    return {
        "scenarios": rows,
        "passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "detection_rate": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "raw_alerts": raw,
        "incidents": incidents,
        "alert_reduction": (raw - incidents) / raw if raw else None,
    }
