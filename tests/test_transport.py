"""The session thread against a fake tinytuya device."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from custom_components.eufy_e15.transport import MowerConnection, MowerConnectionError, probe


class FakeDevice:
    def __init__(self, reports: list) -> None:
        self.reports = reports
        self.written: list[dict] = []
        self.closed = False
        self.updated: list | None = None

    def status(self):
        return {"dps": {"1": False, "8": 90}}

    def set_socketTimeout(self, _timeout):
        pass

    def set_socketRetryLimit(self, _limit):
        pass

    def updatedps(self, index, nowait=False):
        self.updated = index

    def heartbeat(self, nowait=True):
        pass

    def receive(self):
        if self.reports:
            return self.reports.pop(0)
        threading.Event().wait(0.01)
        return None

    def set_multiple_values(self, dps, nowait=False):
        self.written.append(dps)

    def close(self):
        self.closed = True


def test_probe_raises_on_error() -> None:
    device = MagicMock()
    device.status.return_value = {"Error": "Network Error: Unable to Connect", "Err": "901"}
    with (
        patch("custom_components.eufy_e15.transport._new_device", return_value=device),
        pytest.raises(MowerConnectionError),
    ):
        probe("192.0.2.10", "id", "0123456789abcdef")
    device.close.assert_called_once()


async def test_session_dispatches_and_writes() -> None:
    loop = asyncio.get_running_loop()
    received: list[tuple[dict, bool]] = []
    connected = asyncio.Event()
    got_report = asyncio.Event()
    device = FakeDevice([None, {"dps": {"107": "CAIYAQ=="}}])

    def on_dps(dps: dict, from_status: bool) -> None:
        received.append((dps, from_status))
        if not from_status:
            loop.call_soon_threadsafe(got_report.set)

    def on_connected(value: bool) -> None:
        if value:
            loop.call_soon_threadsafe(connected.set)

    connection = MowerConnection("192.0.2.10", "id", "0123456789abcdef", on_dps, on_connected)
    with patch("custom_components.eufy_e15.transport._new_device", return_value=device):
        connection.start()
        await asyncio.wait_for(connected.wait(), 2)
        await asyncio.wait_for(got_report.wait(), 2)
        await asyncio.wait_for(connection.async_write({"1": True}), 2)
        await loop.run_in_executor(None, connection.stop)

    assert received[0] == ({"1": False, "8": 90}, True)
    assert ({"107": "CAIYAQ=="}, False) in received
    assert device.written == [{"1": True}]
    assert device.updated == [107, 108]
    assert device.closed


async def test_write_refused_when_disconnected() -> None:
    connection = MowerConnection("192.0.2.10", "id", "k", MagicMock(), MagicMock())
    with pytest.raises(MowerConnectionError):
        await connection.async_write({"1": True})
