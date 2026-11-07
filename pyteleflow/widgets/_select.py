import asyncio
import contextlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, NamedTuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

from ..errors import WidgetError
from .._flow import Context
from ._common import Button


class _CBData(NamedTuple):
  uid: str
  action: Literal["select_item", "cancel"]
  item_index: str

  def pack(self) -> str:
    return ":".join(self)

  @staticmethod
  def unpack(text: str) -> "_CBData":
    return _CBData(*text.split(":", 2))  # type: ignore


class Select:
  """The widget allows the user to select one option from several."""

  # Maximum number of items in the vertical layout (one extra button is reserved for Cancel)
  MAX_BUTTONS_VERTICAL: int = 99

  # Maximum number of items in a row in the horizontal layout (Cancel occupies its own row)
  MAX_BUTTONS_HORIZONTAL: int = 8

  @dataclass(slots=True)
  class Result:
    index: int | None
    item: str | None
    canceled: bool

  def __init__(self, ctx: Context, chat_id: int | str):
    """
    Args:
      ctx: Flow context.
      chat_id: Chat where the widget is shown.
    """
    self._ctx: Context = ctx
    self._chat_id: int | str = chat_id

    # The last message shown by this widget. Reused on the next show via edit.
    self._message: Message | None = None

  def _create_keyboard(
    self,
    uid: str,
    items: Sequence[str],
    direction: Literal["vertical", "horizontal"],
    cancel_button: Button | None,
  ) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if direction == "vertical":
      for index, item in enumerate(items):
        keyboard.append(
          [
            InlineKeyboardButton(
              str(item),
              callback_data=_CBData(uid=uid, action="select_item", item_index=str(index)).pack(),
            )
          ]
        )

    elif direction == "horizontal":
      row: list[InlineKeyboardButton] = []
      for index, item in enumerate(items):
        row.append(
          InlineKeyboardButton(
            str(item),
            callback_data=_CBData(uid=uid, action="select_item", item_index=str(index)).pack(),
          )
        )
      keyboard.append(row)

    if cancel_button is not None:
      keyboard.append(
        [
          InlineKeyboardButton(
            cancel_button.text,
            style=cancel_button.style,
            callback_data=_CBData(uid=uid, action="cancel", item_index="").pack(),
          )
        ]
      )

    return InlineKeyboardMarkup(keyboard)

  def _check_items(
    self, items: Sequence[str], direction: Literal["vertical", "horizontal"]
  ) -> None:
    max_buttons = (
      self.MAX_BUTTONS_HORIZONTAL if direction == "horizontal" else self.MAX_BUTTONS_VERTICAL
    )
    if len(items) > max_buttons:
      raise WidgetError(
        f"Too many items: {len(items)} for {direction} layout (maximum is {max_buttons})."
      )

  async def show(
    self,
    prompt: str,
    items: Sequence[str],
    direction: Literal["vertical", "horizontal"] = "vertical",
    parse_mode: ParseMode | None = None,
    cancel_button: Button | None = None,
    reply_to_message: Message | None = None,
  ) -> Result:
    """Show the select in the widget chat or as a reply to the given message."""
    self._check_items(items, direction)

    uid: str = secrets.token_urlsafe(8)
    reply_markup = self._create_keyboard(uid, items, direction, cancel_button)

    if self._message is not None:
      # The widget was shown before: replace the previous message instead of sending a new one.
      edited = await self._message.edit_text(
        text=prompt,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
      )
      if isinstance(edited, Message):
        self._message = edited
    elif reply_to_message is None:
      self._message = await self._ctx.bot.send_message(
        chat_id=self._chat_id,
        text=prompt,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
      )
    else:
      self._message = await reply_to_message.reply_text(
        text=prompt,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
      )

    try:
      resp = await self._ctx.callback_query(data_pattern=f"^{uid}.*")
      await resp.answer()
    except asyncio.CancelledError:
      # Best-effort cleanup so a cancelled flow does not leave an orphaned widget message.
      with contextlib.suppress(Exception):
        await self.delete()
      raise

    data = _CBData.unpack(resp.data)  # type: ignore
    if data.action == "cancel":
      return Select.Result(None, None, canceled=True)
    elif data.action == "select_item":
      return Select.Result(
        index=int(data.item_index), item=items[int(data.item_index)], canceled=False
      )

    else:
      raise WidgetError(f'Action "{data.action}" is not implemented.')

  async def delete(self) -> None:
    """Delete the message shown by the widget, if any."""
    if self._message is not None:
      message, self._message = self._message, None
      await message.delete()
