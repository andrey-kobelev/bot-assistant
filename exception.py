
class NotAuthenticatedError(Exception):
    def __init__(self, message):
        super().__init__(message)


class APIAnswerError(Exception):
    def __init__(self, message):
        super().__init__(message)


class UnknownAPIAnswerError(Exception):
    def __init__(self, message):
        super().__init__(message)


class StatusError(ValueError):
    def __init__(self, message):
        super().__init__(message)
