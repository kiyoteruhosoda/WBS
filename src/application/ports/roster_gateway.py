"""The port that asks the IdP "who may use this app right now". Implemented in the infrastructure layer."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.roster import Roster


class RosterGateway(ABC):
    @abstractmethod
    def fetch(self, *, issuer: str, subjects: tuple[str, ...]) -> Roster:
        """Ask by name.

        ⚠ **A candidate list is not enough.** "Not there (gone)" is only known once we
        ask by naming them.

        ⚠ **If it cannot be fetched, stop with an exception.** Returning an empty roster makes the caller
        read it as "everyone left" (``IdentityProviderUnavailableError`` /
        ``MachineNotBoundToApplicationError``).
        """


__all__ = ["RosterGateway"]
