import asyncio as aio
import logging
from asyncio import Task
from enum import IntEnum

from telegram import Update
from telegram.constants import UpdateType

from .errors import UnexpectedError

_logger = logging.getLogger(__name__)


class TaskStatus(IntEnum):
  RUNNING = 10
  CANCELLED = 20
  EXCEPTION = 30
  FINISHED = 40


def get_task_status(task: Task) -> TaskStatus:
  if task.cancelled():
    return TaskStatus.CANCELLED
  elif task.done():
    if task.exception() is not None:
      return TaskStatus.EXCEPTION
    else:
      return TaskStatus.FINISHED
  else:
    return TaskStatus.RUNNING


def get_update_type(update: Update) -> UpdateType:
  for update_type in UpdateType:
    if getattr(update, update_type.value) is not None:
      return update_type
  raise UnexpectedError("Fields that define the Update type are not set in the Update object.")


async def cancel_tasks(tasks: list[Task], cancellation_timeout: float):
  if len(tasks) == 0:
    return

  for task in tasks:
    task.cancel()

  _, pending = await aio.wait(tasks, timeout=cancellation_timeout, return_when=aio.ALL_COMPLETED)

  if len(pending) > 0:
    _logger.warning(f"{len(pending)} tasks did not complete within the cancellation timeout.")

  # Retry stopping hung tasks
  for task in pending:
    task.cancel()

  await aio.sleep(0)
