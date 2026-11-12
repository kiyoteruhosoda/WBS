"""Value object pointing at a person on an external IdP."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import ValidationError


@dataclass(frozen=True)
class FederatedIdentity:
    """The "issuer + subject" pair issued by the IdP.

    In OIDC a user is unique not by ``sub`` alone but by the ``(iss, sub)`` pair
    (``sub`` is unique only within its issuer). Email addresses can be changed or reassigned
    on the IdP side, so they are not used as the matching key.

    ⚠ **``issuer`` is held with the trailing ``/`` removed.** If the same IdP had two
    spellings, logout notices and periodic reconciliation could not find rows written at sign-in.
    The discovery document (``OidcDiscovery.issuer``) keeps exactly what the IdP declared
    — because the ID token's ``iss`` is matched **exactly**.
    """

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if not self.issuer.strip():
            raise ValidationError("issuer must not be empty")
        if not self.subject.strip():
            raise ValidationError("subject must not be empty")
        # Normalize the issuer spelling to one form here. The discovery document must keep what the IdP declared
        # (may include a trailing `/`), but **the addresses we store** must be
        # normalized. Otherwise logout notices and periodic reconciliation find
        # no rows at all, and **nothing gets stopped, with no exception and no log**.
        object.__setattr__(self, "issuer", self.issuer.strip().rstrip("/"))
        object.__setattr__(self, "subject", self.subject.strip())
