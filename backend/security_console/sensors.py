from .models import Event, Kind


ZONES = {
    "lobby": ("Main Lobby", False),
    "server": ("Server Room", True),
    "loading": ("Loading Bay", True),
    "office": ("Office Floor", False),
}

SIGNALS = {
    "camera": {"link_down": Kind.CAMERA_OFFLINE, "link_up": Kind.CAMERA_ONLINE},
    "access": {"allow": Kind.ACCESS_GRANTED, "deny": Kind.ACCESS_DENIED},
    "controller": {"no_response": Kind.CONTROLLER_OFFLINE},
    "door": {
        "contact_open": Kind.DOOR_OPEN,
        "forced_contact": Kind.FORCED_DOOR,
        "unverified_open": Kind.UNAUTHORIZED_OPEN,
    },
    "motion": {"occupied": Kind.MOTION},
    "environment": {"temperature_high": Kind.TEMPERATURE},
}

DEVICE_SUFFIX = {
    "camera": "CAM-01",
    "access": "READER-01",
    "controller": "CTRL-01",
    "door": "DOOR-01",
    "motion": "PIR-01",
    "environment": "ENV-01",
}


def normalize(raw: dict) -> Event:
    """Convert a simulated device payload to the shared event format."""
    source = raw["system"]
    location = raw["location"]
    zone, restricted = ZONES[location]
    return Event(
        id=raw["message_id"],
        device_id=f"{location.upper()}-{DEVICE_SUFFIX[source]}",
        source=source,
        zone=zone,
        kind=SIGNALS[source][raw["signal"]],
        occurred_at=raw["recorded_at"],
        restricted=restricted,
    )
