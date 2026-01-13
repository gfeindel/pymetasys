import re
import socket
import time
import pyte
from dataclasses import dataclass
from typing import List, Optional

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
        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.Stream(self.screen)

    def clear(self):
        self.screen.reset()

    def feed(self, data: bytes):
        text = data.decode("ascii", errors="ignore")
        self.stream.feed(text)

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.screen.display)

class TerminalDriver:
    def __init__(self):
        self.sock = None
        self.screen = ScreenBuffer()

    def connect(self):
        if self.sock:
            return
        self.sock = socket.create_connection(
            (settings.device_server_host, settings.device_server_port),
            timeout=settings.device_server_timeout,
        )
        self.sock.settimeout(settings.device_server_timeout)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send(self, text: str):
        if not self.sock:
            raise RuntimeError("Socket not open")
        payload = text.encode("ascii")
        self.sock.settimeout(settings.device_server_write_timeout)
        try:
            self.sock.sendall(payload)
        finally:
            self.sock.settimeout(settings.device_server_timeout)

    def _read_for(self, seconds: float = 1.0) -> str:
        start = time.time()
        last_data = time.time()
        while time.time() - start < seconds:
            if not self.sock:
                break
            try:
                data = self.sock.recv(1024)
            except socket.timeout:
                data = b""
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
