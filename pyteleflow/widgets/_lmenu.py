import copy
import itertools

from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import filters

from ..errors import WidgetError, UnexpectedError
from .. import Context
from . import ButtonLayout, Button


class LMenu:
  """Advanced menu with a button layout.

  Example:

    panel_layout = [
      ["✏️", "📁", "⏰", "📺"],
      [Button("Admin", style="primary"), "Rules"],
      ["Users", "Setting"],
      [Button("Cancel", style="danger")]
    ]
    menu = LMenu(layout = panel_layout, ...)
    result = await menu.show(...)

  """

  def __init__(
    self,
    ctx: Context,
    chat_id: int,
    layout: ButtonLayout | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ):
    self._ctx: Context = ctx
    self._chat_id: int = chat_id
    self._layout: ButtonLayout | None = layout
    self._prompt: str | None = prompt
    self._parse_mode = parse_mode

  def _create_keyboard(self) -> ReplyKeyboardMarkup:
    keyboard: list[list] = copy.deepcopy(self._layout)

    for i in range(len(keyboard)):
      for j in range(len(keyboard[i])):
        if isinstance(keyboard[i][j], Button):
          _btn = keyboard[i][j]
          keyboard[i][j] = KeyboardButton(text=_btn.text, style=_btn.style)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

  def _check_layout(self, layout: ButtonLayout | None):
    if layout is None:
      raise WidgetError("layout is None")
    elif len(layout) == 0:
      raise WidgetError("Menu layout is empty")

  async def show(
    self,
    layout: ButtonLayout | None = None,
    prompt: str | None = None,
    parse_mode: ParseMode | None = None,
  ) -> str:
    """ Show the menu and wait for the button click result.

      Returns:
        Text of the clicked button
    """

    self._layout = layout or self._layout
    self._parse_mode = parse_mode or self._parse_mode
    self._check_layout(self._layout)

    await self._ctx.bot.send_message(
      chat_id=self._chat_id,
      text=prompt or self._prompt,
      reply_markup=self._create_keyboard(),
      parse_mode=self._parse_mode,
    )

    # Waiting for a button click
    strings = [str(i) for i in itertools.chain.from_iterable(self._layout)]

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
