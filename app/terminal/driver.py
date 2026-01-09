import re
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    import serial
except ImportError:  # pragma: no cover - optional at test time
    serial = None

from ..config import settings

@dataclass
class ParsedPoint:
    point_number: Optional[int]
    name: str
    value: str
    raw_line: str

class ScreenBuffer:
    def __init__(self, rows: int = 24, cols: int = 80):
        self.rows = rows
        self.cols = cols
        self.clear()

    def clear(self):
        self.buffer = [" " * self.cols for _ in range(self.rows)]
        self.row = 0
        self.col = 0

    def feed(self, data: bytes):
        text = data.decode("ascii", errors="ignore")
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":
                if text[i:i+4] == "\x1b[2J":
                    self.clear()
                    i += 4
                    continue
                i += 1
                continue
            if ch == "\r":
                self.col = 0
            elif ch == "\n":
                self.row = min(self.rows - 1, self.row + 1)
                self.col = 0
            else:
                if self.col >= self.cols:
                    self.row = min(self.rows - 1, self.row + 1)
                    self.col = 0
                line = self.buffer[self.row]
                self.buffer[self.row] = line[:self.col] + ch + line[self.col + 1 :]
                self.col += 1
            i += 1

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.buffer)

class TerminalDriver:
    def __init__(self):
        self.serial = None
        self.screen = ScreenBuffer()

    def connect(self):
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        if self.serial and self.serial.is_open:
            return
        self.serial = serial.Serial(
            port=settings.serial_port,
            baudrate=settings.serial_baud,
            timeout=settings.serial_timeout,
            write_timeout=settings.serial_write_timeout,
            bytesize=settings.serial_bytesize,
            parity=settings.serial_parity,
            stopbits=settings.serial_stopbits,
        )

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()

    def send(self, text: str):
        if not self.serial:
            raise RuntimeError("Serial port not open")
        self.serial.write(text.encode("ascii"))

    def _read_for(self, seconds: float = 1.0) -> str:
        start = time.time()
        last_data = time.time()
        while time.time() - start < seconds:
            if not self.serial:
                break
            data = self.serial.read(1024)
            if data:
                self.screen.feed(data)
                last_data = time.time()
            else:
                if time.time() - last_data > 0.3:
                    break
        return self.screen.text()

    def go_to_main_menu(self) -> str:
        self.connect()
        for _ in range(5):
            self.send("\x1b")
            time.sleep(0.2)
            screen = self._read_for(1.0)
            if settings.terminal_login_hint in screen:
                screen = self._handle_login(screen)
            if settings.terminal_main_menu_hint in screen:
                return screen
        return self._read_for(1.0)

    def _handle_login(self, screen: str) -> str:
        if not settings.terminal_login_password:
            return screen
        self.send(settings.terminal_login_password)
        self.send("\r")
        return self._read_for(2.0)

    def open_group_summary(self, group_number: int) -> str:
        self.go_to_main_menu()
        self.send("G")
        self.send("S")
        self.send(str(group_number))
        self.send("\r")
        return self._read_for(2.0)

    def read_group_values(self, group_number: int) -> dict:
        screen = self.open_group_summary(group_number)
        parsed = parse_group_summary(screen)
        return {"group_number": group_number, "points": parsed, "raw_screen": screen}

    def command_point(self, group_number: int, point_number: int, command_type: str, command_value: str) -> dict:
        screen = self.open_group_summary(group_number)
        self.send(str(point_number))
        self.send("\r")
        self._read_for(1.0)
        self.send(command_type)
        self.send("\r")
        self._read_for(0.5)
        self.send(command_value)
        self.send("\r")
        screen = self._read_for(2.0)
        return {"raw_screen": screen}


def parse_group_summary(screen_text: str) -> List[ParsedPoint]:
    points = []
    for line in screen_text.splitlines():
        if not line.strip():
            continue
        match = re.match(r"\s*(\d+)\s+([A-Za-z0-9 \-_/]+?)\s{2,}(.+)$", line)
        if match:
            number = int(match.group(1))
            name = match.group(2).strip()
            value = match.group(3).strip()
            points.append(ParsedPoint(number, name, value, line))
        else:
            if "Point" in line and "Value" in line:
                continue
            points.append(ParsedPoint(None, "", "", line))
    return points
