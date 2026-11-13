from datetime import timedelta

import pytest

from security_console.correlation import correlate, load_rules
from security_console.models import Severity
from security_console.simulation import SCENARIOS, evaluate, simulate


RULES = load_rules()


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_simulation_matches_reference_outcome(scenario_id):
    scenario = SCENARIOS[scenario_id]
    result = simulate(scenario, RULES)
    assert result.passed
    assert [incident.rule_ids[0] for incident in result.incidents] == scenario.info.expected_rules


def test_overlapping_rules_make_one_incident_with_ordered_evidence():
    result = simulate(SCENARIOS["tampering"], RULES)
    incident, = result.incidents
    assert incident.severity == Severity.CRITICAL
    assert incident.zone == "Server Room"
    assert incident.rule_ids == ["camera-controller-door", "camera-door"]
    assert [event.kind for event in incident.evidence] == [
        "camera_offline", "controller_offline", "forced_door"
    ]
    assert len({event.device_id for event in incident.evidence}) == 3


def test_duplicates_are_discarded_and_runs_are_deterministic():
    scenario = SCENARIOS["duplicate-events"]
    first = simulate(scenario, RULES)
    second = simulate(scenario, RULES)
    assert first == second
    assert first.duplicate_count == 2
    assert len(first.events) == 2
    assert len(first.incidents) == 1


def test_rule_window_is_inclusive_and_uses_event_time():
    camera, door = simulate(SCENARIOS["camera-door"], RULES).events
    exact = door.model_copy(update={"occurred_at": camera.occurred_at + timedelta(seconds=120)})
    late = exact.model_copy(update={"occurred_at": exact.occurred_at + timedelta(microseconds=1)})
    simultaneous = door.model_copy(update={"occurred_at": camera.occurred_at})
    assert len(correlate([exact, camera], RULES)) == 1
    assert correlate([late, camera], RULES) == []
    assert correlate([camera, simultaneous], RULES) == []


def test_rule_window_can_be_changed():
    original = next(rule for rule in RULES if rule.id == "camera-door")
    strict = original.model_copy(update={"window_seconds": 29})
    assert simulate(SCENARIOS["camera-door"], [strict]).incidents == []


def test_conflicting_message_id_is_rejected():
    camera, door = simulate(SCENARIOS["camera-door"], RULES).events
    conflict = door.model_copy(update={"id": camera.id})
    with pytest.raises(ValueError, match="Conflicting payloads"):
        correlate([camera, conflict], RULES)


def test_denial_rule_requires_three_distinct_messages():
    one, two, _, door = simulate(SCENARIOS["repeated-denials"], RULES).events
    assert correlate([one, two, two, door], RULES) == []


def test_evaluation_reports_scenario_counts_and_alert_reduction():
    report = evaluate(RULES)
    assert report["passed"] == report["total"] == 12
    assert report["true_positives"] == 5
    assert report["true_negatives"] == 7
    assert report["false_positives"] == report["false_negatives"] == 0
    assert report["incidents"] == 5
    assert report["alert_reduction"] == pytest.approx(1 - 5 / report["raw_alerts"])
