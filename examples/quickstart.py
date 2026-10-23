# type: ignore

import asyncio as aio
import os
import logging

from telegram.ext import ExtBot, AIORateLimiter, filters
from pyteleflow import FlowApp, Context, widgets, ConcurrencyStrategy

# logging initialization
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


async def quickstart_flow(ctx: Context):
  # Get the current chat with the user
  chat = ctx.initial_update.effective_chat

  # Send the user an initial message asking a question
  await chat.send_message("What’s your name?")

  # Wait for the user to send a text message in the chat.
  # Other message types are ignored because we specified the TEXT filter.
  msg = await ctx.message(filters.TEXT)
  user_name = msg.text

  # Ask the user to send a photo
  await chat.send_message("Send me a photo of yourself")

  # Wait until the user sends a photo
  msg = await ctx.message(filters.PHOTO)
  user_photo = msg.photo[0]

  # We show the user a widget with buttons and wait for them to select one
  result = await widgets.Select(
    ctx=ctx,
    prompt="Your profile is complete. Would you like to save it?",
    items=["Save", "View profile"],
    direction="horizontal",
  ).show(chat.id, cancel_button=True)

  if not result.canceled:
    if result.item == "Save":
      alert = await chat.send_message("Profile saved")
      await aio.sleep(2)
      await alert.delete()
    elif result.item == "View profile":
      await chat.send_photo(
        photo=user_photo,
        caption=f"PROFILE\nUser name: {user_name}\nUser ID: {msg.from_user.id}",
      )


async def main():
  bot_token = os.environ.get("BOT_TOKEN")

  app = FlowApp(
    ExtBot(bot_token, rate_limiter=AIORateLimiter()),
    entry_coro=quickstart_flow,
    spawn_trigger=filters.Text(["/start"]),
    concurrency_strategy=ConcurrencyStrategy.CHAT
  )

  try:
    await app.run_polling()
  finally:
    await app.shutdown()


if __name__ == "__main__":
  aio.run(main())
