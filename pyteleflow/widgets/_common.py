from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass
class Button:
  text: str

  # danger (red), success (green), “primary” (blue), None (default)
  style: Literal["danger", "success", "primary"] | None

  def __str__(self):
    return self.text


type ButtonLayout = list[list[str | Button]]
