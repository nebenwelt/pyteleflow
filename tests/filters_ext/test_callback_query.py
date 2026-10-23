import re

import pytest
from telegram import Update

from pyteleflow import filters_ext

from tests import data as td


def _update_with_cb(data: str | None = None) -> Update:
  return td.update(0, _callback_query=td.callback_query("cb_id", data=data))


def test_no_callback_query():
  update = td.update(
    0,
    td.message(text="hello"),
    _callback_query=None,
  )
  assert filters_ext.CallbackQuery().check_update(update) is False
  assert filters_ext.CallbackQuery(data_pattern="open").check_update(update) is False


@pytest.mark.parametrize("data", ["any_data", None])
def test_without_pattern(data):
  f = filters_ext.CallbackQuery()
  assert f.check_update(_update_with_cb(data)) is True


@pytest.mark.parametrize(
  "pattern, data, expected",
  [
    ("open", "open", True),  # exact full match
    ("open", "close", False),  # no match
    ("open", None, False),  # missing data -> no match
    ("open", "opened", False),  # fullmatch, not a prefix
    ("open", "op", False),  # fullmatch, not a substring
    ("^open$", "open", True),  # anchors
    ("o.*n", "open", True),  # arbitrary regex
    ("open1|open2", "open2", True),  # alternation
  ],
)
def test_with_pattern(pattern, data, expected):
  f = filters_ext.CallbackQuery(pattern)
  assert f.check_update(_update_with_cb(data)) is expected


def test_with_precompiled_pattern():
  f = filters_ext.CallbackQuery(re.compile("open"))
  assert f.check_update(_update_with_cb("open")) is True
  assert f.check_update(_update_with_cb("close")) is False
