# Building Control Web App

FastAPI + React app that serializes ASCII-terminal commands to a legacy building controller. Jobs are queued and executed one-at-a-time through a locked serial client, with JWT-based auth (user/admin).

## Features
- Actions map to input sequences + regex parsing rules.
- In-process job queue with a single worker thread to guard the serial port.
- JWT auth, users/roles, CRUD for actions, job history, regex tester.
- React + Vite + MUI frontend with dashboards for users and admins.

## Configuration
Copy `.env.example` to `.env` and adjust:
- `DATABASE_URL` (defaults to SQLite file)
-, optional `REDIS_URL` (not required for the in-process queue)
- Serial: `SERIAL_PORT`, `SERIAL_BAUDRATE`, `SERIAL_TIMEOUT`
- Auth: `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- Admin bootstrap: `ADMIN_EMAIL`, `ADMIN_PASSWORD`

## Backend
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
- API lives at `http://localhost:8000`.
- On startup, the background worker thread starts automatically and processes queued jobs FIFO with a single serial lock.
- Create an admin via `POST /api/auth/bootstrap-admin` (requires `ADMIN_*` in env) or by inserting directly into the DB.

## Frontend
```bash
cd frontend
npm install
npm run dev -- --host --port 5173
```
Set `VITE_API_BASE_URL` to point at the backend (defaults to `http://localhost:8000`).

## Docker Compose (dev)
```bash
docker compose up
```
Starts the API (`uvicorn --reload`), Redis (optional), and Vite dev server on port 5173. The queue is in-process; Redis is present for future persistence.

## Running the worker
No extra process is needed—the worker thread runs inside the API service and enforces single access to the serial port. Jobs are created via `POST /api/actions/{id}/jobs` and polled with `GET /api/jobs`.

## Tests
```bash
pytest
```
Tests mock the serial client and cover auth, regex testing, and job execution.

## Serial notes
- Special keys can be encoded literally (e.g., `\n`, `<TAB>`, `<ESC>`); the sequence is sent as raw ASCII with replacement for unsupported bytes.
- The serial client retries once on connection errors and marks jobs as `timeout` if the device is silent beyond `SERIAL_TIMEOUT`.
