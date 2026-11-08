from collections.abc import Sequence

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import filters

from .._flow import Context
from ..errors import UnexpectedError, WidgetError
from ._common import Button


class Menu:
  """Simple menu with a single vertical column of buttons."""

  MAX_BUTTONS_VERTICAL: int = 300

  def __init__(self, ctx: Context, chat_id: int | str):
    """
    Args:
      ctx: Flow context.
      chat_id: Chat where the widget is shown.
    """
    self._ctx: Context = ctx
    self._chat_id: int | str = chat_id

    # Whether the menu keyboard is currently shown by this widget.
    self._is_shown: bool = False

  def _create_keyboard(self, items: Sequence[str | Button]) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    for item in items:
      if isinstance(item, str):
        btn = KeyboardButton(text=item)
      elif isinstance(item, Button):
        btn = KeyboardButton(text=item.text, style=item.style)
      else:
        raise WidgetError("item must be of type str or Button")

      keyboard.append([btn])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

  def _check_items(self, items: Sequence[str | Button]) -> None:
    if len(items) == 0:
      raise WidgetError("Menu items are empty")
    elif len(items) > self.MAX_BUTTONS_VERTICAL:
      raise WidgetError(f"Too many items: {len(items)} (maximum is {self.MAX_BUTTONS_VERTICAL}).")

  async def show(
    self,
    items: Sequence[str | Button],
    prompt: str,
    parse_mode: ParseMode | None = None,
  ) -> str:
    """Show the menu and wait for the button click result.

    Args:
      items: Buttons of the menu. Each item occupies its own row.
      prompt: Message text shown above the keyboard.
      parse_mode: Parse mode used for `prompt`.

    Returns:
      Text of the clicked button.

    Raises:
      WidgetError: If `items` is empty or contains too many buttons.
    """
    self._check_items(items)

    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt,
      reply_markup=self._create_keyboard(items),
      parse_mode=parse_mode,
    )
    self._is_shown = True

    # Waiting for a button click
    strings = [str(item) for item in items]

    msg = await self._ctx.message(filters.Text(strings))
    if msg.text is None:
      raise UnexpectedError("Message.text is None")
    else:
      return msg.text

  async def remove(self, prompt: str, parse_mode: ParseMode | None = None) -> None:
    """Hide the menu keyboard if it was shown by `show()`.

    Does nothing if the menu keyboard is not currently shown.

    Args:
      prompt: Message text sent together with the keyboard removal.
      parse_mode: Parse mode used for `prompt`.
    """
    if  self._is_shown:
      await self._ctx.bot.send_message(
        chat_id=self._chat_id,
        text=prompt,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=parse_mode,
      )
      self._is_shown = False
