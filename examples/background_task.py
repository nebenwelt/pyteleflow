import asyncio as aio
import logging
import os

from telegram.ext import AIORateLimiter, ExtBot, filters

from pyteleflow import ConcurrencyStrategy, Context, FlowApp, widgets

# logging initialization
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def startup(alert: str):
  logger.info(f"Run startup task. alert: {alert}")


async def timer(seconds, chat):
  while True:
    await aio.sleep(seconds)
    await chat.send_message("Wake up!")


async def flow(ctx: Context):
  chat = ctx.initial_update.effective_chat

  select = widgets.Select(ctx=ctx, chat_id=chat.id)
  result = await select.show(
    prompt="Set a timer?",
    items=["Yes"],
    direction="vertical",
  )
  await select.delete()

  if not result.canceled:
    # Run background task
    ctx.create_bg_task(
      timer(3, chat),
      name="timer_background_task",
    )


async def main():
  bot_token = os.environ.get("BOT_TOKEN")

  app = FlowApp(
    ExtBot(bot_token, rate_limiter=AIORateLimiter()),
    entry_coro=flow,
    spawn_trigger=filters.Text(["/start"]),
    concurrency_strategy=ConcurrencyStrategy.CHAT,
  )

  app.add_startup_task(startup(alert="example"))

  try:
    await app.run_polling()
  finally:
    await app.shutdown()


if __name__ == "__main__":
  aio.run(main())
