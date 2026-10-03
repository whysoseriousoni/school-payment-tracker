"""Exceptions whose messages are safe to show to the user."""


class ServiceError(Exception):
    """Base class: the message explains what to fix."""


class NotFoundError(ServiceError):
    pass


class BusinessRuleError(ServiceError):
    pass


class AuthorizationError(ServiceError):
    pass
