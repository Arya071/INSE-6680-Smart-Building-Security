from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


BUILDING_TIME = ZoneInfo("America/Toronto")


class Kind(StrEnum):
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_ONLINE = "camera_online"
    CONTROLLER_OFFLINE = "controller_offline"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    DOOR_OPEN = "door_open"
    FORCED_DOOR = "forced_door"
    UNAUTHORIZED_OPEN = "unauthorized_open"
    MOTION = "motion_detected"
    TEMPERATURE = "temperature_warning"


class Severity(StrEnum):
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    source: str
    zone: str = Field(min_length=1)
    kind: Kind
    occurred_at: AwareDatetime
    restricted: bool

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @property
    def after_hours(self) -> bool:
        local = self.occurred_at.astimezone(BUILDING_TIME)
        return local.weekday() >= 5 or not 7 <= local.hour < 19


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Severity
    sequence: tuple[Kind, ...] = Field(min_length=2)
    window_seconds: int = Field(gt=0)
    restricted_only: bool = False
    after_hours_only: bool = False


class Incident(BaseModel):
    id: str
    title: str
    severity: Severity
    zone: str
    occurred_at: AwareDatetime
    rule_ids: list[str]
    evidence: list[Event]


class ScenarioInfo(BaseModel):
    id: str
    name: str
    description: str
    expected_rules: list[str]


class RunSummary(BaseModel):
    id: str
    scenario_id: str
    created_at: AwareDatetime
    event_count: int
    duplicate_count: int
    raw_alert_count: int
    incident_count: int
    passed: bool


class Run(RunSummary):
    events: list[Event]
    incidents: list[Incident]
