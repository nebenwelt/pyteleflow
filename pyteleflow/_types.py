from typing import NamedTuple


class FlowKey(NamedTuple):
  chat_id: int | None
  user_id: int | None
  thread_id: int | None
  update_id: int | None
