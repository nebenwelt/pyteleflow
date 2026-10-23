import logging
import re
from re import Pattern

from telegram import Update
from telegram.ext.filters import BaseFilter

logger = logging.getLogger(__name__)


class CallbackQuery(BaseFilter):
  def __init__(self, data_pattern: str | Pattern | None = None):
    """Filter for updates containing a callback query.

    Args:
      data_pattern: A regular expression, provided as a string or a compiled
        `re.Pattern`, that the `callback_query.data` value must fully
        match. If `None`, the filter accepts any callback query update,
        regardless of its data.
    """
    super().__init__(
      name=f"pyteleflow.filters_ext.{self.__class__.__name__}(data_pattern={data_pattern})"
    )
    self.data_pattern: Pattern[str] | None = (
      re.compile(data_pattern) if data_pattern is not None else None
    )

  def check_update(self, update: Update) -> bool:
    if update.callback_query is None:
      return False

    if self.data_pattern is None:
      return True

    if update.callback_query.data is None:
      return False

    return re.fullmatch(self.data_pattern, update.callback_query.data) is not None


class AnyUpdate(BaseFilter):
  def __init__(self):
    super().__init__(name=f"pyteleflow.filters_ext.{self.__class__.__name__}")

  def check_update(self, update: Update) -> bool:
    return True


class UpdateType:
  CALLBACK_QUERY = CallbackQuery()
  ALL = AnyUpdate()
