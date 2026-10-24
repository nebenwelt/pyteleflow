import asyncio as aio
import logging
import platform
import secrets
import signal
import time
from asyncio import Lock, Queue, Task
from collections import deque
from collections.abc import Callable, Coroutine, Sequence
from datetime import timedelta
from types import MappingProxyType
from typing import Any

import telegram.error
from telegram import Update
from telegram.constants import UpdateType
from telegram.ext import ExtBot, filters
from telegram.ext.filters import BaseFilter
from tenacity import Retrying, retry_if_exception_type, wait_exponential

from ._helpers import cancel_tasks
from ._flow import Context, Flow
from ._helpers import TaskStatus, get_task_status
from ._strategy import BaseConcurrencyStrategy, ConcurrencyStrategy
from ._types import FlowKey
from .errors import (
  FlowAlreadySpawned,
  FlowCancellationFailed,
  FlowKeyError,
  UnexpectedError,
  PyteleflowError,
)
from .middleware import AsyncMiddleware, Middleware

_logger = logging.getLogger(__name__)


type FlowCallback = Callable[[Context], Coroutine[Any, Any, None]]

DEFAULT_SPAWN_TRIGGER = filters.Text(["/start"])


class FlowApp:
  def __init__(
    self,
    bot: ExtBot,
    entry_coro: FlowCallback,
    concurrency_limit: int | None = None,
    spawn_trigger: BaseFilter = DEFAULT_SPAWN_TRIGGER,  # Default: "/start" command
    respawn_trigger: BaseFilter | None = DEFAULT_SPAWN_TRIGGER,
    concurrency_strategy: BaseConcurrencyStrategy = ConcurrencyStrategy.CHAT,
    flow_inactivity_timeout: timedelta | float = timedelta(minutes=5),
    flow_cancellation_timeout: timedelta | float = timedelta(seconds=3),
    shared_data: dict | None = None,
  ):
    """
    Args:
      bot: Bot instance (`ExtBot`) used to receive updates and send
        requests to Telegram.

      entry_coro: Coroutine launched when a new Flow is spawned. Receives the
        `Context` of that Flow and runs as a separate task.

      concurrency_limit:
        The maximum number of `Flow` instances that can run concurrently.
        If `None`, there is no limit. When the limit is reached, no new `Flow` is spawned,
        and the corresponding `Update` is silently dropped. A warning is logged in this case.

      spawn_trigger:
        A trigger is a standard `Filter` from `telegram.ext.filters` or a custom filter implementation.
        When an incoming `Update` matches the filter, a new `Flow` instance is spawned,
        and the `Update` that triggered the spawn is available in the context through
        the `ctx.initial_update` property.
        For example, if `spawn_trigger = filters.Text(["Hello"]) | filters.PHOTO`,
        a new `Flow` is spawned only when a user sends a message with the text `Hello` or sends a photo.

      respawn_trigger:
        The filter that determines whether an update belonging to an existing `Flow`
        cancels that `Flow` and restarts it with the new update.

      concurrency_strategy:
        The concurrency strategy defines how incoming updates are processed concurrently.
        For example, it determines whether a single `Flow` instance handles all incoming updates
        or whether a separate `Flow` instance is spawned for each chat or each user within a chat.
        Available strategies:
          `ConcurrencyStrategy.CHAT`
          `ConcurrencyStrategy.USER_IN_GLOBAL`
          `ConcurrencyStrategy.USER_IN_CHAT`
          `ConcurrencyStrategy.THREAD_IN_CHAT`
          `ConcurrencyStrategy.SINGLE_FLOW`
        For a description of each strategy, see the `ConcurrencyStrategy` class.

      flow_inactivity_timeout:
        The maximum period of inactivity allowed for a `Flow`. If this timeout expires,
        the `Flow` is canceled.

        A `Flow` is considered active whenever it receives a new `Update` through methods
        such as `ctx.update()`, `ctx.message()`, and others.

        The `flow_inactivity_timeout` parameter sets the default inactivity timeout for all `Flow` instances.
        You can override this value for an individual `Flow` instance from within the `Flow`
        using the context: `ctx.inactivity_timeout = timedelta(minutes=15)`.

        When a `Flow` is canceled, its associated `asyncio.Task` is also canceled,
        causing an `asyncio.CancelledError` exception to be raised inside the coroutine.

      flow_cancellation_timeout:
        The amount of time allowed to handle `asyncio.CancelledError` when a Flow is
        canceled due to inactivity or respawning.

        For example:

        async def your_flow(ctx: Context):
          try:
            msg = await ctx.message()
          except asyncio.CancelledError:
            # If sleep exceeds flow_cancellation_timeout, another
            # CancelledError will be raised in this block.
            await asyncio.sleep(999)

      shared_data:
        Shared data passed to all Flow instances. This data is accessible through the Flow context.
    """

    self._bot: ExtBot = bot
    self._entry_coro = entry_coro
    self._concurrency_strategy: BaseConcurrencyStrategy = concurrency_strategy
    self._concurrency_limit: int | None = concurrency_limit
    self._shared_data = shared_data or {}
    self._respawn_trigger = respawn_trigger
    self._last_update_id: int | None = None
    self._poll_interval: int = 0
    self._spawn_trigger: BaseFilter = spawn_trigger
    self._allowed_updates: tuple[UpdateType, ...] | None = None
    self._middlewares: list[Middleware | AsyncMiddleware] = []
    self._lock: Lock = Lock()
    self._is_running: bool = False
    self._bg_tasks: set[Task] = set()  # background tasks
    self._startup_coroutines: list[tuple[str | None, Coroutine]] = []

    self._flow_inactivity_timeout: float
    if isinstance(flow_inactivity_timeout, timedelta):
      self._flow_inactivity_timeout = float(flow_inactivity_timeout.total_seconds())
    else:
      self._flow_inactivity_timeout = float(flow_inactivity_timeout)

    self._flow_cancellation_timeout: float
    if isinstance(flow_cancellation_timeout, timedelta):
      self._flow_cancellation_timeout = float(flow_cancellation_timeout.total_seconds())
    else:
      self._flow_cancellation_timeout = float(flow_cancellation_timeout)

    self._spawned_flows: dict[FlowKey, Flow] = {}

  async def _get_updates(self) -> tuple[Update, ...]:
    # Skip updates on first launch
    if self._last_update_id is None:
      updates = await self._bot.get_updates(
        offset=-1, timeout=0, allowed_updates=self._allowed_updates
      )
      self._last_update_id = updates[-1].update_id + 1 if len(updates) > 0 else 0

    updates = await self._bot.get_updates(
      offset=self._last_update_id,
      timeout=self._poll_interval,
      allowed_updates=self._allowed_updates,
    )
    if len(updates) > 0:
      self._last_update_id = updates[-1].update_id + 1

    return updates

  def _spawn_new_flow(self, flow_key: FlowKey, initial_update: Update) -> None:
    if flow_key in self._spawned_flows:
      raise FlowAlreadySpawned("The flow with such an KEY has already been spawned")

    if self._concurrency_limit is not None and len(self._spawned_flows) >= self._concurrency_limit:
      _logger.warning("Concurrency limit reached. Unable to spawn a new flow.")
      return

    context = Context(
      bot=self._bot,
      initial_update=initial_update,
      inactivity_timeout=self._flow_inactivity_timeout,
      shared_data=self._shared_data,
      app=self,
    )

    task = aio.create_task(
      self._entry_coro(context),
      name=f"flow_{flow_key.chat_id}_{flow_key.user_id}_{flow_key.thread_id}_{flow_key.update_id}",
    )
    task.add_done_callback(
      lambda _task: self._done_flow_task_callback(_task, flow_key),
    )

    new_flow = Flow(
      task=task,
      context=context,
      key=flow_key,
    )
    self._spawned_flows[flow_key] = new_flow

    _logger.debug(
      f"Flow spawned (chat_id={flow_key.chat_id}, user_id={flow_key.user_id}, "
      f"thread_id={flow_key.thread_id}, update_id={flow_key.update_id}), "
      f"limit {len(self._spawned_flows)}/{self._concurrency_limit or '∞'}"
    )

  async def _cancel_inactive_flows(self):
    """
    Cancel Flows that haven't received Updates for a long time
    """
    inactive_keys: deque[FlowKey] = deque()

    for flow in self._spawned_flows.values():
      delta = time.monotonic() - flow.context.last_activity_at
      if (
        delta > flow.context.inactivity_timeout and get_task_status(flow.task) == TaskStatus.RUNNING
      ):
        inactive_keys.append(flow.key)

    await cancel_tasks(
      [self._spawned_flows[key].task for key in inactive_keys], self._flow_cancellation_timeout
    )

    for key in inactive_keys:
      if self._spawned_flows.get(key, None) is not None:
        flow = self._spawned_flows[key]
        status = get_task_status(flow.task)
        if status == TaskStatus.EXCEPTION:
          e = flow.task.exception()
          _logger.error(e, exc_info=e)
        if status == TaskStatus.RUNNING:
          raise FlowCancellationFailed("Failed to cancel the task associated with the Flow.")

        self._spawned_flows.pop(key, None)

  async def _respawn_flow(self, key: FlowKey, initial_update: Update):
    flow = self._spawned_flows[key]

    if get_task_status(flow.task) == TaskStatus.RUNNING:
      await cancel_tasks([flow.task], self._flow_cancellation_timeout)

    if get_task_status(flow.task) != TaskStatus.RUNNING:
      self._spawned_flows.pop(key, None)
      self._spawn_new_flow(key, initial_update)
    else:
      raise UnexpectedError("Failed to cancel the task during flow respawn.")

  def _done_flow_task_callback(self, task: Task, key: FlowKey):
    flow = self._spawned_flows.get(key, None)
    if flow is None:
      return

    status = get_task_status(flow.task)
    if status == TaskStatus.EXCEPTION:
      e = flow.task.exception()
      _logger.error(e, exc_info=e)
    elif status == TaskStatus.RUNNING:
      raise UnexpectedError("The Flow task is still running")

    self._spawned_flows.pop(key, None)

  def _done_bg_task_callback(self, task: Task):
    if get_task_status(task) == TaskStatus.EXCEPTION:
      e = task.exception()
      _logger.error(e, exc_info=e)
    self._bg_tasks.discard(task)

  def create_bg_task(self, coroutine: Coroutine, name: str | None = None):
    """Create a background asyncio task."""
    task = aio.create_task(coroutine, name=name or f"background_task_{secrets.token_urlsafe(8)}")
    task.add_done_callback(self._done_bg_task_callback)
    self._bg_tasks.add(task)

  async def process_update(self, update: Update):
    async with self._lock:
      await self._cancel_inactive_flows()

      await aio.sleep(0)

      for middleware in self._middlewares:
        try:
          if isinstance(middleware, Middleware):
            update = middleware(update)  # type: ignore
          elif isinstance(middleware, AsyncMiddleware):
            update = await middleware(update)  # type: ignore
        except Exception as e:
          _logger.error(e, exc_info=e)
          return
        if update is None:
          return

      try:
        flow_key = self._concurrency_strategy.get_flow_key(update)
      except FlowKeyError as e:
        _logger.error(e, exc_info=e)
        return

      if flow_key in self._spawned_flows:
        if self._respawn_trigger is not None and self._respawn_trigger.check_update(update):
          await self._respawn_flow(flow_key, update)
        else:
          await self._spawned_flows[flow_key].context.put_update(update)
      else:
        if self._spawn_trigger.check_update(update):
          self._spawn_new_flow(flow_key, update)

      await aio.sleep(0)

  @staticmethod
  def _raise_system_exit():
    raise SystemExit()

  async def _long_polling_loop(self):
    retrying = Retrying(
      wait=wait_exponential(multiplier=1, min=1, max=64),
      retry=retry_if_exception_type(telegram.error.TelegramError),
    )
    while True:
      for attempt in retrying:
        with attempt:
          try:
            updates = await self._get_updates()
          except Exception as e:
            _logger.error(f"Error in the long polling loop ({e.__class__.__name__}). {e}")
            raise

      if len(updates) > 0:
        _logger.debug(f"Updates received: {len(updates)}")
        for update in updates:
          await self.process_update(update)
      else:
        await self._cancel_inactive_flows()

  async def initialize(self):
    await self._bot.initialize()

  def add_startup_task(self, coroutine: Coroutine, name: str | None = None):
    """Coroutine that run as background task alongside long polling."""
    self._startup_coroutines.append((name, coroutine))

  async def shutdown(self, max_timeout: timedelta | float = 10.0):
    """Graceful shutdown.
    Args:
      max_timeout:
        The maximum amount of time allowed for all Flow instances and background tasks to
        handle asyncio.CancelledError and shutdown.

    Example:
      try:
        ...
        await app.run_polling()
      finally:
        await app.shutdown(max_timeout=10.0)
    """
    if isinstance(max_timeout, timedelta):
      _max_timeout = float(max_timeout.total_seconds())
    else:
      _max_timeout = float(max_timeout)

    tasks = [flow.task for flow in self._spawned_flows.values()]
    flow_task_count = len(tasks)
    bg_task_count = len(self._bg_tasks)

    tasks.extend(self._bg_tasks)
    if len(tasks) > 0:
      _logger.info(
        f"Waiting for tasks to be cancelled. Flow tasks: {flow_task_count}, background tasks: {bg_task_count}"
      )
      await cancel_tasks(tasks, _max_timeout)

    await self._bot.shutdown()
    self._is_running = False
    _logger.info("Shutdown completed")

  async def run_polling(
    self,
    poll_interval: int = 30,
    allowed_updates: tuple[UpdateType, ...] = (
      UpdateType.MESSAGE,
      UpdateType.CALLBACK_QUERY,
    ),
    handle_sys_signals: bool = True,
    with_bg_tasks: Sequence[Coroutine] | None = None,
  ) -> None:
    """Starts the long polling loop and processes incoming updates.

    Fetches updates from Telegram via long polling and dispatches each update
    to the matching Flow. Blocks until the loop is stopped (e.g. by a system
    signal when ``handle_sys_signals`` is ``True``).

    Args:
      poll_interval: Timeout in seconds for long polling.

      allowed_updates: Update types the bot subscribes to.

      handle_sys_signals: If `True`, installs handlers for `SIGINT`,
        `SIGTERM` and `SIGABRT` to stop polling on system signals. Has no
        effect on Windows.

    Example:
      app = FlowApp(...)
      try:
        await app.run_polling(...)
      finally:
        await app.shutdown()
    """
    if self._is_running:
      raise PyteleflowError(f"{self.__class__.__name__} is already running.")

    self._poll_interval = poll_interval
    self._allowed_updates = allowed_updates

    if handle_sys_signals and platform.system() != "Windows":
      loop = aio.get_event_loop()
      for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        loop.add_signal_handler(sig, self._raise_system_exit)

    await self.initialize()

    for name, coro in self._startup_coroutines:
      self.create_bg_task(coro, name)
      await aio.sleep(0)

    _logger.info("Run long polling")
    try:
      self._is_running = True
      await self._long_polling_loop()
    except aio.CancelledError:
      _logger.info("Stop long polling")

  def add_pre_middlewares(self, middlewares: list[Middleware | AsyncMiddleware]):
    self._middlewares.extend(middlewares)

  @property
  def spawned_flows(self) -> MappingProxyType[FlowKey, Flow]:
    return MappingProxyType(self._spawned_flows)
