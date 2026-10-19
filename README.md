# Eufy E15 Local

Local-only Home Assistant integration for the **Eufy E15** robot mower (T2880).
It talks to the mower over your LAN with the Tuya 3.5 protocol. No Eufy account is
stored and nothing goes to the cloud at runtime.

## What you get

| Entity | Source |
| --- | --- |
| `lawn_mower`: start, pause/resume, send home | DP 1, DP 2 |
| Activity: mowing, paused, returning, docked, idle, error | DP 107 mission status + DP 108 charger contact (pushed reports) |
| Battery, Wi-Fi signal (%), network | DP 8, 109, 134 |
| Task and phase (whole lawn, zone, box, edge… / positioning, defogging, saving map…) | DP 107 |
| On charging station, problem | DP 108, DP 107 |
| Mowing height (25–75 mm), volume | DP 110, 26 |
| Smart no-go suggestions, mow yellow grass | DP 132, 141 |
| Return when raining, child lock (read-only) | DP 101, 47 |
| Blade and base-station usage | DP 126, 125 |
| Last mowing session, with the last 20 sessions as attributes | derived locally, stored in `.storage` |

Not available locally, and therefore not in this integration: the map, and the
cloud-only work parameters (travel speed, blade speed, edge distance, path distance,
pad direction). Set those in the Eufy app.

## Setup

1. Give the mower a fixed IP address in your router.
2. Get the device ID and local key once with `tools/get-local-key.sh`. It asks for
   your Eufy email and password, prints the key and stores nothing. This is the only
   step that uses your Eufy account. The key changes if you re-pair the mower.
3. Install through HACS (custom repository, category *Integration*), restart, and add
   **Eufy E15 Local** with IP, device ID and local key.

The E15 accepts a single local session. Do not run another local integration, or
`tools/watch_dps.py`, at the same time.

### Options

**Allow control** (default on). Off makes the integration observe-only: every write
is refused.

## How it works

One thread keeps a persistent session open: a heartbeat every 10 s, a status query
every 60 s, and every pushed report as it arrives (`iot_class: local_push`). The E15
never includes DP 107/108 in a status reply, only in pushed reports, so on connect the
integration asks the mower to re-report them, and it persists the last values across
restarts.

Commands use only writes that were validated on hardware:

- **start**: DP 1 = true (from paused: DP 2 = false)
- **pause**: DP 2 = true, only while mowing
- **dock**: DP 1 = false. The E15 ends the task and drives home. There is no
  stop-in-place over the LAN, and DP 3 (`switch_charge`) is ignored by the mower.

Commands are refused while the mower saves its map (DP 118 between 0 and 100).

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component tinytuya==1.20.0 ruff
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

CI runs hassfest, HACS validation, ruff and the tests.
