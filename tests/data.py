from telegram import Chat, User, Message, Update, MessageOriginUser, CallbackQuery
from telegram.constants import ChatType
import datetime as dtm


def user(user_id=0, username="test_user", is_bot=False):
  return User(user_id, first_name=username, username=username, is_bot=is_bot)


def chat(chat_id: int = 0, chat_type: ChatType = ChatType.PRIVATE):
  return Chat(chat_id, chat_type)


def message(
  text: str = "Test text message",
  from_user: User | None = None,
  _chat: Chat | None = None,
  message_id: int = 0,
  message_thread_id: int | None = None,
):
  _chat = _chat or chat()
  return Message(
    message_id,
    dtm.datetime.now(dtm.UTC),
    _chat,
    from_user=from_user or user(),
    sender_chat=_chat,
    is_topic_message=message_thread_id is not None,
    message_thread_id=message_thread_id,
    text=text,
  )


def callback_query(_id: str, from_user: User | None = None, data: str | None = None):
  return CallbackQuery(
    id=_id,
    from_user=from_user or user(),
    chat_instance="test_chat_instance",
    data=data,
  )


def update(
  update_id=0, _message: Message | None = None, _callback_query: CallbackQuery | None = None
):
  return Update(update_id, message=_message or message(), callback_query=_callback_query)
