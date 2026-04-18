"""Tests for the screen-state recognizers."""

from __future__ import annotations

from metasys.driver.screen import Screen
from metasys.driver.states import State, detect_state
from tests.fixtures import (
    CRITICAL_ALARM_ROWS,
    GROUP_LIST_ROWS,
    GROUP_MENU_ROWS,
    GROUP_SUMMARY_ROWS,
    LOGIN_ROWS,
    MAIN_MENU_ROWS,
    PASSWORD_ROWS,
    POINT_MENU_ROWS,
    layout,
)


def _feed(rows):
    s = Screen()
    s.feed(layout(rows))
    return s


def test_detect_main_menu():
    assert detect_state(_feed(MAIN_MENU_ROWS)) is State.MAIN_MENU


def test_detect_group_menu():
    assert detect_state(_feed(GROUP_MENU_ROWS)) is State.GROUP_MENU


def test_detect_group_list():
    assert detect_state(_feed(GROUP_LIST_ROWS)) is State.GROUP_LIST


def test_detect_group_summary():
    assert detect_state(_feed(GROUP_SUMMARY_ROWS)) is State.GROUP_SUMMARY


def test_detect_point_menu():
    assert detect_state(_feed(POINT_MENU_ROWS)) is State.POINT_MENU


def test_detect_login_press_any_key():
    assert detect_state(_feed(LOGIN_ROWS)) is State.LOGIN_PROMPT


def test_detect_login_password():
    assert detect_state(_feed(PASSWORD_ROWS)) is State.LOGIN_PROMPT


def test_critical_alarm_still_detects_group_summary():
    # With a critical alarm in the header area, state should still resolve
    # to the underlying screen — the alarm watcher handles the alarm
    # separately.
    assert detect_state(_feed(CRITICAL_ALARM_ROWS)) is State.GROUP_SUMMARY
