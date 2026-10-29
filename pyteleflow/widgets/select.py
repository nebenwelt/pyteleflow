import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple, Literal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

from ..errors import WidgetError
from .._flow import Context


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
  # Maximum number of items in the vertical layout (one extra button is reserved for Cancel)
  MAX_BUTTONS_VERTICAL: int = 99

  # Maximum number of items in a row in the horizontal layout (Cancel occupies its own row)
  MAX_BUTTONS_HORIZONTAL: int = 8

  @dataclass(slots=True)
  class Result:
    index: int | None
    item: str | None
    canceled: bool

  def __init__(
    self,
    ctx: Context,
    prompt: str,
    items: Sequence[str],
    direction: Literal["vertical", "horizontal"] = "vertical",
    parse_mode: ParseMode | None = None,
  ):
    """
    Args:
      ctx: Flow context.
      prompt: Message text shown above the keyboard.
      items: Full list of items to choose from.
      direction: Vertical or horizontal button layout.

    Raises:
      WidgetError: If the number of items exceeds the limit for the given layout.
    """
    max_buttons = (
      self.MAX_BUTTONS_HORIZONTAL if direction == "horizontal" else self.MAX_BUTTONS_VERTICAL
    )
    if len(items) > max_buttons:
      raise WidgetError(
        f"Too many items: {len(items)} for {direction} layout (maximum is {max_buttons})."
      )

    self._ctx: Context = ctx
    self._items: Sequence[str] = items
    self._prompt: str = prompt
    self._direction = direction
    self._parse_mode = parse_mode

  def _create_keyboard(self, uid: str, cancel_button: bool):
    keyboard = []
    row = []

    if self._direction == "vertical":
      for index, item in enumerate(self._items):
        row = [
          InlineKeyboardButton(
            str(item),
            callback_data=_CBData(uid=uid, action="select_item", item_index=str(index)).pack(),
          )
        ]
        keyboard.append(row)

    elif self._direction == "horizontal":
      for index, item in enumerate(self._items):
        row.append(
          InlineKeyboardButton(
            str(item),
            callback_data=_CBData(uid=uid, action="select_item", item_index=str(index)).pack(),
          )
        )
      keyboard.append(row)

    if cancel_button:
      row = [
        InlineKeyboardButton(
          "Cancel",
          style="danger",
          callback_data=_CBData(uid=uid, action="cancel", item_index="").pack(),
        )
      ]
      keyboard.append(row)
    return keyboard

  async def _show(
    self,
    chat_id: int | str | None,
    cancel_button: bool,
    reply_to_message: Message | None = None,
  ) -> Result:
    uid: str = secrets.token_urlsafe(8)
    keyboard = self._create_keyboard(uid, cancel_button)

    sent_msg = None
    try:
      if reply_to_message is None:
        sent_msg = await self._ctx.bot.send_message(
          chat_id=chat_id,  # type: ignore
          text=self._prompt,
          reply_markup=InlineKeyboardMarkup(keyboard),
          parse_mode=self._parse_mode,
        )
      else:
        sent_msg = await reply_to_message.reply_text(
          text=self._prompt,
          reply_markup=InlineKeyboardMarkup(keyboard),
          parse_mode=self._parse_mode,
        )

      resp = await self._ctx.callback_query(data_pattern=f"^{uid}.*")
      await resp.answer()

      data = _CBData.unpack(resp.data)  # type: ignore
      if data.action == "cancel":
        return Select.Result(None, None, canceled=True)
      elif data.action == "select_item":
        return Select.Result(
          index=int(data.item_index), item=self._items[int(data.item_index)], canceled=False
        )

      else:
        raise WidgetError(f'Action "{data.action}" is not implemented.')

    finally:
      if sent_msg is not None:
        await sent_msg.delete()

  async def show_as_reply(self, reply_to_message: Message, cancel_button: bool = True) -> Result:
    return await self._show(None, cancel_button, reply_to_message)

  async def show(self, chat_id: int | str, cancel_button: bool = True) -> Result:
    return await self._show(chat_id, cancel_button)
