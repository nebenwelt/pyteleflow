from collections.abc import Sequence

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import filters

from ..errors import WidgetError, UnexpectedError
from .._flow import Context


type Button = str | KeyboardButton


class Menu:
  MAX_BUTTONS_VERTICAL = 300

  def __init__(
    self,
    ctx: Context,
    chat_id: int,
    items: Sequence[Button] | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ):
    self._ctx: Context = ctx
    self._chat_id: int = chat_id
    self._items: Sequence[Button] | None = items
    self._prompt: str | None = prompt
    self._parse_mode = parse_mode

  def _create_keyboard(self) -> ReplyKeyboardMarkup:
    keyboard = []
    for item in self._items:
      keyboard.append([item])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

  def _check_items(self, items: Sequence[Button] | None):
    if items is None:
      raise WidgetError("items is None")
    elif len(items) == 0:
      raise WidgetError("Menu items is empty")
    elif len(items) > self.MAX_BUTTONS_VERTICAL:
      raise WidgetError(f"Too many items: {len(items)} (maximum is {self.MAX_BUTTONS_VERTICAL}).")

  async def show(
    self,
    items: Sequence[Button] | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ):
    self._items = items or self._items
    self._parse_mode = parse_mode or self._parse_mode
    self._check_items(self._items)

    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt or self._prompt,
      reply_markup=self._create_keyboard(),
      parse_mode=self._parse_mode,
    )
    return self

  async def result(self) -> str:
    self._check_items(self._items)

    _items = [i if isinstance(i, str) else i.text for i in self._items]

    msg = await self._ctx.message(filters.Text(_items))
    if msg.text is None:
      raise UnexpectedError("Message.text is None")
    else:
      return msg.text

  async def remove(self, prompt: str):
    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt,
      reply_markup=ReplyKeyboardRemove(),
    )
