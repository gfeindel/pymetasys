"""Raw TCP connection to the serial-to-IP bridge.

The bridge only accepts one TCP client at a time, so this module owns the one
socket for the life of the process. Everything that reads or writes serial goes
through :class:`Bridge`, serialized by an internal lock.

Reads go to a single fan-out: bytes pulled off the socket land in the
:class:`~metasys.driver.screen.Screen` that the driver hands us, and any number
of subscribers (manual-terminal passthrough, trace logger) can tap the same
stream without interfering with each other.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Callable

log = logging.getLogger(__name__)


class BridgeNotConnected(RuntimeError):
    pass


ByteSink = Callable[[bytes], None]


class Bridge:
    """Owns the single TCP socket to the serial-to-IP bridge.

    The reader task pulls bytes off the socket and fans them out to all
    registered sinks. The write path is guarded by an asyncio.Lock so that
    two callers cannot interleave keystroke bytes.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        reconnect_min: float = 1.0,
        reconnect_max: float = 30.0,
    ) -> None:
        self._host = host
        self._port = port
        self._reconnect_min = reconnect_min
        self._reconnect_max = reconnect_max

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._connected_event = asyncio.Event()

        self._sinks: set[ByteSink] = set()
        self._stop = False

    # ---- lifecycle -----------------------------------------------------

    async def start(self, *, wait_connected: bool = False, connect_timeout: float = 5.0) -> None:
        """Begin the background reader/reconnect loop.

        By default returns immediately — the loop handles initial connect and
        reconnect in the background so the app can come up even when the
        bridge is unreachable. Pass ``wait_connected=True`` to block up to
        ``connect_timeout`` waiting for the first successful connect.
        """
        self._stop = False
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._run(), name="bridge-reader")
        if wait_connected:
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=connect_timeout)
            except asyncio.TimeoutError:
                log.warning("bridge: first-connect timed out — background reconnect continues")

    async def stop(self) -> None:
        self._stop = True
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001 — best-effort close
                pass
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    @property
    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    async def wait_connected(self) -> None:
        await self._connected_event.wait()

    # ---- fan-out subscriptions ----------------------------------------

    def subscribe(self, sink: ByteSink) -> Callable[[], None]:
        """Register a sink for every byte read from the bridge.

        Returns an unsubscribe callable. Sinks are called synchronously from
        the reader task — keep them cheap and non-blocking.
        """
        self._sinks.add(sink)

        def _unsub() -> None:
            self._sinks.discard(sink)

        return _unsub

    @asynccontextmanager
    async def subscription(self, sink: ByteSink) -> AsyncIterator[None]:
        unsub = self.subscribe(sink)
        try:
            yield
        finally:
            unsub()

    # ---- writes --------------------------------------------------------

    async def send(self, data: bytes) -> None:
        if self._writer is None or not self.is_connected:
            raise BridgeNotConnected("bridge socket is not currently open")
        async with self._write_lock:
            self._writer.write(data)
            await self._writer.drain()

    # ---- internal reader loop -----------------------------------------

    async def _run(self) -> None:
        backoff = self._reconnect_min
        while not self._stop:
            try:
                log.info("bridge: connecting to %s:%s", self._host, self._port)
                self._reader, self._writer = await asyncio.open_connection(
                    self._host, self._port
                )
                backoff = self._reconnect_min
                self._connected_event.set()
                log.info("bridge: connected")
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — reconnect on anything
                log.warning("bridge: connection error: %s", e)
            finally:
                self._connected_event.clear()
                if self._writer is not None:
                    try:
                        self._writer.close()
                    except Exception:  # noqa: BLE001
                        pass
                self._writer = None
                self._reader = None

            if self._stop:
                break

            log.info("bridge: reconnecting in %.1fs", backoff)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2, self._reconnect_max)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while not self._stop:
            chunk = await self._reader.read(4096)
            if not chunk:
                log.info("bridge: socket closed by peer")
                return
            # Fan-out. Copy the set so sinks that unsubscribe mid-iteration
            # don't break us.
            for sink in list(self._sinks):
                try:
                    sink(chunk)
                except Exception:  # noqa: BLE001
                    log.exception("bridge: sink raised — removing")
                    self._sinks.discard(sink)
