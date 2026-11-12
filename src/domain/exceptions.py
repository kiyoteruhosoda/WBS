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

class AuthenticationError(DomainException):
    """The person cannot be verified (not signed in, session expired, bad IdP response)."""

class AccessDeniedError(DomainException):
    """The person was verified but is not allowed to use this app (disabled, outside the organization)."""

class IdentityProviderUnavailableError(DomainException):
    """Could not ask the IdP (unreachable, 5xx, unreadable response).

    ⚠ **Do not confuse this with "nobody is there".** Treating it as an empty roster would stop
    everyone just because the IdP is having trouble. When the IdP cannot be asked, change nothing and skip.
    """

class MachineNotBoundToApplicationError(DomainException):
    """The service account that identified itself is not yet linked to the app on the IdP side.

    ⚠ **Not a failure but pending setup.** Every cycle comes here until it is linked, so do not warn.
    """

class ProjectCycleError(ConflictError):
    """Tried to move a project under itself or one of its descendants (doing so would leave the branch unreachable)."""

    def __init__(self) -> None:
        super().__init__("a project cannot be moved under itself or its own sub-project")

class ProjectNotEmptyError(ConflictError):
    """A project containing tasks, child projects or milestones is not deleted (use archiving)."""

    def __init__(self) -> None:
        super().__init__(
            "the project still has sub-projects, tasks or milestones; archive it or move them out first"
        )


class ProjectManagerRequiredError(AccessDeniedError):
    """Operations only admins can do (adding/removing members, deleting the top-level project or moving it under another). ADR-0055."""

    def __init__(self) -> None:
        super().__init__("only a manager of the top project can do this")


class ProjectCreatorRequiredError(AccessDeniedError):
    """Only people with the mark can create top-level projects (ADR-0065)."""

    def __init__(self) -> None:
        super().__init__("only people allowed to create projects can create a top project")


class LastProjectManagerError(ConflictError):
    """Removing the last admin or demoting them to member would leave nobody able to add or remove members (ADR-0055)."""

    def __init__(self) -> None:
        super().__init__("a top project needs at least one manager")
