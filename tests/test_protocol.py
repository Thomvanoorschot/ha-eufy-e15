"""Decoding and activity rules, with synthetic payloads."""

from __future__ import annotations

import base64

import pytest

from custom_components.eufy_e15.protocol import (
    Activity,
    BatteryStatus,
    MalformedPayload,
    MissionStatus,
    decode_varint_message,
    derive_activity,
)


def b64(*data: int) -> str:
    return base64.b64encode(bytes(data)).decode()


MOWING = MissionStatus.from_raw(b64(0x08, 0x02, 0x18, 0x01))
PAUSED = MissionStatus.from_raw(b64(0x08, 0x02, 0x18, 0x02))
RETURNING = MissionStatus.from_raw(b64(0x08, 0x01, 0x18, 0x01))
SAVING_MAP = MissionStatus.from_raw(b64(0x10, 0x05, 0x18, 0x01))
DEFAULT = MissionStatus.from_raw(b64(0x00))


def test_varint_message() -> None:
    assert decode_varint_message(bytes([0x08, 0x02, 0x10, 0x09, 0x18, 0x01])) == {1: 2, 2: 9, 3: 1}
    assert decode_varint_message(bytes([0x08, 0x96, 0x01])) == {1: 150}
    assert decode_varint_message(b"") == {}
    assert decode_varint_message(b"\x00") == {}


@pytest.mark.parametrize(
    "data",
    [
        bytes([0x0A, 0x01, 0x00]),  # length-delimited field
        bytes([0x08]),  # truncated
        bytes([0x08, 0x01, 0x08, 0x02]),  # repeated field
        bytes([0x08, *([0xFF] * 10), 0x01]),  # varint too long
    ],
)
def test_varint_message_rejects(data: bytes) -> None:
    with pytest.raises(MalformedPayload):
        decode_varint_message(data)


def test_not_base64() -> None:
    with pytest.raises(MalformedPayload):
        MissionStatus.from_raw("not base64!")


def test_mission_status_fields() -> None:
    status = MissionStatus.from_raw(b64(0x08, 0x11, 0x10, 0x03, 0x18, 0x01, 0x20, 0x02))
    assert status.mission_name == "box"
    assert status.sub_mission_name == "leaving_station"
    assert status.power_mode == 2
    assert SAVING_MAP.is_saving_map
    assert MissionStatus() == DEFAULT
    assert MissionStatus(mission=99).mission_name == "other"


def test_battery_status() -> None:
    assert BatteryStatus.from_raw(b64(0x08, 0x02, 0x10, 0x01, 0x18, 0x01)) == BatteryStatus(
        charge_state=2, charger_connected=True
    )
    assert not BatteryStatus.from_raw(b64(0x18, 0x01)).charger_connected
    with pytest.raises(MalformedPayload):
        BatteryStatus.from_raw(b64(0x10, 0x02))


@pytest.mark.parametrize(
    ("mission", "charger", "expected"),
    [
        (MOWING, None, Activity.MOWING),
        (MOWING, True, Activity.MOWING),  # defogging in the station
        (PAUSED, False, Activity.PAUSED),
        (RETURNING, False, Activity.RETURNING),
        (RETURNING, True, Activity.DOCKED),
        (SAVING_MAP, True, Activity.DOCKED),
        (SAVING_MAP, False, None),
        (MissionStatus(saving_data=True), False, None),
        (MissionStatus(saving_data=True), True, Activity.DOCKED),
        (DEFAULT, True, Activity.DOCKED),
        (DEFAULT, False, Activity.IDLE),
        (DEFAULT, None, None),
        (None, None, None),
        (None, True, Activity.DOCKED),
        (MissionStatus(mission=2, state=1, error=True), False, Activity.ERROR),
        (MissionStatus(mission=2, state=4), True, Activity.DOCKED),
        (MissionStatus(mission=2, state=4), False, None),
    ],
)
def test_derive_activity(
    mission: MissionStatus | None, charger: bool | None, expected: Activity | None
) -> None:
    assert derive_activity(mission, charger) is expected
