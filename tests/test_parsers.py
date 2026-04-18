"""Tests for the screen parsers."""

from __future__ import annotations

from metasys.driver.parsers import (
    parse_group_list,
    parse_group_summary,
    parse_point_row,
)
from metasys.driver.screen import Screen
from tests.fixtures import GROUP_LIST_ROWS, GROUP_SUMMARY_ROWS, layout


def _feed(rows):
    s = Screen()
    s.feed(layout(rows))
    return s


def test_parse_point_row_simple_ai():
    rec = parse_point_row("  1 ACM BI7 AHU255  1500.0 KW")
    assert rec is not None
    assert rec.number == 1
    assert "ACM BI7 AHU255" in rec.name
    assert rec.value.startswith("1500.0")


def test_parse_point_row_with_abnormal_status():
    rec = parse_point_row("* 9 LCP-1 BI2       Off")
    assert rec is not None
    assert rec.number == 9
    assert rec.status == "*"
    assert rec.is_abnormal is True
    assert rec.value == "Off"


def test_parse_point_row_garbage_returns_none():
    assert parse_point_row("F1 Cancel                 F3 More") is None
    assert parse_point_row("") is None
    assert parse_point_row("-" * 80) is None


def test_parse_group_summary_header():
    gs = parse_group_summary(_feed(GROUP_SUMMARY_ROWS))
    assert gs is not None
    assert gs.number == 1
    assert "Bldg Overview" in gs.name


def test_parse_group_summary_finds_points():
    gs = parse_group_summary(_feed(GROUP_SUMMARY_ROWS))
    assert gs is not None
    numbers = {p.number for p in gs.points}
    # Spot-check a handful — the fixture lists 14 points across two columns.
    for n in (1, 3, 5, 7, 9):
        assert n in numbers
    abnormal = [p for p in gs.points if p.status == "*"]
    assert any(p.number == 9 for p in abnormal)


def test_parse_group_list_extracts_defined_groups():
    groups = parse_group_list(_feed(GROUP_LIST_ROWS))
    nums = {g.number for g in groups}
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
        assert n in nums
    # Sanity: names aren't digit-only.
    assert any(g.name == "Bldg Overview" for g in groups)
