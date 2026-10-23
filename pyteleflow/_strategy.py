from abc import ABC, abstractmethod

from telegram import Update
from telegram.constants import ChatType

from ._types import FlowKey
from .errors import FlowKeyError


class BaseConcurrencyStrategy(ABC):
  def __init__(self, name: str):
    self._name = name

  @abstractmethod
  def get_flow_key(self, update: Update) -> FlowKey:
    pass

  @property
  def name(self) -> str:
    return self._name


class Chat(BaseConcurrencyStrategy):
  def get_flow_key(self, update: Update) -> FlowKey:
    u = update
    chat_id = u.effective_chat.id if u.effective_chat is not None else None
    update_id = u.update_id if chat_id is None else None

    return FlowKey(chat_id, None, None, update_id)


class UserInChat(BaseConcurrencyStrategy):
  def get_flow_key(self, update: Update) -> FlowKey:
    u = update
    chat_id = u.effective_chat.id if u.effective_chat is not None else None
    user_id = u.effective_user.id if u.effective_user is not None else None
    update_id = None

    return FlowKey(chat_id, user_id, None, update_id)


class UserInGlobal(BaseConcurrencyStrategy):
  def get_flow_key(self, update: Update) -> FlowKey:
    u = update
    user_id = u.effective_user.id if u.effective_user is not None else None
    update_id = None

    return FlowKey(None, user_id, None, update_id)


class ThreadInChat(BaseConcurrencyStrategy):
  def get_flow_key(self, update: Update) -> FlowKey:
    u = update
    chat_id = u.effective_chat.id if u.effective_chat is not None else None

    if u.effective_message is None or u.effective_chat is None:
      raise FlowKeyError(
        f"For the {self.name} spawn strategy, update.effective_message and update.effective_chat must not be None."
      )

    if u.effective_chat.type == ChatType.PRIVATE:
      return FlowKey(chat_id, None, None, None)
    elif u.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
      thread_id = u.effective_message.message_thread_id or u.effective_message.id
      return FlowKey(chat_id, None, thread_id, None)

    else:
      raise FlowKeyError(
        f"The {self.name} spawn strategy can only be used with chats of type PRIVATE, GROUP, or SUPERGROUP."
      )


class SingleFlow(BaseConcurrencyStrategy):
  def get_flow_key(self, update: Update) -> FlowKey:
    return FlowKey(None, None, None, None)


class ConcurrencyStrategy:
  """
  Spawn a separate Flow for each chat.
  All updates from the same chat are processed by the same Flow instance.
  """

  CHAT = Chat(name="CHAT")

  """
  Spawn a separate Flow for each user across all chats.
  All updates from the same user are processed by the same Flow instance,
  regardless of which chat they belong to.
  """
  USER_IN_GLOBAL = UserInGlobal(name="USER_IN_GLOBAL")

  """
  Spawn a separate Flow for each user within each chat.
  All updates from the same user in the same chat are processed by the same
  Flow instance, regardless of the thread.

  WARNING: This strategy may spawn a large number of Flows if the Spawn trigger
  filter is too broad.
  """
  USER_IN_CHAT = UserInChat(name="USER_IN_CHAT")

  """
  Spawn a separate Flow for each thread within a chat.
  All updates from the same thread are processed by the same Flow instance,
  regardless of which user sent them.
  Threads are supported in group chats and supergroups. Private chats have
  a single thread.

  NOTE: Updates without an effective message are ignored by this strategy.

  WARNING: This strategy may spawn a large number of Flows if the Spawn trigger
  filter is too broad.
  """
  THREAD_IN_CHAT = ThreadInChat(name="THREAD_IN_CHAT")

  """
  Process all incoming updates using a single Flow instance, without separating
  them by chat, user, or thread.
  """
  SINGLE_FLOW = SingleFlow(name="SINGLE_FLOW")
