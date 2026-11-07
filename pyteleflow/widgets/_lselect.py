import asyncio
import contextlib
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
  """Advanced version of the Select widget with a custom layout.

  Example:

    panel_layout = [
      ["✏️", "📁", "⏰", "📺"],
      [Button("Admin", style="primary"), "Rules"],
      ["Users", "Setting"],
      [Button("Cancel", style="danger")]
    ]
    select = LSelect(ctx=ctx, chat_id=chat.id)
    result = await select.show(prompt="Menu", layout=panel_layout)

  """

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

  def _check_layout(self, layout: ButtonLayout | None) -> None:
    if layout is None:
      raise WidgetError("layout is None")
    if len(layout) == 0:
      raise WidgetError("Layout is empty")

  async def show(
    self,
    prompt: str,
    layout: ButtonLayout,
    parse_mode: ParseMode | None = None,
    reply_to_message: Message | None = None,
  ) -> str:
    """Show the select in the widget chat or as a reply to the given message."""
    self._check_layout(layout)

    uid: str = secrets.token_urlsafe(8)
    reply_markup = self._create_keyboard(uid, layout)

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
    row_index = int(data.row)
    column_index = int(data.column)

    if row_index < 0 or row_index >= len(layout):
      raise WidgetError("Invalid button row")
    if column_index < 0 or column_index >= len(layout[row_index]):
      raise WidgetError("Invalid button column")

    item = layout[row_index][column_index]
    return str(item)

  async def delete(self) -> None:
    """Delete the message shown by the widget, if any."""
    if self._message is not None:
      message, self._message = self._message, None
      await message.delete()
