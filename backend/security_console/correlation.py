from collections import defaultdict
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path

from pydantic import TypeAdapter

from .models import Event, Incident, Rule, Severity


SEVERITY_RANK = {Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}


def load_rules(path: Path | None = None) -> list[Rule]:
    path = path or Path(__file__).with_name("rules.json")
    rules = TypeAdapter(list[Rule]).validate_json(path.read_bytes())
    if not rules or len({rule.id for rule in rules}) != len(rules):
        raise ValueError("Configure at least one rule and use unique rule IDs.")
    return rules


def event_key(event: Event):
    return event.occurred_at, event.id


def deduplicate(events: Iterable[Event]) -> list[Event]:
    unique: dict[str, Event] = {}
    for event in events:
        if event.id in unique and unique[event.id] != event:
            raise ValueError(f"Conflicting payloads for event {event.id}")
        unique[event.id] = event
    return sorted(unique.values(), key=event_key)


def _evidence(rule: Rule, trigger: Event, earlier: list[Event]) -> list[Event]:
    cutoff = trigger.occurred_at - timedelta(seconds=rule.window_seconds)
    next_time = trigger.occurred_at
    needed = list(rule.sequence[:-1])
    matches = [trigger]

    for event in reversed(earlier):
        if event.occurred_at < cutoff:
            break
        if event.occurred_at >= next_time or event.kind != needed[-1]:
            continue
        if (rule.restricted_only and not event.restricted) or (
            rule.after_hours_only and not event.after_hours
        ):
            continue
        matches.append(event)
        next_time = event.occurred_at
        needed.pop()
        if not needed:
            return list(reversed(matches))
    return []


def correlate(events: Iterable[Event], rules: list[Rule]) -> list[Incident]:
    history: dict[str, list[Event]] = defaultdict(list)
    rules_by_trigger: dict = defaultdict(list)
    for rule in rules:
        rules_by_trigger[rule.sequence[-1]].append(rule)

    incidents = []
    for event in deduplicate(events):
        candidates = []
        for rule in rules_by_trigger[event.kind]:
            if (rule.restricted_only and not event.restricted) or (
                rule.after_hours_only and not event.after_hours
            ):
                continue
            evidence = _evidence(rule, event, history[event.zone])
            if evidence:
                candidates.append((rule, evidence))
        history[event.zone].append(event)
        if not candidates:
            continue

        candidates.sort(key=lambda item: (
            -SEVERITY_RANK[item[0].severity], -len(item[0].sequence), item[0].id
        ))
        strongest = candidates[0][0]
        evidence = {item.id: item for _, match in candidates for item in match}
        incidents.append(Incident(
            id=f"INC-{len(incidents) + 1:03}",
            title=strongest.title,
            severity=strongest.severity,
            zone=event.zone,
            occurred_at=event.occurred_at,
            rule_ids=[rule.id for rule, _ in candidates],
            evidence=sorted(evidence.values(), key=event_key),
        ))
    return incidents
