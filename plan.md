# Metasys CF Terminal Web Front-End — Implementation Plan

A Python web application that lets a facilities team view and modify points on a Johnson Controls Metasys Panel Unit by screen-scraping its VT100 serial console, exposed over the network via a serial-to-IP bridge.

---

## 1. What we're actually controlling

The Panel Unit exposes a **CF Terminal** interface — a text-mode VT100 screen with four regions: time/date line, alarm report area, main area, and message line. Operators navigate a fixed menu tree from the Main Menu using single-letter shortcuts and arrow keys, and enter data into bracketed fields like `[ ]`. Function keys F1 (Cancel), F2 (Save), F3 (More — paginate), and F4 (Acknowledge) are the only out-of-band controls. ESC backs out one level.

Two screens carry almost all the operational value:

- **Group Summary** (`G → S → <group#> → Enter`) — the *only* screen with auto-refreshing point values (10-second tick). It's also the *only* screen from which a point can be commanded.
- **Point Override/Command** (`P → O → <point#> → Enter → <command type> → <value> → Enter`) — the standard write path. The set of valid command types depends on point type: BO supports Override/Auto/Command/Release; AI/BI support Override/Auto; AO supports Override/Auto/Adjust. AC points cannot be commanded at all.

Beyond that there are Point Summary, Trend Log Summary, Scheduling Summary, Totalization Summary, Energy Profile, plus database-generation screens (Add/Modify Point, Group, Schedule, etc.). The Add/Modify screens are where the user's "highly variable layout" warning bites — every point type (AC/AI/AO/BI/BO) has its own field set on its own line layout, and many features (Demand Limiting, Trending, Totalization, Control Logic) layer additional fields onto the same Point Modify screen depending on what's enabled.

The Panel Unit itself enforces a four-tier capability model on whichever password is currently logged in: Monitor, Command, Operate, System. This is the *device's* auth, not the web app's, and it ultimately gates everything we can do over the wire.

---

## 2. Why this is harder than it looks

Five things make this a non-trivial integration, and the design has to take all of them seriously up front:

**Single-connection serial bridge.** The serial-to-IP bridge accepts exactly one TCP client at a time. Every read, every write, every screen scrape goes through that one socket. The web app must own the socket exclusively and serialize all operations behind it. There is no concurrency at the device layer — only at the queue layer in front of it.

**Stateful, modal navigation.** The terminal has no addressable endpoints. To read Group 7, you have to *be* on the Group Summary screen with group number 7 entered. To get there, you walk the menu tree. If something else (an alarm pop-up, another in-flight command) leaves the terminal on a different screen, the next operation has to first navigate back to a known state. The driver's job is to model "where am I now" and compute the keystroke sequence to get from there to where it needs to be.

**Async alarm interruptions.** Critical and Network alarms appear in the alarm report area whenever they happen, regardless of what screen the operator is on. They contaminate the screen buffer and must be acknowledged with F4 before lower-priority alarms can display. The driver has to detect alarm-region content separately from main-area content, decide whether to auto-acknowledge or surface to a human, and not confuse alarm text with the data it was trying to scrape.

**Highly variable screen layouts.** Group Summary and Point Summary have predictable structure and can be parsed with a small number of patterns. The Add/Modify screens for points, schedules, and control logic do not — field positions shift based on point type, on which features are enabled for that point, on whether help is on or off, on whether an error message is currently flashing. Trying to support every variant up front is the wrong move; supporting view + command for the common cases and falling back to an interactive web terminal for everything else is the right one.

**Stale data is dangerous.** Group Summary refreshes every 10 seconds. Anything we cache and display in a web UI is at least that stale, and likely staler once you account for queue latency. Modifying a point based on a stale read is how you turn off a chiller someone else just turned on. Every command path needs a re-read confirmation step before the write actually goes out.

---

## 3. Architecture

Five layers, each with a single responsibility. The split matters because each layer fails differently and needs its own retry, logging, and test strategy.

```
┌─────────────────────────────────────────────────────────────┐
│  Browser: React or HTMX UI + xterm.js for manual terminal   │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTPS + WebSocket
┌──────────────────▼──────────────────────────────────────────┐
│  FastAPI app: auth, RBAC, REST + WS endpoints, audit log    │
└──────────────────┬──────────────────────────────────────────┘
                   │ async function calls
┌──────────────────▼──────────────────────────────────────────┐
│  Operation queue (asyncio.Queue) — single consumer           │
└──────────────────┬──────────────────────────────────────────┘
                   │ pop one op at a time
┌──────────────────▼──────────────────────────────────────────┐
│  Terminal driver: navigation FSM, screen parser, alarm      │
│  watcher, manual-mode passthrough                            │
└──────────────────┬──────────────────────────────────────────┘
                   │ raw bytes
┌──────────────────▼──────────────────────────────────────────┐
│  TCP client to serial-to-IP bridge (single socket, owned)    │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1 — Bridge connection

A single long-lived asyncio TCP connection to the serial bridge. Reconnect with exponential backoff on drop. Wrap in an asyncio.Lock so nothing else can touch the socket. Maintain a rolling raw-bytes buffer that the screen parser consumes.

A small VT100/ANSI parser is needed — `pyte` is the right pick. It's a pure-Python terminal emulator that maintains a virtual screen (24×80 grid of characters with attributes) you can query by row/column. You feed it bytes, it updates the grid. This is dramatically more reliable than regex-on-raw-bytes because it correctly handles cursor positioning, screen clears, scroll regions, and attribute changes that the real Panel Unit emits.

### Layer 2 — Terminal driver

This is where most of the engineering goes. Conceptually a state machine whose states are the screens the Panel Unit can be on (Main Menu, Group Menu, Group Summary, Point Menu, Point Summary, Point Command, Manual Mode passthrough, Unknown). Each state knows:

- A **screen recognizer** — given the current pyte screen, am I on this screen? Usually a couple of fixed strings at known coordinates, e.g., "Group Summary" near the top, the "F1 Cancel ... F3 More" line at the bottom.
- An **outbound transition table** — what keystrokes take me from here to each adjacent state. From Main Menu, `G` → Group Menu. From Group Menu, `S` → "Group Number [ ]" prompt. Etc.
- A **parser** — given the screen, extract structured data (list of points with values, list of defined groups, current command field options, error message in the message line).

A `navigate_to(target_state, **params)` method plans a path from the current state to the target and executes it keystroke by keystroke, waiting for the screen to settle (no new bytes for ~150ms, with a hard timeout) between sends. If the screen isn't what was expected after a transition, the driver bails to "Unknown" state and recovers by sending ESC repeatedly until it sees the Main Menu.

A separate **alarm watcher** task continuously inspects the alarm report area of the screen buffer. When an alarm appears, it logs the alarm, optionally posts to Teams or PagerDuty, and either auto-acknowledges (configurable per priority) or marks the system "alarm-blocked" until a human acks via the UI. No other operation can run while alarm-blocked.

### Layer 3 — Operation queue

A single `asyncio.Queue` of operation objects. One consumer task. Operations carry: op type, params, requesting user, priority, timeout, and a future to resolve with the result. The consumer pulls the next op, asks the driver to execute it, resolves the future, repeats. Priority lanes handle command (highest), read (medium), background poll (lowest). The driver itself is single-threaded by virtue of being the only consumer.

### Layer 4 — Web app (FastAPI)

REST endpoints for the structured operations (`GET /api/groups`, `GET /api/groups/{n}`, `POST /api/points/{n}/command`, etc.). Each handler enqueues an op and awaits its future. A WebSocket endpoint streams live group-summary updates by pulling from a per-group pub/sub fed by a low-priority background poll task. A second WebSocket endpoint is the manual-terminal passthrough — when a user opens manual mode, the driver enters a special "passthrough" state where the queue is paused, raw bytes flow bidirectionally between the user's xterm.js and the bridge, and a heartbeat keeps the session alive. Only one user can hold manual mode at a time; the UI shows who has it.

### Layer 5 — Browser

For the structured UI, plain HTMX or a small React app — nothing exotic needed. For the manual terminal, **xterm.js** rendering output and capturing keystrokes, talking to the FastAPI WebSocket. Show the user clearly when a command is queued vs. executing vs. complete, and always show the most recent screen scrape with its timestamp so they know how stale it is.

---

## 4. Authentication and roles

Two separate auth layers — don't conflate them.

**Web app auth (your roles).** Standard session-based auth with `admin` and `user` (facilities) roles. Use `fastapi-users` or roll your own with `passlib` + signed cookies. Since this is for a church and likely <20 users, SQLite for the user table is fine; if you want SSO via Microsoft/Google, `Authlib` makes that straightforward.

| Capability | Admin | Facilities |
|------------|:-----:|:----------:|
| View groups & points | ✓ | ✓ |
| Command points (where supported in UI) | ✓ | ✓ |
| Open manual web terminal | ✓ | — |
| Acknowledge alarms | ✓ | ✓ |
| View audit log | ✓ | — |
| Manage users | ✓ | — |
| Configure connection settings | ✓ | — |

The principle: facilities can do the day-to-day operational work, but anything that drops them into raw terminal mode (where they could accidentally delete a point or change a password) is admin-only.

**Panel Unit auth (the device's roles).** The web app logs into the Panel Unit on startup using a single stored System-capability password held in config (encrypted at rest). The Panel Unit doesn't know about your individual web users — from its perspective, every action is the same "service account" operator. This is fine and standard for this kind of integration, but it means **the audit log in the web app is the only record of who did what.** That log is non-negotiable: every command op records user, timestamp, point number, command type, command value, before-value, after-value, and any error.

---

## 5. The "fall back to manual terminal" escape hatch

The user requirement that pre-empts the entire Modify-Point complexity problem. The plan: build structured UI for the things that are stable and high-value (Group Summary view, Point Summary view, point commanding via the standard P→O→... flow, Trend Log view, alarm acknowledgment), and for everything else — Schedule editing, Add Point, Modify Point, Control Logic, etc. — let the user click "Open Terminal" and get an xterm.js window that's directly bridged to the device.

In manual mode, the queue is paused (no background polls, no other users' commands queued behind), the user gets exclusive ownership for up to 10 minutes (with a warning at 8 and an extend button), and every keystroke sent and every screen returned is logged for the audit trail. When the user closes the session or times out, the driver sends `ESC ESC ESC` until it's back at Main Menu, then resumes the queue.

This is the safety valve that makes the rest of the project tractable. You don't have to build a parser for every point-modify variant — you just have to build it for the read paths and the command path, and let humans handle the rest manually with a better-than-PuTTY UI.

---

## 6. Recommended tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Web framework | **FastAPI** | Native async, perfect for the queue + WS pattern, good typing |
| ASGI server | **uvicorn** behind **nginx** | Standard, handles WS cleanly |
| Terminal emulation | **pyte** | Pure-Python VT100, virtual screen as a queryable grid |
| Bridge I/O | **asyncio** stdlib | No extra dep needed for raw TCP |
| DB | **SQLite** + **SQLAlchemy** | Plenty for users + audit log; one file, easy backup |
| Auth | **fastapi-users** or **Authlib** for SSO | Don't roll your own |
| Frontend | **HTMX** + **Alpine.js**, or **React** | HTMX is lighter and fits FastAPI well; React if the team prefers it |
| Terminal UI | **xterm.js** | Industry standard browser terminal |
| Process supervision | **systemd** | One service file, restarts on failure |
| Deployment | **Docker** on a small Linux VM | Keep it simple; this isn't a fleet |

---

## 7. Build order

Phased delivery so you have something working end-to-end early and can validate the hard parts (driver reliability, alarm handling) before committing to UI polish.

**Phase 0 — Spike (1–2 days).** Get a Python script that opens the TCP socket, feeds bytes through pyte, sends `\r` to wake the screen, logs in, navigates to Group Summary 1, and prints the parsed list of points to stdout. No web app yet. The goal is to confirm the bridge works as expected, the login sequence is what the manual implies, and pyte handles the device's actual escape sequences. **If this phase reveals that the device emits non-standard sequences pyte can't handle, the entire plan needs revisiting** — so do it first.

**Phase 1 — Driver core (1 week).** Build the navigation FSM, screen recognizers, and parsers for Main Menu, Group Menu, Group Summary, Point Menu, Point Summary. Build the operation queue. Build the alarm watcher. Test extensively against the real device using a CLI harness. This is the high-risk, high-value work — invest in it.

**Phase 2 — Read-only web UI (3–4 days).** FastAPI app with auth, list of groups, group summary view (live updating via WS + 10s background poll), point summary view, alarm display + ack. No commanding yet. Get facilities looking at it and giving feedback.

**Phase 3 — Commanding (3–4 days).** Add the P→O→... flow for the four commandable point types. Confirm-before-send modal showing current value and proposed change. Audit logging. Gate behind role check. Test exhaustively, including the failure modes (point doesn't exist, command rejected, alarm interrupts mid-command, bridge drops mid-command).

**Phase 4 — Manual terminal (3–4 days).** xterm.js + WS passthrough, exclusive lock, timeout, audit-log every keystroke. Admin-only. This unlocks the long tail of "I just need to edit a schedule" use cases without you having to build UI for each.

**Phase 5 — Polish (ongoing).** Trend log views, totalization views, energy profile dashboard, search across points by name, export to CSV, Teams/PagerDuty alarm integration, etc. Pick what facilities actually asks for.

Total realistic timeline for a single dev: **3–4 weeks to a usable Phase 4 release**, then iterate.

---

## 8. Things to nail down before building

A short list of things the implementer will need to know or verify; worth getting answers up front so they don't become blockers mid-build.

1. **The actual login prompt sequence.** The manual describes the password capability model but the exact "Press any key to log on" → "Password: ____" interaction needs to be confirmed against the live device, including character echo behavior and the post-login landing screen.
2. **How the bridge advertises connection state.** Does it close the TCP connection cleanly when the serial cable is unplugged, or does it just stop responding? Affects the reconnect logic.
3. **Whether the device echoes characters or the bridge does.** Affects how the driver knows a keystroke was received.
4. **Idle behavior of the Panel Unit.** Does it auto-log-out after inactivity? If yes, the driver needs to handle re-login transparently.
5. **The exact set of point types in your church's installation.** If you only have AI, BI, BO, and AO (no AC), that simplifies the commanding UI. A one-time scrape of the All Points summary will tell you.
6. **Alarm volume.** If the system rarely alarms, auto-ack-and-log is fine. If it alarms constantly, you need the alarm UI from day one or the driver will be perpetually blocked.
7. **Whether facilities wants mobile access.** Affects UI framework choice and whether the manual terminal needs to work on a phone (xterm.js does, but it's a poor experience).

---

## 9. Risks worth flagging

Three things that could derail this and what to do about each:

- **VT100 dialect mismatch.** The Panel Unit was built in the late 1990s and "VT100-compatible" was loose terminology back then. If pyte chokes on what the device emits, fall back to `pyte`'s lower-level `Stream` with a custom listener that handles the device's quirks, or in the worst case do hand-rolled parsing of the screen-clear/cursor-position sequences. Mitigated by Phase 0 spike.
- **The "screen settled" heuristic is unreliable.** Waiting 150ms for no new bytes is a guess. If the device sometimes pauses mid-render, the parser will see a partial screen. Mitigation: parse only after seeing a known anchor string at a known coordinate (e.g., the F-key footer line) — that's a positive confirmation the screen is fully drawn. Skip time-based heuristics.
- **Alarm storms.** If a real incident produces dozens of alarms in seconds, the auto-ack loop could either miss alarms or spam the audit log. Mitigation: rate-limit auto-ack to 1/second, batch identical alarms in the log, and surface a "system in alarm storm" banner in the UI.

---

## 10. Out of scope for v1

Worth being explicit about so scope doesn't creep:

- Writing or modifying schedules, control logic, or point definitions through the structured UI (use manual terminal mode).
- Multi-site or multi-Panel-Unit support (one bridge, one device).
- Historical trend graphing beyond what the device's Trend Log Summary already shows (that's a separate Trend-archive problem).
- Mobile-native apps (responsive web only).
- Direct N2 Bus integration bypassing the terminal (would require very different hardware and is a different project).

---

## 11. One-paragraph summary for the implementer

Build a FastAPI application whose core is a single-consumer asyncio queue feeding a stateful terminal driver that owns the only TCP connection to the serial-to-IP bridge. Use pyte to maintain a virtual VT100 screen, build a navigation FSM whose states correspond to Panel Unit screens, write recognizers and parsers for Group Summary and Point Summary first, then wire up the standard P→O→<point>→<command>→<value> commanding flow with a confirm-before-send modal and full audit logging. Layer web-app auth (admin/user) on top, separate from the device's own password. Provide an xterm.js-based manual terminal mode for everything that doesn't fit the structured UI, with exclusive locking and per-keystroke audit logging. Phase 0 must validate that pyte handles the device's actual VT100 dialect before committing to the rest of the architecture.