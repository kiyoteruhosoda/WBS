"""Claims identifying the person, taken from a verified ID token."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity


@dataclass(frozen=True)
class IdentityClaims:
    """Identity received from the IdP.

    Verification of the signature, ``iss``, ``aud``, ``exp`` and ``nonce`` is done in the infrastructure layer (IdP adapter)
    before the value comes here. This value object only checks "whether it is enough for the app
    to create / match the person".
    """

    identity: FederatedIdentity
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    preferred_username: str | None = None
    #: The ID token's ``sid`` (IdP-side sign-in session). Some IdPs do not issue it, so
    #: it may be ``None`` — with such an IdP sign-ins can only be stopped **per user**.
    session_id: str | None = None

    def __post_init__(self) -> None:
        if self.email is not None and "@" not in self.email:
            raise ValidationError(f"Invalid email in ID token: {self.email}")

    @property
    def issuer(self) -> str:
        return self.identity.issuer

    @property
    def subject(self) -> str:
        return self.identity.subject

    @property
    def email_domain(self) -> str | None:
        """Domain part of the email address (lowercase). Used to filter by affiliation."""
        if self.email is None:
            return None
        return self.email.rsplit("@", 1)[1].lower()

    def resolved_display_name(self) -> str:
        """Name shown on screen. The IdP may not return name, so fall back in order."""
        for candidate in (self.display_name, self.preferred_username, self.email, self.subject):
            if candidate and candidate.strip():
                return candidate.strip()
        return self.subject
