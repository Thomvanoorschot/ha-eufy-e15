"""Constants for the Eufy E15 Local integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "eufy_e15"
MANUFACTURER: Final = "Eufy"
MODEL: Final = "E15 (T2880)"

CONF_DEVICE_ID: Final = "device_id"
CONF_LOCAL_KEY: Final = "local_key"
CONF_ALLOW_CONTROL: Final = "allow_control"
DEFAULT_ALLOW_CONTROL: Final = True

# Transport. The E15 speaks Tuya LAN protocol 3.5 on TCP 6668 and accepts a single
# local session, so this integration keeps exactly one persistent connection open.
TUYA_VERSION: Final = 3.5
TUYA_PORT: Final = 6668
CONNECT_TIMEOUT: Final = 5.0
RECEIVE_TIMEOUT: Final = 1.0
# The reference Tuya LAN stack drops a session after 30 s without incoming traffic.
HEARTBEAT_INTERVAL: Final = 10.0
STATUS_INTERVAL: Final = 60.0
RECONNECT_MIN: Final = 5.0
RECONNECT_MAX: Final = 300.0
# How long a lost connection may last before entities report unavailable.
UNAVAILABLE_AFTER: Final = timedelta(seconds=90)

# Data points. Codes are the mower's own declarations (product schema of the T2880).
DP_SWITCH_GO: Final = "1"  # bool, rw: true starts a task, false ends it and drives home
DP_PAUSE: Final = "2"  # bool, rw: true pauses, false resumes
DP_BATTERY: Final = "8"  # int 0-100 %
DP_VOLUME: Final = "26"  # int 0-100 %
DP_CHILD_LOCK: Final = "47"  # bool
DP_RAIN_AUTO_RETURN: Final = "101"  # bool
DP_ROBOT_STATUS: Final = "107"  # raw, mission status (pushed reports only)
DP_BATTERY_STATUS: Final = "108"  # raw, charger contact (pushed reports only)
DP_SIGNAL: Final = "109"  # int 0-100 %
DP_MOW_HEIGHT: Final = "110"  # int 25-75 mm
DP_SAVE_MAP_PROCESS: Final = "118"  # int 0-100 %, map-save progress (not mowing progress)
DP_BASE_STATION_USED: Final = "125"  # int, minutes
DP_BLADE_USED: Final = "126"  # int, minutes
DP_SMART_FORBID_ZONE: Final = "132"  # bool
DP_NET_MEDIA_TYPE: Final = "134"  # enum None/Wifi/Cellular
DP_SPARSE_LAWN: Final = "141"  # bool

MOW_HEIGHT_MIN: Final = 25
MOW_HEIGHT_MAX: Final = 75
MOW_HEIGHT_STEP: Final = 5

SESSION_HISTORY_LIMIT: Final = 50
STORAGE_VERSION: Final = 1
