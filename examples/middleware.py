# type: ignore

import asyncio as aio
import os
import logging
from collections.abc import Iterable

from telegram import Update
from telegram.ext import ExtBot, AIORateLimiter, filters
from pyteleflow import FlowApp, Context, widgets, ConcurrencyStrategy
from pyteleflow.middleware import Middleware

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


class Authentication(Middleware):
  def __init__(self, allowed_user_ids: Iterable[int]):
    self._allowed_user_ids: set[int] = set(allowed_user_ids)

  def __call__(self, update: Update | None):
    if update.effective_user is not None and update.effective_user.id in self._allowed_user_ids:
      # If the user is on the allowlist, pass the Update to the next middleware in the chain.
      return update

    # Returning None stops the Update processing chain entirely.
    return None


async def flow(ctx: Context):
  await ctx.initial_update.effective_message.reply_text("Hello")


async def main():
  bot_token = os.environ.get("BOT_TOKEN")

  app = FlowApp(
    ExtBot(bot_token, rate_limiter=AIORateLimiter()),
    entry_coro=flow,
    spawn_trigger=filters.Text(["/start"]),
    concurrency_strategy=ConcurrencyStrategy.CHAT,
  )

  # The order in which items are added matters.
  app.add_pre_middlewares(
    [Authentication(allowed_user_ids=(111111, 222222, 3333333))],
  )
  try:
    await app.run_polling()
  finally:
    await app.shutdown()


if __name__ == "__main__":
  aio.run(main())
