import asyncio as aio

import pytest

from telegram.constants import ChatType
from telegram.ext import AIORateLimiter, ExtBot, filters

from pyteleflow import ConcurrencyStrategy, Context, FlowApp

from . import data as td


async def _flow_coro(ctx: Context):
  while True:
    await ctx.message()


def _make_app(strategy) -> FlowApp:
  return FlowApp(
    ExtBot("TEST_BOT_TOKEN", rate_limiter=AIORateLimiter()),
    entry_coro=_flow_coro,
    concurrency_limit=None,
    flow_inactivity_timeout=999.0,
    concurrency_strategy=strategy,
    spawn_trigger=filters.Text(["/start"]),
    respawn_trigger=None,
  )


@pytest.mark.asyncio
async def test_chat_strategy():
  """CHAT: one Flow per chat, no matter which user sent the update."""
  app = _make_app(ConcurrencyStrategy.CHAT)

  _user_1 = td.user(111, "test_user_1")
  _user_2 = td.user(222, "test_user_2")
  _chat_1 = td.chat(chat_id=111)
  _chat_2 = td.chat(chat_id=222)

  update_1 = td.update(0, td.message(text="/start", from_user=_user_1, _chat=_chat_1))
  update_2 = td.update(1, td.message(text="/start", from_user=_user_2, _chat=_chat_1))
  update_3 = td.update(2, td.message(text="/start", from_user=_user_1, _chat=_chat_2))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.chat_id == _chat_1.id
  assert flow.key.user_id is None

  # A different user in the same chat is routed to the same Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow
  await aio.sleep(0.05)
  assert flow.context.last_update.update_id == update_2.update_id

  # A different chat gets its own Flow.
  await app.process_update(update_3)
  assert len(app.spawned_flows) == 2
  assert {key.chat_id for key in app.spawned_flows} == {_chat_1.id, _chat_2.id}

  await app.shutdown()


@pytest.mark.asyncio
async def test_user_in_global_strategy():
  """USER_IN_GLOBAL: one Flow per user across all chats."""
  app = _make_app(ConcurrencyStrategy.USER_IN_GLOBAL)

  _user_1 = td.user(111, "test_user_1")
  _user_2 = td.user(222, "test_user_2")
  _chat_1 = td.chat(chat_id=111)
  _chat_2 = td.chat(chat_id=222)

  update_1 = td.update(0, td.message(text="/start", from_user=_user_1, _chat=_chat_1))
  update_2 = td.update(1, td.message(text="/start", from_user=_user_1, _chat=_chat_2))
  update_3 = td.update(2, td.message(text="/start", from_user=_user_2, _chat=_chat_1))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.user_id == _user_1.id
  assert flow.key.chat_id is None

  # The same user in another chat is routed to the existing Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow
  await aio.sleep(0.05)
  assert flow.context.last_update.update_id == update_2.update_id

  # Another user gets a separate Flow, even in the same chat
  await app.process_update(update_3)
  assert len(app.spawned_flows) == 2
  assert {key.user_id for key in app.spawned_flows} == {_user_1.id, _user_2.id}
  assert all(key.chat_id is None for key in app.spawned_flows)

  await app.shutdown()


@pytest.mark.asyncio
async def test_user_in_chat_strategy():
  """USER_IN_CHAT: one Flow per user within a chat."""
  app = _make_app(ConcurrencyStrategy.USER_IN_CHAT)

  _user_1 = td.user(111, "test_user_1")
  _user_2 = td.user(222, "test_user_2")
  _chat_1 = td.chat(chat_id=111)
  _chat_2 = td.chat(chat_id=222)

  update_1 = td.update(0, td.message(text="/start", from_user=_user_1, _chat=_chat_1))
  update_2 = td.update(1, td.message(text="/start", from_user=_user_1, _chat=_chat_1))
  update_3 = td.update(2, td.message(text="/start", from_user=_user_1, _chat=_chat_2))
  update_4 = td.update(3, td.message(text="/start", from_user=_user_2, _chat=_chat_1))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.chat_id == _chat_1.id
  assert flow.key.user_id == _user_1.id

  # The same user in the same chat is routed to the existing Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow
  await aio.sleep(0.05)
  assert flow.context.last_update.update_id == update_2.update_id

  # The same user in another chat gets a separate Flow
  await app.process_update(update_3)
  assert len(app.spawned_flows) == 2

  # Another user in the same chat gets a separate Flow
  await app.process_update(update_4)
  assert len(app.spawned_flows) == 3
  assert {(key.chat_id, key.user_id) for key in app.spawned_flows} == {
    (_chat_1.id, _user_1.id),
    (_chat_2.id, _user_1.id),
    (_chat_1.id, _user_2.id),
  }

  await app.shutdown()


@pytest.mark.asyncio
async def test_thread_in_chat_strategy():
  """THREAD_IN_CHAT: one Flow per thread within a group chat."""
  app = _make_app(ConcurrencyStrategy.THREAD_IN_CHAT)

  _user = td.user(111, "test_user_1")
  _group = td.chat(chat_id=111, chat_type=ChatType.GROUP)

  update_1 = td.update(
    0, td.message(text="/start", from_user=_user, _chat=_group, message_id=1, message_thread_id=10)
  )
  update_2 = td.update(
    1, td.message(text="/start", from_user=_user, _chat=_group, message_id=2, message_thread_id=10)
  )
  update_3 = td.update(
    2, td.message(text="/start", from_user=_user, _chat=_group, message_id=3, message_thread_id=11)
  )

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.chat_id == _group.id
  assert flow.key.thread_id == 10

  # Another message in the same thread is routed to the existing Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow
  await aio.sleep(0.05)
  assert flow.context.last_update.update_id == update_2.update_id

  # A message in another thread gets a separate Flow
  await app.process_update(update_3)
  assert len(app.spawned_flows) == 2
  assert {key.thread_id for key in app.spawned_flows} == {10, 11}

  await app.shutdown()


@pytest.mark.asyncio
async def test_thread_in_chat_strategy_message_id_fallback():
  """THREAD_IN_CHAT: without message_thread_id the message id is used as the thread id."""
  app = _make_app(ConcurrencyStrategy.THREAD_IN_CHAT)

  _user = td.user(111, "test_user_1")
  _group = td.chat(chat_id=111, chat_type=ChatType.SUPERGROUP)

  update_1 = td.update(0, td.message(text="/start", from_user=_user, _chat=_group, message_id=100))
  update_2 = td.update(1, td.message(text="/start", from_user=_user, _chat=_group, message_id=101))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.thread_id == update_1.message.message_id

  # Another message without message_thread_id has its own message id as the thread id
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 2
  assert {key.thread_id for key in app.spawned_flows} == {100, 101}

  await app.shutdown()


@pytest.mark.asyncio
async def test_thread_in_chat_strategy_private_chat():
  """THREAD_IN_CHAT: a private chat is a single thread."""
  app = _make_app(ConcurrencyStrategy.THREAD_IN_CHAT)

  _user = td.user(111, "test_user_1")
  _private_chat = td.chat(chat_id=111)

  update_1 = td.update(
    0, td.message(text="/start", from_user=_user, _chat=_private_chat, message_id=1)
  )
  update_2 = td.update(
    1, td.message(text="/start", from_user=_user, _chat=_private_chat, message_id=2)
  )

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.chat_id == _private_chat.id
  assert flow.key.thread_id is None

  # Different messages in a private chat still share the same Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow

  await app.shutdown()


@pytest.mark.asyncio
async def test_single_flow_strategy():
  """SINGLE_FLOW: one Flow for every update, regardless of chat or user."""
  app = _make_app(ConcurrencyStrategy.SINGLE_FLOW)

  _user_1 = td.user(111, "test_user_1")
  _user_2 = td.user(222, "test_user_2")
  _chat_1 = td.chat(chat_id=111)
  _chat_2 = td.chat(chat_id=222)

  update_1 = td.update(0, td.message(text="/start", from_user=_user_1, _chat=_chat_1))
  update_2 = td.update(1, td.message(text="/start", from_user=_user_2, _chat=_chat_2))

  await app.process_update(update_1)
  assert len(app.spawned_flows) == 1
  flow = next(iter(app.spawned_flows.values()))
  assert flow.key.chat_id is None
  assert flow.key.user_id is None
  assert flow.key.thread_id is None

  # Updates from another chat and another user are routed to the same Flow
  await app.process_update(update_2)
  assert len(app.spawned_flows) == 1
  assert next(iter(app.spawned_flows.values())) is flow
  await aio.sleep(0.05)
  assert flow.context.last_update.update_id == update_2.update_id

  await app.shutdown()
