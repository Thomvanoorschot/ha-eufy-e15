"""Pure decoding of E15 data points and derivation of the mower's activity.

Nothing in this module touches the network or Home Assistant, so every rule here is
covered by unit tests with synthetic payloads. Raw data points arrive as base64 text
whose bytes are a protobuf message of plain varint fields.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from enum import StrEnum

# DP 107 field 1: the mission.
MISSION_NONE = 0
MISSION_RECHARGE = 1
MOWING_MISSIONS: dict[int, str] = {
    2: "whole_lawn",
    4: "mapping_while_mowing",
    5: "temporary",
    7: "remote_control",
    8: "scheduled_whole_lawn",
    9: "scheduled_mapping",
    10: "zone",
    16: "scheduled_zone",
    17: "box",
    18: "edge",
    22: "scheduled_edge",
}
MISSIONS: dict[int, str] = {
    MISSION_NONE: "none",
    MISSION_RECHARGE: "recharge",
    3: "mapping",
    **MOWING_MISSIONS,
}

# DP 107 field 2: the sub-mission (phase).
SUB_MISSION_SAVING_MAP = 5
SUB_MISSIONS: dict[int, str] = {
    0: "none",
    1: "relocating",
    3: "leaving_station",
    5: "saving_map",
    6: "setting_blade_height",
    9: "defogging",
}

# DP 107 field 3: the mission state.
STATE_IDLE = 0
STATE_RUNNING = 1
STATE_PAUSED = 2
STATE_ABORTED = 3
STATE_COMPLETE = 4

OTHER = "other"


class Activity(StrEnum):
    """Activity derived from local data. Mirrors HA's LawnMowerActivity values."""

    MOWING = "mowing"
    PAUSED = "paused"
    RETURNING = "returning"
    DOCKED = "docked"
    IDLE = "idle"
    ERROR = "error"


class MalformedPayload(ValueError):
    """A raw data point that is not the expected varint message."""


def decode_raw(value: str) -> bytes:
    """Decode the base64 envelope of a raw data point."""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError) as err:
        raise MalformedPayload(f"not base64: {err}") from err


def decode_varint_message(data: bytes) -> dict[int, int]:
    """Decode a protobuf message that holds only varint fields.

    An empty message and the single zero byte the E15 sends as its default payload
    both decode to ``{}``: every field then reads as its zero default.
    """
    if data in (b"", b"\x00"):
        return {}
    fields: dict[int, int] = {}
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        field, wire_type = tag >> 3, tag & 0x07
        if field == 0:
            raise MalformedPayload("field number 0")
        if wire_type != 0:
            raise MalformedPayload(f"field {field} has wire type {wire_type}")
        if field in fields:
            raise MalformedPayload(f"field {field} repeated")
        fields[field], pos = _read_varint(data, pos)
    return fields


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise MalformedPayload("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
    raise MalformedPayload("varint longer than ten bytes")


@dataclass(frozen=True, slots=True)
class MissionStatus:
    """DP 107 ``robot_status``."""

    mission: int = 0
    sub_mission: int = 0
    state: int = 0
    power_mode: int = 0
    error: bool = False
    saving_data: bool = False

    @classmethod
    def from_raw(cls, value: str) -> MissionStatus:
        fields = decode_varint_message(decode_raw(value))
        return cls(
            mission=fields.get(1, 0),
            sub_mission=fields.get(2, 0),
            state=fields.get(3, 0),
            power_mode=fields.get(4, 0),
            error=bool(fields.get(5, 0)),
            saving_data=bool(fields.get(6, 0)),
        )

    @property
    def is_mowing_mission(self) -> bool:
        return self.mission in MOWING_MISSIONS

    @property
    def is_recharge_mission(self) -> bool:
        return self.mission == MISSION_RECHARGE

    @property
    def is_saving_map(self) -> bool:
        return self.mission == MISSION_NONE and self.sub_mission == SUB_MISSION_SAVING_MAP

    @property
    def mission_name(self) -> str:
        return MISSIONS.get(self.mission, OTHER)

    @property
    def sub_mission_name(self) -> str:
        return SUB_MISSIONS.get(self.sub_mission, OTHER)


@dataclass(frozen=True, slots=True)
class BatteryStatus:
    """DP 108 ``battery_status``. Field 2 is the charger contact."""

    charge_state: int = 0
    charger_connected: bool = False

    @classmethod
    def from_raw(cls, value: str) -> BatteryStatus:
        fields = decode_varint_message(decode_raw(value))
        contact = fields.get(2, 0)
        if contact not in (0, 1):
            raise MalformedPayload(f"charger contact {contact}")
        return cls(charge_state=fields.get(1, 0), charger_connected=bool(contact))


def derive_activity(
    mission: MissionStatus | None,
    charger_connected: bool | None,
) -> Activity | None:
    """Derive the activity from the latest mission status and charger contact.

    The E15 reports DP 107 and DP 108 only as pushed LAN reports, never in a status
    reply, so either may be unknown right after start-up. ``None`` means the local
    data does not establish an activity; nothing is guessed from silence.

    Without a mission the mower is either at the station or standing on the lawn
    after a stop; only the charger contact tells them apart.
    """
    if mission is not None:
        if mission.error:
            return Activity.ERROR
        if mission.is_mowing_mission:
            if mission.state == STATE_PAUSED:
                return Activity.PAUSED
            if mission.state in (STATE_RUNNING, STATE_IDLE):
                return Activity.MOWING
            # A completed or aborted task is followed by the drive home; until the
            # mower reports that, the previous activity stands.
            return Activity.DOCKED if charger_connected else None
        # DP 108 reports the charger contact a few seconds before DP 107 leaves the
        # recharge mission, so contact during the drive home is the dock arrival.
        if mission.is_recharge_mission and mission.state != STATE_PAUSED:
            return Activity.DOCKED if charger_connected else Activity.RETURNING
    if charger_connected is None:
        return None
    return Activity.DOCKED if charger_connected else Activity.IDLE
