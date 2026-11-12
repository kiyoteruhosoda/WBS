"""Rules for whether a person verified by the IdP may enter this app."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import AccessDeniedError
from src.domain.value_objects.identity_claims import IdentityClaims


@dataclass(frozen=True)
class ProvisioningPolicy:
    """Whether to create users automatically on first sign-in, and whom to let in.

    Passing authentication at the IdP and being allowed to use this app are different things. With a multi-tenant IdP
    (such as the Microsoft Entra ID common endpoint), letting everyone through would mean
    "anyone can get in because authentication succeeds".
    """

    auto_provision: bool = True
    allowed_email_domains: tuple[str, ...] = ()
    require_verified_email: bool = True
    #: Whether a not-yet-linked person may be merged into **an existing user with the same email address**.
    #:
    #: ⚠ **Not merged by default.** Even if ``email_verified`` is true, it means "the IdP confirmed it can
    #: reach that address", not "this user is that person". Leaving the merge path
    #: open would let anyone who can claim someone's address on the IdP into that existing account in this app
    #: (= their past work records). Linking happens only when ``(iss, sub)`` already exists.
    link_by_email: bool = False

    def ensure_allowed(self, claims: IdentityClaims) -> None:
        needs_email = bool(self.allowed_email_domains) or self.require_verified_email
        if needs_email and claims.email is None:
            raise AccessDeniedError(
                "IdP did not provide an email address; cannot apply the sign-in policy"
            )
        if self.require_verified_email and not claims.email_verified:
            raise AccessDeniedError(f"Email address is not verified by the IdP: {claims.email}")
        if self.allowed_email_domains and claims.email_domain not in self.allowed_email_domains:
            raise AccessDeniedError(f"Email domain is not allowed: {claims.email}")

    def ensure_can_link_by_email(self, claims: IdentityClaims) -> None:
        """Check whether merging into an existing user by email address is allowed.

        ⚠ **Both gates must pass.** Even if merging is enabled, addresses
        the IdP has not verified are not merged.
        """
        if not self.link_by_email:
            raise AccessDeniedError(
                "This account is not linked to an identity provider subject; "
                "linking by email address is disabled (OIDC_LINK_BY_EMAIL)"
            )
        if not self.require_verified_email:
            raise AccessDeniedError(
                "Linking an existing account by email requires verified email addresses; "
                "enable OIDC_REQUIRE_VERIFIED_EMAIL"
            )

    def ensure_can_provision(self, claims: IdentityClaims) -> None:
        """Whether a new, unregistered person may be created."""
        if not self.auto_provision:
            raise AccessDeniedError(
                "This account is not registered and automatic provisioning is disabled"
            )
        if claims.email is None:
            raise AccessDeniedError("IdP did not provide an email address; cannot create a user")
