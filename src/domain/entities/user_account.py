"""A user within the app, linked to a person on the IdP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity

DEFAULT_TIMEZONE = "Asia/Tokyo"
DEFAULT_LANGUAGE = "ja"


@dataclass
class UserAccount:
    id: int | None
    email: str
    display_name: str
    timezone: str = DEFAULT_TIMEZONE
    language: str = DEFAULT_LANGUAGE
    is_active: bool = True
    #: Whether they can create top-level projects (ADR-0065). Granted/revoked with scripts/grant_project_creator.py
    can_create_projects: bool = False
    identities: list[FederatedIdentity] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def has_identity(self, identity: FederatedIdentity) -> bool:
        return identity in self.identities

    def link_identity(self, identity: FederatedIdentity) -> None:
        """Link a person on the IdP to this user.

        Adding a different ``sub`` from the same issuer is refused. Belonging to several IdPs (an in-house IdP
        and a partner IdP, etc.) is allowed, but two identities for one person at the same issuer would show
        the same screen in either session and cause mix-ups.
        """
        if self.has_identity(identity):
            return
        conflicting = next((i for i in self.identities if i.issuer == identity.issuer), None)
        if conflicting is not None:
            raise ValidationError(
                f"User is already linked to another subject on issuer {identity.issuer}"
            )
        self.identities.append(identity)

    def apply_profile(self, *, email: str | None, display_name: str | None) -> bool:
        """Take in profile changes from the IdP. True if anything changed.

        Time zone and language are chosen in the app's settings screen, so they are not overwritten.
        """
        changed = False
        if email and email != self.email:
            self.email = email
            changed = True
        if display_name and display_name != self.display_name:
            self.display_name = display_name
            changed = True
        return changed

    def ensure_can_sign_in(self) -> None:
        if not self.is_active:
            raise ValidationError(f"User account is deactivated: {self.email}")
