# CF Terminal Web App

Small FastAPI app that queues terminal operations to a single RS-485 serial worker and provides a web UI for groups/points.

## Requirements

- Ubuntu 24.04
- Python 3.11+
- RS-485 serial adapter

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

## Serial configuration

Edit `.env`:

- `SERIAL_PORT=/dev/ttyUSB0`
- `SERIAL_BAUD=9600`
- `SERIAL_TIMEOUT=1.0`
- `SERIAL_WRITE_TIMEOUT=1.0`
- `SERIAL_BYTESIZE=8`
- `SERIAL_PARITY=N`
- `SERIAL_STOPBITS=1`
- `TERMINAL_LOGIN_HINT=Password`
- `TERMINAL_LOGIN_PASSWORD=1234`

## Troubleshooting

- Check job status: `GET /jobs/{id}`
- Raw screen capture is stored in job `result_json.raw_screen`.
- Logs: stdout and rotating file from `LOG_FILE`.

## Notes

- Only the worker touches the serial port.
- Requests enqueue jobs in SQLite; the worker processes them sequentially.
