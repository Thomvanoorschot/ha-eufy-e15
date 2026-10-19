#!/usr/bin/env python3
"""Watch everything the mower reports over the LAN, decoded. For verification.

The E15 accepts one local session: disable the integration in Home Assistant first.

    .venv/bin/python tools/watch_dps.py <ip> <device_id> <local_key>

Start, pause and send the mower home from the Eufy app while this runs, and compare
the decoded mission and charger contact with what the app shows. Output contains no
secrets, but do not publish raw logs.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "eufy_e15"))

import tinytuya
from protocol import BatteryStatus, MalformedPayload, MissionStatus


def describe(dp: str, value: object) -> str:
    try:
        if dp == "107":
            m = MissionStatus.from_raw(value)
            return (
                f"mission={m.mission_name}({m.mission}) phase={m.sub_mission_name}"
                f"({m.sub_mission}) state={m.state} power={m.power_mode}"
                f" error={m.error} saving={m.saving_data}"
            )
        if dp == "108":
            b = BatteryStatus.from_raw(value)
            return f"charger_connected={b.charger_connected} charge_state={b.charge_state}"
    except MalformedPayload as err:
        return f"malformed: {err}"
    return ""


def show(kind: str, response: object) -> None:
    if not isinstance(response, dict):
        return
    if "Error" in response:
        print(f"{datetime.now():%H:%M:%S.%f} {kind} ERROR {response}")
        return
    for dp, value in sorted(response.get("dps", {}).items(), key=lambda kv: int(kv[0])):
        print(
            f"{datetime.now():%H:%M:%S.%f} {kind:6} dp {dp:>3} = {value!r:30} {describe(dp, value)}"
        )


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    host, device_id, local_key = sys.argv[1:]
    device = tinytuya.Device(device_id, host, local_key, version=3.5, persist=True)
    show("status", device.status())
    device.set_socketTimeout(1)
    device.updatedps([107, 108], nowait=True)
    last_heartbeat = time.monotonic()
    try:
        while True:
            if time.monotonic() - last_heartbeat > 10:
                device.heartbeat(nowait=True)
                last_heartbeat = time.monotonic()
            show("report", device.receive())
    except KeyboardInterrupt:
        pass
    finally:
        device.close()


if __name__ == "__main__":
    main()
