
class NotAuthenticatedError(Exception):
    def __init__(self, message):
        super().__init__(message)


class FromDateFormatError(Exception):
    def __init__(self, message):
        super().__init__(message)


class EmptyHomeworksListException(Exception):
    def __init__(self, message):
        super().__init__(message)


class EndpointError(Exception):
    def __init__(self, message):
        super().__init__(message)


class SendMessageError(Exception):
    def __init__(self, message):
        super().__init__(message)


class ApiKeysError(KeyError):
    def __init__(self, message):
        super().__init__(message)


class NoNewStatus(Exception):
    def __init__(self, message):
        super().__init__(message)


class InvalidStatusError(Exception):
    def __init__(self, message):
        super().__init__(message)
