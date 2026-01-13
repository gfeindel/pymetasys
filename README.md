# Overview

Pymetasys is a small FastAPI app that provides a web interface to the Johnson Controls Metasys building control system. It translates user actions on the web to the equivalent sequence of characters for the terminal operations. Operations are queued and run over a single TCP-connected terminal worker. The app supports basic group and point operations.

## Requirements

- Ubuntu 24.04
- Python 3.11+
- Serial device server reachable over TCP

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Initialize the database and start the server:

```bash
uvicorn app.main:app --reload
```

Start the worker in a separate terminal:

```bash
python -m app.jobs.worker
```

Default admin credentials come from `.env` (`DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`).

## Device server configuration

Edit `.env`:

- `DEVICE_SERVER_HOST=127.0.0.1`
- `DEVICE_SERVER_PORT=4001`
- `DEVICE_SERVER_TIMEOUT=1.0`
- `DEVICE_SERVER_WRITE_TIMEOUT=1.0`
- `TERMINAL_LOGIN_HINT=Password`
- `TERMINAL_LOGIN_PASSWORD=1234`

## Troubleshooting

- Check job status: `GET /jobs/{id}`
- Raw screen capture is stored in job `result_json.raw_screen`.
- Logs: stdout and rotating file from `LOG_FILE`.

## Notes

- Only the worker touches the device server connection.
- Requests enqueue jobs in SQLite; the worker processes them sequentially.
