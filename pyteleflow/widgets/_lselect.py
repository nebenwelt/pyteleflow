import secrets
from typing import Literal, NamedTuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

from .._flow import Context
from ..errors import WidgetError
from ._common import Button, ButtonLayout


class _CBData(NamedTuple):
  uid: str
  action: Literal["select_item"]
  row: str
  column: str

  def pack(self) -> str:
    return ":".join(self)

  @staticmethod
  def unpack(text: str) -> "_CBData":
    parts = text.split(":")
    return _CBData(parts[0], parts[1], parts[2], parts[3])  # type: ignore


class LSelect:
  """ Advanced version of the Select widget with a custom layout.

  Example:

    panel_layout = [
      ["✏️", "📁", "⏰", "📺"],
      [Button("Admin", style="primary"), "Rules"],
      ["Users", "Setting"],
      [Button("Cancel", style="danger")]
    ]
    select = LSelect(layout = panel_layout, ...)
    result = await select.show(...)

  """
  def __init__(
    self,
    ctx: Context,
    prompt: str,
    layout: ButtonLayout | None = None,
    parse_mode: ParseMode | None = None,
  ):
    self._ctx: Context = ctx
    self._prompt: str = prompt
    self._layout: ButtonLayout | None = layout
    self._parse_mode = parse_mode

  def _create_keyboard(self, uid: str, layout: ButtonLayout) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    for row_index, row in enumerate(layout):
      keyboard_row: list[InlineKeyboardButton] = []
      for column_index, item in enumerate(row):
        callback_data = _CBData(
          uid=uid,
          action="select_item",
          row=str(row_index),
          column=str(column_index),
        ).pack()

        if isinstance(item, str):
          keyboard_row.append(InlineKeyboardButton(item, callback_data=callback_data))
        elif isinstance(item, Button):
          keyboard_row.append(
            InlineKeyboardButton(item.text, callback_data=callback_data, style=item.style)
          )
        else:
          raise WidgetError("item must be of type str or Button")
      keyboard.append(keyboard_row)

    return InlineKeyboardMarkup(keyboard)

  async def _show(
    self,
    chat_id: int | str | None,
    layout: ButtonLayout | None = None,
    reply_to_message: Message | None = None,
  ) -> str:
    layout_to_use = layout if layout is not None else self._layout
    if layout_to_use is None:
      raise WidgetError("layout is None")
    if len(layout_to_use) == 0:
      raise WidgetError("Layout is empty")

    uid: str = secrets.token_urlsafe(8)
    reply_markup = self._create_keyboard(uid, layout_to_use)

    sent_msg: Message | None = None
    try:
      if reply_to_message is None:
        sent_msg = await self._ctx.bot.send_message(
          chat_id=chat_id,  # type: ignore
          text=self._prompt,
          reply_markup=reply_markup,
          parse_mode=self._parse_mode,
        )
      else:
        sent_msg = await reply_to_message.reply_text(
          text=self._prompt,
          reply_markup=reply_markup,
          parse_mode=self._parse_mode,
        )

      resp = await self._ctx.callback_query(data_pattern=f"^{uid}.*")
      await resp.answer()

      data = _CBData.unpack(resp.data)  # type: ignore
      row_index = int(data.row)
      column_index = int(data.column)

      if row_index < 0 or row_index >= len(layout_to_use):
        raise WidgetError("Invalid button row")
      if column_index < 0 or column_index >= len(layout_to_use[row_index]):
        raise WidgetError("Invalid button column")

      item = layout_to_use[row_index][column_index]
      return str(item)

    finally:
      if sent_msg is not None:
        await sent_msg.delete()

  async def show(self, chat_id: int | str, layout: ButtonLayout | None = None) -> str:
    return await self._show(chat_id, layout)

  async def show_as_reply(self, reply_to_message: Message, layout: ButtonLayout | None = None) -> str:
    return await self._show(None, layout, reply_to_message)
