"""State of one mower, fed by the local session, plus its mowing-session history."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    DOMAIN,
    DP_BATTERY,
    DP_BATTERY_STATUS,
    DP_ROBOT_STATUS,
    SESSION_HISTORY_LIMIT,
    STORAGE_VERSION,
    UNAVAILABLE_AFTER,
)
from .protocol import (
    STATE_ABORTED,
    STATE_COMPLETE,
    Activity,
    BatteryStatus,
    MalformedPayload,
    MissionStatus,
    derive_activity,
)
from .transport import MowerConnection

_LOGGER = logging.getLogger(__name__)

type E15ConfigEntry = ConfigEntry[E15Coordinator]


@dataclass(slots=True)
class MowSession:
    """One mowing task, from the first mowing report to the dock or a stop."""

    started: str
    mission: str
    battery_start: int | None
    ended: str | None = None
    result: str | None = None
    mowing_seconds: float = 0.0
    pauses: int = 0
    battery_end: int | None = None
    error: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MowerState:
    """Everything the mower told us, merged across status replies and reports."""

    dps: dict[str, Any] = field(default_factory=dict)
    mission: MissionStatus | None = None
    battery_status: BatteryStatus | None = None
    charger_connected: bool | None = None
    activity: Activity | None = None
    last_report: datetime | None = None


class E15Coordinator(DataUpdateCoordinator[MowerState]):
    """Push-based coordinator: the session thread delivers, nothing is polled here."""

    config_entry: E15ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: E15ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.connection = MowerConnection(
            entry.data["host"],
            self.device_id,
            entry.data[CONF_LOCAL_KEY],
            on_dps=self._threadsafe(self._handle_dps),
            on_connected=self._threadsafe(self._handle_connected),
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.sessions: list[MowSession] = []
        self.current_session: MowSession | None = None
        self._mowing_since: datetime | None = None
        self._unavailable_timer: CALLBACK_TYPE | None = None
        self._pending_result: str | None = None
        self._robot_status_raw: str | None = None
        self.data = MowerState()

    def _threadsafe(self, func: Any) -> Any:
        def call(*args: Any) -> None:
            self.hass.loop.call_soon_threadsafe(func, *args)

        return call

    async def async_start(self) -> None:
        await self._async_restore()
        self.connection.start()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unavailable_timer:
            self._unavailable_timer()
        await self.hass.async_add_executor_job(self.connection.stop)
        await self._async_save()

    async def _async_update_data(self) -> MowerState:
        return self.data

    @property
    def available(self) -> bool:
        return self.last_update_success and bool(self.data.dps)

    # -- incoming data -------------------------------------------------------------

    @callback
    def _handle_connected(self, connected: bool) -> None:
        if connected:
            if self._unavailable_timer:
                self._unavailable_timer()
                self._unavailable_timer = None
            self.last_update_success = True
            self.async_update_listeners()
        elif self._unavailable_timer is None:
            self._unavailable_timer = async_call_later(
                self.hass, UNAVAILABLE_AFTER, self._mark_unavailable
            )

    @callback
    def _mark_unavailable(self, _now: datetime) -> None:
        self._unavailable_timer = None
        if not self.connection.connected:
            _LOGGER.warning("Lost the local connection to the mower")
            self.last_update_success = False
            self.async_update_listeners()

    @callback
    def _handle_dps(self, dps: dict[str, Any], from_status: bool) -> None:
        state = self.data
        state.dps.update(dps)
        if not from_status:
            state.last_report = dt_util.utcnow()
        if DP_ROBOT_STATUS in dps:
            try:
                state.mission = MissionStatus.from_raw(dps[DP_ROBOT_STATUS])
            except MalformedPayload as err:
                _LOGGER.debug("Ignoring DP 107 %r: %s", dps[DP_ROBOT_STATUS], err)
            else:
                self._robot_status_raw = dps[DP_ROBOT_STATUS]
                # A mission means the mower left, or is about to leave, the station;
                # the next DP 108 report tells us when it is back on the contacts.
                if state.mission.is_mowing_mission or state.mission.is_recharge_mission:
                    state.charger_connected = False
                if state.mission.state in (STATE_COMPLETE, STATE_ABORTED):
                    self._pending_result = (
                        "completed" if state.mission.state == STATE_COMPLETE else "aborted"
                    )
        if DP_BATTERY_STATUS in dps:
            try:
                state.battery_status = BatteryStatus.from_raw(dps[DP_BATTERY_STATUS])
            except MalformedPayload as err:
                _LOGGER.debug("Ignoring DP 108 %r: %s", dps[DP_BATTERY_STATUS], err)
            else:
                state.charger_connected = state.battery_status.charger_connected

        previous = state.activity
        activity = derive_activity(state.mission, state.charger_connected)
        if activity is not None:
            state.activity = activity
        if state.activity != previous:
            self._track_session(previous, state.activity)
            self.hass.async_create_task(self._async_save())
        self.last_update_success = True
        self.async_set_updated_data(state)

    # -- session history -----------------------------------------------------------

    def _track_session(self, previous: Activity | None, activity: Activity | None) -> None:
        now = dt_util.utcnow()
        session = self.current_session
        battery = self.data.dps.get(DP_BATTERY)

        if session is not None and previous is Activity.MOWING and self._mowing_since:
            session.mowing_seconds += (now - self._mowing_since).total_seconds()
            self._mowing_since = None

        if activity is Activity.MOWING:
            if session is None:
                mission = self.data.mission
                self.current_session = MowSession(
                    started=now.isoformat(),
                    mission=mission.mission_name if mission else "unknown",
                    battery_start=battery,
                )
                self._pending_result = None
            self._mowing_since = now
        elif activity is Activity.PAUSED and session is not None:
            session.pauses += 1
        elif activity is Activity.ERROR and session is not None:
            session.error = True
        elif activity in (Activity.DOCKED, Activity.IDLE) and session is not None:
            session.ended = now.isoformat()
            session.battery_end = battery
            session.result = self._pending_result or (
                "returned" if activity is Activity.DOCKED else "stopped"
            )
            if session.error:
                session.result = "error"
            self.sessions.insert(0, session)
            del self.sessions[SESSION_HISTORY_LIMIT:]
            self.current_session = None
            self._pending_result = None

    def note_requested_dock(self) -> None:
        """Remember that the current task ends because we sent it home."""
        if self.current_session is not None:
            self._pending_result = "sent_home"

    # -- persistence ---------------------------------------------------------------

    async def _async_restore(self) -> None:
        stored = await self._store.async_load() or {}
        self.sessions = [MowSession(**item) for item in stored.get("sessions", [])]
        if current := stored.get("current_session"):
            self.current_session = MowSession(**current)
        state = self.data
        state.charger_connected = stored.get("charger_connected")
        if raw := stored.get("robot_status"):
            try:
                state.mission = MissionStatus.from_raw(raw)
            except MalformedPayload:
                state.mission = None
            else:
                self._robot_status_raw = raw
        state.activity = derive_activity(state.mission, state.charger_connected)
        if state.activity is Activity.MOWING and self.current_session is not None:
            self._mowing_since = dt_util.utcnow()

    async def _async_save(self) -> None:
        state = self.data
        await self._store.async_save(
            {
                "sessions": [s.as_dict() for s in self.sessions],
                "current_session": self.current_session.as_dict() if self.current_session else None,
                "charger_connected": state.charger_connected,
                "robot_status": self._robot_status_raw,
            }
        )
