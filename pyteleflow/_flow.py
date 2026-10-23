import time
from asyncio import Queue, Task
from datetime import timedelta
from re import Pattern

from telegram import Bot, CallbackQuery, Message, Update
from telegram.ext import filters
from telegram.ext.filters import BaseFilter, MessageFilter

from . import filters_ext
from ._types import FlowKey


class Context:
  def __init__(
    self,
    bot: Bot,
    initial_update: Update,
    inactivity_timeout: float,
    shared_data: dict,
  ):
    self._updates: Queue[Update] = Queue()
    self.bot = bot
    self._shared_data = shared_data
    self._last_activity_at: float = time.monotonic()

    self._inactivity_timeout: float = float(inactivity_timeout)

    self._initial_update: Update = initial_update
    self._last_update: Update = initial_update

  @property
  def inactivity_timeout(self) -> float:
    return self._inactivity_timeout

  @inactivity_timeout.setter
  def inactivity_timeout(self, timeout: timedelta | float):
    if isinstance(timeout, timedelta):
      self._inactivity_timeout = float(timeout.total_seconds())
    else:
      self._inactivity_timeout = float(timeout)

  @property
  def initial_update(self) -> Update:
    """The initial Update that triggered the Flow"""
    return self._initial_update

  @property
  def shared_data(self) -> dict:
    return self._shared_data

  async def _get_update(self, _filter: BaseFilter | None = None) -> Update:
    while True:
      update = await self._updates.get()
      if _filter is None or _filter.check_update(update):
        self._last_update = update
        return update

  async def update(self, _filter: BaseFilter | None = None) -> Update:
    """Waits for and returns the next Update from Flow context queue.

    Args:
      _filter: Optional filter to match the Update against. If provided,
        Updates that do not match the filter are ignored. The Update will wait until
        a matching Update appears in the queue.
    """
    return await self._get_update(_filter)

  async def message(self, _filter: MessageFilter | None = None) -> Message:
    while True:
      if _filter:
        update = await self._get_update(filters.UpdateType.MESSAGE & _filter)
      else:
        update = await self._get_update(filters.UpdateType.MESSAGE)

      if update.message is not None:
        return update.message

  async def callback_query(self, data_pattern: str | Pattern | None = None) -> CallbackQuery:
    while True:
      update = await self._get_update(filters_ext.CallbackQuery(data_pattern))
      if update.callback_query is not None:
        return update.callback_query

  async def put_update(self, update: Update):
    """Adds an Update to the Flow context queue."""
    self._last_activity_at = time.monotonic()
    await self._updates.put(update)

  @property
  def last_activity_at(self) -> float:
    return self._last_activity_at

  @property
  def last_update(self) -> Update:
    """Returns the last Update retrieved from the Flow context queue."""
    return self._last_update

class Flow:
  def __init__(self, task: Task, context: Context, key: FlowKey):
    self.task = task
    self.context = context
    self.key = key

