from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import filters

from .._flow import Context
from ..errors import UnexpectedError, WidgetError
from ._common import Button, ButtonLayout


class LMenu:
  """Advanced menu with a button layout.

  Example:

    panel_layout = [
      ["✏️", "📁", "⏰", "📺"],
      [Button("Admin", style="primary"), "Rules"],
      ["Users", "Setting"],
      [Button("Cancel", style="danger")]
    ]
    menu = LMenu(ctx=ctx, chat_id=chat_id)
    result = await menu.show(layout=panel_layout, prompt="Choose")

  """

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

  def _create_keyboard(self, layout: ButtonLayout) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    for row in layout:
      keyboard_row: list[KeyboardButton] = []
      for item in row:
        if isinstance(item, str):
          keyboard_row.append(KeyboardButton(text=item))
        elif isinstance(item, Button):
          keyboard_row.append(KeyboardButton(text=item.text, style=item.style))
        else:
          raise WidgetError("item must be of type str or Button")

      keyboard.append(keyboard_row)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

  def _check_layout(self, layout: ButtonLayout) -> None:
    if len(layout) == 0:
      raise WidgetError("Menu layout is empty")

  async def show(
    self,
    layout: ButtonLayout,
    prompt: str,
    parse_mode: ParseMode | None = None,
    no_wait: bool = False,
  ) -> str | None:
    """Show the menu.

    Waits for the button click result unless `no_wait` is True.

    Args:
      layout: Rows of buttons of the menu.
      prompt: Message text shown above the keyboard.
      parse_mode: Parse mode used for `prompt`.
      no_wait: If True, return immediately after showing the menu without waiting
        for a button click.

    Returns:
      Text of the clicked button, or None if `no_wait` is True.

    Raises:
      WidgetError: If `layout` is empty.
    """
    self._check_layout(layout)

    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt,
      reply_markup=self._create_keyboard(layout),
      parse_mode=parse_mode,
    )
    self._is_shown = True

    if no_wait:
      return None

    # Waiting for a button click
    strings = [str(item) for row in layout for item in row]

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
    if self._is_shown:
      await self._ctx.bot.send_message(
        chat_id=self._chat_id,
        text=prompt,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=parse_mode,
      )
      self._is_shown = False
