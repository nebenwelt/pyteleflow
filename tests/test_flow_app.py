import asyncio as aio

import logging

import pytest

from telegram.ext import AIORateLimiter, ExtBot, filters

from pyteleflow import Context, FlowApp, ConcurrencyStrategy

from . import data as td

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def _flow_coro(ctx: Context):
  while True:
    await ctx.message()
    logger.debug("CALL _flow_coro")


@pytest.mark.asyncio
async def test_spawn_flow():
  app = FlowApp(
    ExtBot("TEST_BOT_TOKEN", rate_limiter=AIORateLimiter()),
    entry_coro=_flow_coro,
    concurrency_limit=2,
    flow_inactivity_timeout=999.0,
    concurrency_strategy=ConcurrencyStrategy.CHAT,
    spawn_trigger=filters.Text(["/start"]),
    respawn_trigger=None,
  )

  update_1 = td.update(
    0,
    td.message(text="/start", from_user=td.user(111, "test_user_1"), _chat=td.chat(111)),
  )

  update_2 = td.update(
    1,
    td.message(text="/start", from_user=td.user(222, "test_user_2"), _chat=td.chat(222)),
  )

  await app.process_update(update_1)
  await app.process_update(update_2)

  assert len(app.spawned_flows) == 2

  await app.shutdown()


@pytest.mark.asyncio
async def test_inactivity_timeout():
  _inactivity_timeout = 1.0

  app = FlowApp(
    ExtBot("TEST_BOT_TOKEN", rate_limiter=AIORateLimiter()),
    entry_coro=_flow_coro,
    concurrency_limit=1,
    flow_inactivity_timeout=_inactivity_timeout,
    concurrency_strategy=ConcurrencyStrategy.CHAT,
    spawn_trigger=filters.Text(["/start"]),
    respawn_trigger=None,
  )

  _user = td.user(111, "test_user_1")
  _chat = td.chat(chat_id=111)
  update_1 = td.update(0, td.message(text="/start", from_user=_user, _chat=_chat))
  update_2 = td.update(1, td.message(text="hello", from_user=_user, _chat=_chat))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  await aio.sleep(_inactivity_timeout + 0.5)
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 0

  await app.shutdown()


@pytest.mark.asyncio
async def test_respawn_flow():
  app = FlowApp(
    ExtBot("TEST_BOT_TOKEN", rate_limiter=AIORateLimiter()),
    entry_coro=_flow_coro,
    concurrency_limit=2,
    flow_inactivity_timeout=999.0,
    concurrency_strategy=ConcurrencyStrategy.CHAT,
    spawn_trigger=filters.Text(["/start"]),
    respawn_trigger=filters.Text(["/start"]),
  )

  _user = td.user(111, "test_user_1")
  _chat = td.chat(chat_id=111)
  update_1 = td.update(0, td.message(text="/start", from_user=_user, _chat=_chat))
  update_2 = td.update(1, td.message(text="/start", from_user=_user, _chat=_chat))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow_before = next(iter(app.spawned_flows.values()))

  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  flow_after = next(iter(app.spawned_flows.values()))

  assert flow_after.task is not flow_before.task
  assert flow_before.task.cancelled()
  assert flow_after.context.last_update.update_id == 1

  await app.shutdown()


@pytest.mark.asyncio
async def test_concurrency_limit():
  app = FlowApp(
    ExtBot("TEST_BOT_TOKEN", rate_limiter=AIORateLimiter()),
    entry_coro=_flow_coro,
    concurrency_limit=1,
    flow_inactivity_timeout=999.0,
    concurrency_strategy=ConcurrencyStrategy.CHAT,
    spawn_trigger=filters.Text(["/start"]),
    respawn_trigger=None,
  )

  update_1 = td.update(
    0,
    td.message(text="/start", from_user=td.user(111, "test_user_1"), _chat=td.chat(111)),
  )

  update_2 = td.update(
    1,
    td.message(text="/start", from_user=td.user(222, "test_user_2"), _chat=td.chat(222)),
  )

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1

  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1

  await app.shutdown()
