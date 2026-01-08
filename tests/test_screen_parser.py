from app.terminal.driver import ScreenBuffer, parse_group_summary


def test_screen_buffer_basic():
    buf = ScreenBuffer(rows=3, cols=10)
    buf.feed(b"Hello")
    buf.feed(b"\r\nWorld")
    assert "Hello" in buf.text()
    assert "World" in buf.text()


def test_parse_group_summary_lines():
    sample = """
    For Group Number: 2
    Point  Name            Value
      1    Temp Supply      72.4
      2    Fan Status       ON
      3    Mode             AUTO
    """
    points = [p for p in parse_group_summary(sample) if p.point_number is not None]
    assert len(points) == 3
    assert points[0].point_number == 1
    assert points[0].name == "Temp Supply"
    assert points[0].value == "72.4"
