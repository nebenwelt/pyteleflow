import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, NamedTuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .._flow import Context
from ..errors import WidgetError


class _CBData(NamedTuple):
  uid: str
  action: Literal["select_item", "prev", "next", "cancel", "noop"]
  value: str

  def pack(self) -> str:
    return ":".join(self)

  @staticmethod
  def unpack(text: str) -> "_CBData":
    return _CBData(*text.split(":", 2))  # type: ignore


class PagedSelect:
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
    page_size: int = 5,
  ):
    """
    Args:
      ctx: Flow context.
      prompt: Message text shown above the keyboard.
      items: Full list of items to choose from.
      page_size: Number of items displayed on a single page.
        Must be greater than or equal to 1.

    Raises:
      ValueError: If `page_size` is less than 1.
    """
    if page_size < 1:
      raise ValueError("page_size must be greater than or equal to 1.")

    self._ctx: Context = ctx
    self._items: Sequence[str] = items
    self._prompt: str = prompt
    self._page_size: int = page_size

  @property
  def pages_count(self) -> int:
    """Total number of pages (not less than 1)."""
    return max(1, -(-len(self._items) // self._page_size))

  def _create_keyboard(
    self, uid: str, page: int, cancel_button: bool
  ) -> list[list[InlineKeyboardButton]]:
    keyboard = []

    start = page * self._page_size
    end = min(start + self._page_size, len(self._items))

    for index in range(start, end):
      keyboard.append(
        [
          InlineKeyboardButton(
            str(self._items[index]),
            callback_data=_CBData(uid=uid, action="select_item", value=str(index)).pack(),
          )
        ]
      )

    pages_count = self.pages_count
    if pages_count > 1:
      keyboard.append(
        [
          InlineKeyboardButton(
            "<",
            callback_data=_CBData(
              uid=uid, action="prev", value=str((page - 1) % pages_count)
            ).pack(),
          ),
          InlineKeyboardButton(
            f"{page + 1}/{pages_count}",
            callback_data=_CBData(uid=uid, action="noop", value="").pack(),
          ),
          InlineKeyboardButton(
            ">",
            callback_data=_CBData(
              uid=uid, action="next", value=str((page + 1) % pages_count)
            ).pack(),
          ),
        ]
      )

    if cancel_button:
      keyboard.append(
        [
          InlineKeyboardButton(
            "Cancel",
            style="danger",
            callback_data=_CBData(uid=uid, action="cancel", value="").pack(),
          )
        ]
      )

    return keyboard

  async def _show(
    self,
    chat_id: int | str | None,
    cancel_button: bool,
    reply_to_message: Message | None = None,
  ) -> Result:
    uid: str = secrets.token_urlsafe(8)
    page: int = 0

    sent_msg: Message | None = None
    try:
      if reply_to_message is None:
        sent_msg = await self._ctx.bot.send_message(
          chat_id=chat_id,  # type: ignore
          text=self._prompt,
          reply_markup=InlineKeyboardMarkup(self._create_keyboard(uid, page, cancel_button)),
        )
      else:
        sent_msg = await reply_to_message.reply_text(
          text=self._prompt,
          reply_markup=InlineKeyboardMarkup(self._create_keyboard(uid, page, cancel_button)),
        )

      while True:
        resp = await self._ctx.callback_query(data_pattern=f"^{uid}.*")
        await resp.answer()

        data = _CBData.unpack(resp.data)  # type: ignore

        if data.action == "cancel":
          return PagedSelect.Result(None, None, canceled=True)

        elif data.action == "select_item":
          index = int(data.value)
          return PagedSelect.Result(index=index, item=self._items[index], canceled=False)

        elif data.action in ("prev", "next"):
          page = int(data.value) % self.pages_count
          if sent_msg is not None:
            await sent_msg.edit_text(
              text=self._prompt,
              reply_markup=InlineKeyboardMarkup(self._create_keyboard(uid, page, cancel_button)),
            )
          continue

        elif data.action == "noop":
          # Page number button: pressing it is simply ignored.
          continue

        raise WidgetError(f'Action "{data.action}" is not implemented.')

    finally:
      if sent_msg is not None:
        await sent_msg.delete()

  async def show_as_reply(self, reply_to_message: Message, cancel_button: bool = True) -> Result:
    return await self._show(None, cancel_button, reply_to_message)

  async def show(self, chat_id: int | str, cancel_button: bool = True) -> Result:
    return await self._show(chat_id, cancel_button)
