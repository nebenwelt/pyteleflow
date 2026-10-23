class PyteleflowError(Exception):
  pass


class FlowAlreadySpawned(PyteleflowError):
  pass


class FlowKeyError(PyteleflowError):
  pass


class FlowCancellationFailed(PyteleflowError):
  pass


class UnexpectedError(PyteleflowError):
  pass


class WidgetError(PyteleflowError): ...
