![Static Badge](https://img.shields.io/badge/version-0.1.0-blue?style=plastic) ![Static Badge](https://img.shields.io/badge/license-MIT-green?style=plastic) ![Static Badge](https://img.shields.io/badge/python-3.12+-blue?style=plastic&logo=python)

# Introduction

`pyteleflow` is an asynchronous Python framework for building Telegram bots. It offers an alternative to the traditional approach based on event handlers and finite-state machines (FSMs).

Instead of distributing conversation logic across handlers, wiring them together, and managing states manually, you describe the entire interaction flow in one or more asynchronous functions.

With `pyteleflow`, you write code the same way you think about a conversation:
 - ask the user a question
 - wait for a response
 - perform an action
 - ask another question
 - and so on

Here is what a minimal example looks like:
```python
async def your_flow(ctx: Context):
  # Get the current chat with the user
  chat = ctx.initial_update.effective_chat

  # Send the user an initial message asking a question
  await chat.send_message("How old are you?")

  # Wait for the user to send a text message in the chat.
  # Other message types are ignored because we specified the TEXT filter.
  msg = await ctx.message(filters.TEXT)
  age = msg.text

  # Ask the user to send a photo
  await chat.send_message("Send me a photo of yourself")

  # Wait until the user sends a photo
  msg = await ctx.message(filters.PHOTO)
  photo = msg.photo
```

And there is more! `pyteleflow` also makes it easy to describe and create widgets:
```python
# ...
result = await widgets.Select(
  ctx=ctx,
  prompt="Which file-sharing service do you use?",
  items=["Skype", "Telegram"],
).show_as_reply(msg)
# ...
```

`pyteleflow` makes code easier to write and review, including when an AI agent writes it for you.


# Dependencies
To access the Telegram Bot API, `pyteleflow` uses the popular [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) wrapper. You can also use the extensive collection of existing filters provided by `python-telegram-bot`.

Why not aiogram?
aiogram uses heavyweight Pydantic models, and its author does not appear to have plans to move away from them.


# Quickstart
## Installation
Using uv:
```sh
uv add pyteleflow
```

Using pip:
```sh
pip install pyteleflow
```


## Simple Bot
> 💡 The code for this example is in [quickstart.py](./examples/quickstart.py)



1. Import the dependencies and initialize logging:
```python
import asyncio as aio
import os
import logging

from telegram.ext import ExtBot, AIORateLimiter, filters
from pyteleflow import FlowApp, Context, widgets, ConcurrencyStrategy

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
```

2. Create a Flow that collects a simple user profile:
```python
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

  # Show the user a widget with buttons and wait for their selection
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
        caption=f"PROFILE\nUser name:  {user_name}\nUser ID:  {msg.from_user.id}",
      )
```

3. Create the application, specifying the Flow to run, and start it:

```python
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
```

4. To start a conversation with the bot, send the `/start` command in the bot's chat.


# Overview
## Framework specifics and limitations

__Conversation state does not survive restarts.__

The simplicity of writing and reading Flows comes at a cost. In the current architecture, active Flow instances are stored only in process memory. If the bot restarts, all conversations will be lost, and users will have to start them over. Python cannot serialize and restore the stack of `asyncio` coroutines. As a result, a coroutine cannot resume from its suspension point after the process restarts. There are theoretically a couple of ways to address this problem, but they would make Flow code more complicated.

How critical is this?
There are different opinions on this. For example, web users are accustomed to a browser page's front-end state being reset when the page is refreshed, while the back-end state (user data) is stored persistently and survives restarts. Telegram bots are also the front-end state of your application.

## Widgets
Currently, `pyteleflow.widgets` includes only a few widgets. More may be added in the future, but for now these widgets serve as examples of how you can implement your own.

## Flow cancellation handling
Spawned Flow instances can be cancelled for several reasons:

__Flow inactivity__
The last activity is considered to be the moment you receive a message through the context, when `ctx.message()` returns a received message that matches the specified filter
```python
msg = await ctx.message(filters.PHOTO)
```
If the period of inactivity exceeds `flow_inactivity_timeout` (set when creating `FlowApp`), the Flow instance will be cancelled. You can change this timeout for an individual Flow during the conversation through the context:
```python
ctx.inactivity_timeout = timedelta(minutes=20)
```

__Flow respawn__
If a filter is configured in `respawn_trigger` (set when creating `FlowApp`), for example `filters.Text(["/start"])`, the active Flow instance will first be cancelled and then restarted from the beginning.

__Stopping the bot application__
Always use the `FlowApp.shutdown()` method when stopping the application. This method initiates cancellation of all active Flow instances.


When a coroutine is cancelled, an `asyncio.CancelledError` exception is raised inside it. You can handle it if necessary:
```python
async def your_flow(ctx: Context):
  try:
    # ...
    msg = ctx.message(filter.PHOTO)
    # ...
  except asyncio.CancelledError:
    # Handle Flow cancellation

    raise
```

## Middleware

> 💡 The code for this example is in [middleware.py](./examples/middleware.py)

Middleware allows you to intercept incoming `Update` objects before they reach a Flow. You can use middleware to restrict access, log incoming updates, modify an `Update` before processing, and more.

If a middleware returns `None`, the remaining middleware chain is skipped, and the `Update` is discarded.

```python
from pyteleflow.middleware import Middleware

class Authentication(Middleware):
  def __init__(self, allowed_user_ids: Iterable[int]):
    self._allowed_user_ids: set[int] = set(allowed_user_ids)

  def __call__(self, update: Update | None):
    if update.effective_user is not None and update.effective_user.id in self._allowed_user_ids:
      return update

    return None
```

Middleware is executed in the order in which it is added:

```python
app.add_pre_middlewares(
    [Authentication(allowed_user_ids=(111111, 222222, 3333333))],
)
```

## Background tasks
`pyteleflow` supports running background tasks. See the example in [background_task.py](./examples/background_task.py) 
