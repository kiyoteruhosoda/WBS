from __future__ import annotations


class DomainException(Exception):
    pass

class NotFoundError(DomainException):
    def __init__(self, resource: str, id: int | str) -> None:
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} with id={id} not found")

class ValidationError(DomainException):
    pass

class ConflictError(DomainException):
    pass

class CyclicDependencyError(ConflictError):
    def __init__(self) -> None:
        super().__init__("Adding this dependency would create a cycle")

class InvalidStatusTransitionError(ValidationError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Invalid status transition: {from_status} -> {to_status}")
