from abc import ABC, abstractmethod

from telegram import Update


class Middleware(ABC):
  @abstractmethod
  def __call__(self, update: Update | None) -> Update | None:
    """To interrupt Update processing, return `None`."""
    return update


class AsyncMiddleware(ABC):
  @abstractmethod
  async def __call__(self, update: Update | None) -> Update | None:
    """To interrupt Update processing, return `None`."""
    return update
