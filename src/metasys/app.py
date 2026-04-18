"""FastAPI application factory + routes."""

from __future__ import annotations

import asyncio
import binascii
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import (
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    SESSION_COOKIE,
    clear_session,
    hash_password,
    issue_session,
    require_admin,
    require_any,
    verify_password,
)
from .config import get_settings
from .db import AuditEvent, User, get_session, init_db
from .driver.bridge import Bridge
from .driver.driver import CommandRequest, Driver
from .driver.screen import Screen
from .manual import ManualSessionManager
from .poller import GroupPoller
from .queue import PRIO_COMMAND, PRIO_READ, OpQueue

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_ROOT / "templates"))


# ---- app state container ------------------------------------------------


class AppState:
    def __init__(self) -> None:
        self.bridge: Bridge | None = None
        self.screen: Screen | None = None
        self.driver: Driver | None = None
        self.queue: OpQueue | None = None
        self.poller: GroupPoller | None = None
        self.manual: ManualSessionManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await init_db()
    await _seed_admin_if_empty()

    st = AppState()
    st.screen = Screen()
    st.bridge = Bridge(
        settings.bridge_host,
        settings.bridge_port,
        reconnect_min=settings.reconnect_min,
        reconnect_max=settings.reconnect_max,
    )
    st.driver = Driver(st.bridge, st.screen, settings)
    st.queue = OpQueue(st.driver)
    st.poller = GroupPoller(st.queue, interval=settings.poll_interval)
    st.manual = ManualSessionManager(st.driver, st.queue)
    app.state.app = st

    # Start the bridge first; if it can't connect, the driver will still come up
    # and operations will fail loudly until the bridge comes back.
    try:
        await st.bridge.start()
        await st.driver.start()
    except Exception:  # noqa: BLE001
        log.exception("startup: bridge/driver failed to come up — serving HTTP anyway")

    st.queue.start()
    try:
        yield
    finally:
        if st.poller is not None:
            await st.poller.stop()
        if st.queue is not None:
            await st.queue.stop()
        if st.driver is not None:
            await st.driver.stop()
        if st.bridge is not None:
            await st.bridge.stop()


app = FastAPI(title="Metasys CF Terminal", lifespan=lifespan)

if (_ROOT / "static").exists():
    app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")


@app.exception_handler(HTTPException)
async def _redirect_unauthenticated(request: Request, exc: HTTPException) -> Response:
    # Redirect browser GETs on protected HTML pages to /login; keep 401 for API clients.
    if (
        exc.status_code == status.HTTP_401_UNAUTHORIZED
        and request.method == "GET"
        and not request.url.path.startswith("/api/")
        and not request.url.path.startswith("/ws/")
    ):
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ---- helpers ------------------------------------------------------------


def _app_state(request: Request) -> AppState:
    return request.app.state.app  # type: ignore[no-any-return]


async def _seed_admin_if_empty() -> None:
    """Create a default admin user if the users table is empty.

    Credentials logged once at startup; rotate immediately.
    """
    import secrets

    async for session in get_session():
        count = await session.scalar(select(User).limit(1))
        if count is not None:
            return
        pw = secrets.token_urlsafe(16)
        admin = User(
            username="admin",
            password_hash=hash_password(pw),
            role="admin",
        )
        session.add(admin)
        await session.commit()
        log.warning(
            "*** Created default admin user. Username: admin  Password: %s  (rotate ASAP) ***",
            pw,
        )


async def _audit(
    session: AsyncSession,
    user: User | None,
    *,
    kind: str,
    point_number: int | None = None,
    command_type: str | None = None,
    command_value: str | None = None,
    before_value: str | None = None,
    after_value: str | None = None,
    success: bool = True,
    message: str | None = None,
    raw_bytes: bytes | None = None,
) -> None:
    session.add(
        AuditEvent(
            user_id=user.id if user else None,
            username=user.username if user else "",
            kind=kind,
            point_number=point_number,
            command_type=command_type,
            command_value=command_value,
            before_value=before_value,
            after_value=after_value,
            success=success,
            message=message,
            raw_bytes_hex=binascii.hexlify(raw_bytes).decode() if raw_bytes else None,
        )
    )
    await session.commit()


# ---- auth routes --------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or user.disabled or not verify_password(password, user.password_hash):
        return _TEMPLATES.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )
    response = RedirectResponse(url="/", status_code=303)
    issue_session(response, user)
    await _audit(session, user, kind="login")
    return response


@app.post("/logout")
async def logout(response: Response) -> Response:
    clear_session(response)
    return RedirectResponse(url="/login", status_code=303)


# ---- pages --------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request, "index.html", {"user": user}
    )


@app.get("/groups/{n}", response_class=HTMLResponse)
async def group_page(
    request: Request,
    n: int,
    user: Annotated[User, Depends(require_any)],
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request, "group.html", {"user": user, "group_number": n}
    )


@app.get("/terminal", response_class=HTMLResponse)
async def terminal_page(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request, "terminal.html", {"user": user}
    )


# ---- REST API -----------------------------------------------------------


@app.get("/api/groups")
async def api_list_groups(
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> JSONResponse:
    st = _app_state(request)
    assert st.queue is not None
    groups = await st.queue.submit(
        lambda d: d.read_group_list(),
        priority=PRIO_READ,
        name="read_group_list",
        user=user.username,
    )
    return JSONResponse([asdict(g) for g in groups])


@app.get("/api/groups/{n}")
async def api_get_group(
    n: int,
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> JSONResponse:
    st = _app_state(request)
    assert st.queue is not None
    summary = await st.queue.submit(
        lambda d: d.read_group_summary(n),
        priority=PRIO_READ,
        name=f"read_group_{n}",
        user=user.username,
    )
    return JSONResponse(_summary_to_json(summary))


@app.get("/api/points/{n}/command-options")
async def api_command_options(
    n: int,
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> JSONResponse:
    st = _app_state(request)
    assert st.queue is not None
    opts = await st.queue.submit(
        lambda d: d.probe_command_options(n),
        priority=PRIO_READ,
        name=f"probe_point_{n}",
        user=user.username,
    )
    return JSONResponse(asdict(opts))


@app.post("/api/points/{n}/command")
async def api_command_point(
    n: int,
    request: Request,
    user: Annotated[User, Depends(require_any)],
    session: Annotated[AsyncSession, Depends(get_session)],
    command_type: Annotated[str, Form()],
    value: Annotated[str, Form()] = "",
    confirm_before: Annotated[str, Form()] = "",
) -> JSONResponse:
    """Issue a command to a point. Confirm-before-send is caller-enforced:
    the UI modal shows the current value + proposed change, collects a
    ``confirm_before`` echo of what the user agreed to, and we reject if the
    freshly-read value now differs from it.
    """
    st = _app_state(request)
    assert st.queue is not None
    req = CommandRequest(point_number=n, command_type=command_type, value=value)

    # Re-read before proceeding — protect against stale-data writes (plan §2).
    pre = None
    if confirm_before:
        pre_summary = await st.queue.submit(
            lambda d: d.read_point_summary(n),
            priority=PRIO_READ,
            name=f"preread_{n}",
            user=user.username,
        )
        for p in pre_summary.points:
            if p.number == n:
                pre = p.value
                break
        if pre is not None and pre.strip() != confirm_before.strip():
            await _audit(
                session,
                user,
                kind="command_rejected_stale",
                point_number=n,
                command_type=command_type,
                command_value=value,
                before_value=pre,
                success=False,
                message=f"current value '{pre}' != confirmed '{confirm_before}'",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "stale_value",
                    "current": pre,
                    "confirmed": confirm_before,
                },
            )

    result = await st.queue.submit(
        lambda d: d.command_point(req),
        priority=PRIO_COMMAND,
        name=f"command_point_{n}",
        user=user.username,
        timeout=30.0,
    )

    await _audit(
        session,
        user,
        kind="command",
        point_number=n,
        command_type=command_type,
        command_value=value,
        before_value=result.before,
        after_value=result.after,
        success=result.success,
        message=result.message,
    )
    return JSONResponse(asdict(result))


@app.post("/api/alarm/ack")
async def api_ack_alarm(
    request: Request,
    user: Annotated[User, Depends(require_any)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    st = _app_state(request)
    assert st.driver is not None
    alarm = st.driver.alarms.blocked_alarm
    await st.driver.alarms.human_ack()
    await _audit(
        session,
        user,
        kind="ack",
        success=True,
        message=alarm.text if alarm else "no alarm displayed",
    )
    return JSONResponse({"acked": True})


@app.get("/api/status/fragment", response_class=HTMLResponse)
async def api_status_fragment(
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> HTMLResponse:
    """Small HTML fragment rendered into the top status bar by HTMX."""
    st = _app_state(request)
    assert st.driver is not None and st.queue is not None
    bits = [
        f"bridge: {'connected' if (st.bridge and st.bridge.is_connected) else 'DOWN'}",
        f"state: {st.driver.state.name}",
        f"queue: {st.queue.depth} depth{' (paused)' if st.queue.is_paused else ''}",
    ]
    if st.driver.alarms.is_blocked and st.driver.alarms.blocked_alarm:
        a = st.driver.alarms.blocked_alarm
        bits.append(
            f'<span class="error">ALARM [{a.priority.value}]: {a.text} '
            f'<button hx-post="/api/alarm/ack" hx-swap="none">Ack</button></span>'
        )
    return HTMLResponse(" · ".join(bits))


@app.get("/api/status")
async def api_status(
    request: Request,
    user: Annotated[User, Depends(require_any)],
) -> JSONResponse:
    st = _app_state(request)
    assert st.driver is not None and st.queue is not None and st.manual is not None
    return JSONResponse(
        {
            "bridge_connected": st.bridge.is_connected if st.bridge else False,
            "driver_state": st.driver.state.name,
            "manual_mode": st.driver.manual_mode,
            "queue_depth": st.queue.depth,
            "queue_paused": st.queue.is_paused,
            "alarm_blocked": st.driver.alarms.is_blocked,
            "blocked_alarm": (
                {
                    "text": st.driver.alarms.blocked_alarm.text,
                    "priority": st.driver.alarms.blocked_alarm.priority.value,
                }
                if st.driver.alarms.blocked_alarm
                else None
            ),
            "manual_session": (
                {
                    "owner": st.manual.current.owner,
                    "remaining": st.manual.current.remaining(),
                }
                if st.manual.current
                else None
            ),
        }
    )


# ---- WebSockets ---------------------------------------------------------


@app.websocket("/ws/groups/{n}")
async def ws_group(websocket: WebSocket, n: int) -> None:
    """Live Group Summary feed. Authenticated via session cookie."""
    await websocket.accept()

    cookie = websocket.cookies.get(SESSION_COOKIE)
    if not cookie:
        await websocket.close(code=4401, reason="not authenticated")
        return
    try:
        from .auth import _serializer  # lazy

        _serializer().loads(cookie)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="invalid session")
        return

    st: AppState = websocket.app.state.app
    assert st.poller is not None
    try:
        async for summary in st.poller.subscribe(n):
            await websocket.send_json(_summary_to_json(summary))
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        log.exception("ws_group error")


@app.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket) -> None:
    """xterm.js passthrough. Admin only, exclusive, audit-logged."""
    await websocket.accept()

    cookie = websocket.cookies.get(SESSION_COOKIE)
    if not cookie:
        await websocket.close(code=4401, reason="not authenticated")
        return
    try:
        from .auth import _serializer

        data = _serializer().loads(cookie)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="invalid session")
        return
    if data.get("role") != "admin":
        await websocket.close(code=4403, reason="admin only")
        return

    st: AppState = websocket.app.state.app
    assert st.manual is not None and st.bridge is not None

    try:
        sess = await st.manual.acquire(data["username"])
    except RuntimeError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=4423, reason="manual session busy")
        return

    # Forwarder task: bridge→ws.
    async def bridge_to_ws() -> None:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1024)
        unsub = st.bridge.subscribe(lambda data: _offer_bytes(q, data))  # type: ignore[union-attr]
        try:
            while True:
                chunk = await q.get()
                await websocket.send_bytes(chunk)
        finally:
            unsub()

    forward_task = asyncio.create_task(bridge_to_ws())

    # Deadline watcher.
    async def deadline_watcher() -> None:
        warned = False
        while st.manual.current is sess:
            rem = sess.remaining()
            if rem <= 0:
                await websocket.send_json({"type": "timeout"})
                await websocket.close(code=4408, reason="session timed out")
                return
            if not warned and rem <= (sess.deadline - sess.warn_at):
                await websocket.send_json({"type": "warn", "remaining": rem})
                warned = True
            await asyncio.sleep(1.0)

    watcher_task = asyncio.create_task(deadline_watcher())

    async for message in _iter_messages(websocket):
        if isinstance(message, bytes):
            await st.driver.manual_send(message)  # type: ignore[union-attr]
            # Audit as a separate task to not block the forward loop.
            async for session in get_session():
                u = await session.scalar(select(User).where(User.username == data["username"]))
                await _audit(session, u, kind="manual_send", raw_bytes=message)
                break
        elif isinstance(message, dict) and message.get("type") == "extend":
            try:
                await st.manual.extend(data["username"], int(message.get("seconds", 120)))
            except Exception as e:  # noqa: BLE001
                await websocket.send_json({"type": "error", "message": str(e)})

    forward_task.cancel()
    watcher_task.cancel()
    await st.manual.release(data["username"])


# ---- helpers ------------------------------------------------------------


def _offer_bytes(q: asyncio.Queue[bytes], data: bytes) -> None:
    try:
        q.put_nowait(data)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


async def _iter_messages(websocket: WebSocket):
    """Yield both bytes frames and JSON control frames from a websocket."""
    while True:
        try:
            msg = await websocket.receive()
        except WebSocketDisconnect:
            return
        if msg["type"] == "websocket.disconnect":
            return
        if "bytes" in msg and msg["bytes"] is not None:
            yield msg["bytes"]
        elif "text" in msg and msg["text"] is not None:
            try:
                import json

                yield json.loads(msg["text"])
            except Exception:  # noqa: BLE001
                # Treat as raw bytes if caller sent text for keystrokes.
                yield msg["text"].encode()


def _summary_to_json(s) -> dict:
    return {
        "group_number": s.number,
        "group_name": s.name,
        "points": [
            {
                "number": p.number,
                "name": p.name,
                "value": p.value,
                "unacknowledged": p.unacknowledged,
                "status": p.status,
                "flags": list(p.flags),
                "abnormal": p.is_abnormal,
                "offline": p.is_offline,
                "overridden": p.is_overridden,
            }
            for p in s.points
        ],
        "message": s.message,
    }


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "metasys.app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
