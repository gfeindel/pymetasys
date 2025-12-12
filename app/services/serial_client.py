import threading
import time
import serial
from serial import SerialException, SerialTimeoutException
from app.config import get_settings


class SerialClient:
    """
    Thin wrapper around pyserial to ensure single access to the port.
    """

    def __init__(self):
        self.settings = get_settings()
        self.lock = threading.Lock()
        self._serial = None

    def _connect(self):
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(
            port=self.settings.serial_port,
            baudrate=self.settings.serial_baudrate,
            timeout=self.settings.serial_timeout,
        )

    def _reset_connection(self) -> None:
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None

    def _execute_once(self, input_sequence: str, timeout: float) -> str:
        self._connect()
        ser = self._serial
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write(input_sequence.encode("ascii", errors="replace"))
        ser.flush()

        ser.timeout = timeout
        chunks: list[bytes] = []
        start = time.time()
        last_data_time = start
        quiet_gap = 0.25  # how long to wait with no data before considering the screen finished
        while True:
            data = ser.read(ser.in_waiting or 1)
            now = time.time()
            if data:
                chunks.append(data)
                last_data_time = now
            if (now - start) >= timeout:
                raise TimeoutError("Serial read timed out")
            if (now - last_data_time) >= quiet_gap and (now - start) > 0.05:
                break
        return b"".join(chunks).decode("ascii", errors="replace")

    def execute_sequence(self, input_sequence: str, timeout: float | None = None) -> str:
        """
        Execute the ASCII sequence against the serial device.
        Uses a lock to guarantee single access and retries once on serial failure.
        """
        with self.lock:
            timeout = timeout or self.settings.serial_timeout
            try:
                return self._execute_once(input_sequence, timeout)
            except SerialTimeoutException as exc:
                # Map pyserial timeout to TimeoutError for the worker to handle
                raise TimeoutError(str(exc))
            except (SerialException, OSError):
                # Reconnect once and retry to satisfy resilience requirement
                self._reset_connection()
                return self._execute_once(input_sequence, timeout)
