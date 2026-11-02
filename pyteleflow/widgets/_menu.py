import logging
from collections.abc import Sequence

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import filters

from .._flow import Context
from ..errors import UnexpectedError, WidgetError
from ._common import Button

_logger = logging.getLogger(__name__)


class Menu:
  """Simple menu with a single vertical column of buttons."""

  MAX_BUTTONS_VERTICAL = 300

  def __init__(
    self,
    ctx: Context,
    chat_id: int,
    items: Sequence[str | Button] | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ):
    self._ctx: Context = ctx
    self._chat_id: int = chat_id
    self._items: Sequence[str | Button] | None = items
    self._prompt: str | None = prompt
    self._parse_mode = parse_mode

  def _create_keyboard(self) -> ReplyKeyboardMarkup:
    keyboard = []
    for item in self._items:
      if isinstance(item, str):
        btn = KeyboardButton(text=item)
      elif isinstance(item, Button):
        btn = KeyboardButton(text=item.text, style=item.style)
      else:
        raise WidgetError("item must be of type str or Button")

      keyboard.append([btn])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

  def _check_items(self, items: Sequence[str | Button] | None):
    if items is None:
      raise WidgetError("items is None")
    elif len(items) == 0:
      raise WidgetError("Menu items is empty")
    elif len(items) > self.MAX_BUTTONS_VERTICAL:
      raise WidgetError(f"Too many items: {len(items)} (maximum is {self.MAX_BUTTONS_VERTICAL}).")

  async def show(
    self,
    items: Sequence[str | Button] | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ) -> str:
    """Show the menu and wait for the button click result.

    Returns:
      Text of the clicked button
    """

    self._items = items or self._items
    self._parse_mode = parse_mode or self._parse_mode
    self._check_items(self._items)

    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt or self._prompt,
      reply_markup=self._create_keyboard(),
      parse_mode=self._parse_mode,
    )

    # Waiting for a button click
    strings = [str(i) for i in self._items]

    msg = await self._ctx.message(filters.Text(strings))
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
