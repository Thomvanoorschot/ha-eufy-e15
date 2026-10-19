"""Persistent local Tuya 3.5 session with the mower.

tinytuya is synchronous, so the session lives in one dedicated thread that owns the
socket. Everything the mower pushes (command-8 reports) and every status reply is
handed to the event loop through ``on_dps``. Writes are queued into the same thread,
because the E15 accepts only one local session and the socket must not be shared.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import tinytuya

from .const import (
    CONNECT_TIMEOUT,
    DP_BATTERY_STATUS,
    DP_ROBOT_STATUS,
    HEARTBEAT_INTERVAL,
    RECEIVE_TIMEOUT,
    RECONNECT_MAX,
    RECONNECT_MIN,
    STATUS_INTERVAL,
    TUYA_PORT,
    TUYA_VERSION,
)

_LOGGER = logging.getLogger(__name__)

type DpsCallback = Callable[[dict[str, Any], bool], None]
type ConnectedCallback = Callable[[bool], None]


class MowerConnectionError(Exception):
    """The mower could not be reached or rejected the session."""


def _error_of(response: Any) -> str | None:
    if isinstance(response, dict) and "Error" in response:
        return f"{response.get('Error')} ({response.get('Err')})"
    return None


def probe(host: str, device_id: str, local_key: str) -> dict[str, Any]:
    """Open a short session and return one status reply. Blocking."""
    device = _new_device(host, device_id, local_key, persist=False)
    try:
        response = device.status()
    finally:
        device.close()
    if error := _error_of(response):
        raise MowerConnectionError(error)
    if not isinstance(response, dict) or "dps" not in response:
        raise MowerConnectionError(f"unexpected reply: {response!r}")
    return response["dps"]


def _new_device(host: str, device_id: str, local_key: str, *, persist: bool) -> tinytuya.Device:
    device = tinytuya.Device(
        device_id,
        address=host,
        local_key=local_key,
        version=TUYA_VERSION,
        port=TUYA_PORT,
        persist=persist,
        connection_timeout=CONNECT_TIMEOUT,
        connection_retry_limit=1,
    )
    device.set_socketRetryLimit(1)
    return device


class MowerConnection:
    """Owns the single local session for one mower."""

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        on_dps: DpsCallback,
        on_connected: ConnectedCallback,
    ) -> None:
        self._host = host
        self._device_id = device_id
        self._local_key = local_key
        self._on_dps = on_dps
        self._on_connected = on_connected
        self._writes: queue.Queue[tuple[dict[str, Any], concurrent.futures.Future[None]]] = (
            queue.Queue()
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"eufy_e15 {self._host}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=CONNECT_TIMEOUT + RECEIVE_TIMEOUT + 1)

    async def async_write(self, dps: dict[str, Any]) -> None:
        """Queue one control frame. Resolves once the frame was written to the socket.

        The mower confirms a write only through the reports that follow it, which
        reach the coordinator like any other report.
        """
        if not self.connected:
            raise MowerConnectionError("not connected to the mower")
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._writes.put((dps, future))
        await asyncio.wrap_future(future)

    def _run(self) -> None:
        backoff = RECONNECT_MIN
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._session()
            except Exception as err:
                _LOGGER.debug("Session with %s ended: %s", self._host, err)
            self._set_connected(False)
            self._fail_pending("connection lost")
            if self._stop.is_set():
                break
            if time.monotonic() - started > RECONNECT_MAX:
                backoff = RECONNECT_MIN
            _LOGGER.debug("Reconnecting to %s in %.0f s", self._host, backoff)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX)

    def _session(self) -> None:
        device = _new_device(self._host, self._device_id, self._local_key, persist=True)
        try:
            self._dispatch(device.status(), from_status=True)
            device.set_socketTimeout(RECEIVE_TIMEOUT)
            self._set_connected(True)
            # Ask the mower to re-report its raw status points, so activity and
            # charger contact are known without waiting for the next change.
            device.updatedps([int(DP_ROBOT_STATUS), int(DP_BATTERY_STATUS)], nowait=True)
            last_heartbeat = last_status = time.monotonic()
            while not self._stop.is_set():
                self._drain_writes(device)
                now = time.monotonic()
                if now - last_status >= STATUS_INTERVAL:
                    self._dispatch(device.status(), from_status=True)
                    last_status = last_heartbeat = now
                elif now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    device.heartbeat(nowait=True)
                    last_heartbeat = now
                self._dispatch(device.receive(), from_status=False)
        finally:
            device.close()

    def _drain_writes(self, device: tinytuya.Device) -> None:
        while True:
            try:
                dps, future = self._writes.get_nowait()
            except queue.Empty:
                return
            if future.cancelled():
                continue
            try:
                response = device.set_multiple_values(dps, nowait=True)
            except Exception as err:
                future.set_exception(MowerConnectionError(str(err)))
                raise
            if error := _error_of(response):
                future.set_exception(MowerConnectionError(error))
                raise MowerConnectionError(error)
            _LOGGER.debug("Wrote %s", dps)
            future.set_result(None)

    def _dispatch(self, response: Any, *, from_status: bool) -> None:
        if response is None:
            return
        if error := _error_of(response):
            raise MowerConnectionError(error)
        if isinstance(response, dict) and isinstance(response.get("dps"), dict):
            self._on_dps(response["dps"], from_status)

    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            self._on_connected(connected)

    def _fail_pending(self, reason: str) -> None:
        while True:
            try:
                _, future = self._writes.get_nowait()
            except queue.Empty:
                return
            if not future.done():
                future.set_exception(MowerConnectionError(reason))
