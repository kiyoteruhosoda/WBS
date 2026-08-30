import pytest

from src.domain.exceptions import AccessDeniedError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy

ISSUER = "https://idp.example.com/realms/wbs"


def _claims(**overrides) -> IdentityClaims:
    kwargs = {
        "identity": FederatedIdentity(issuer=ISSUER, subject="abc"),
        "email": "taro@example.com",
        "email_verified": True,
    }
    kwargs.update(overrides)
    return IdentityClaims(**kwargs)


def test_verified_email_is_required_by_default() -> None:
    with pytest.raises(AccessDeniedError):
        ProvisioningPolicy().ensure_allowed(_claims(email_verified=False))


def test_allowed_domains_shut_out_everyone_else() -> None:
    policy = ProvisioningPolicy(allowed_email_domains=("example.com",))
    policy.ensure_allowed(_claims(email="taro@example.com"))
    with pytest.raises(AccessDeniedError):
        policy.ensure_allowed(_claims(email="attacker@evil.example"))


def test_domain_comparison_ignores_case() -> None:
    policy = ProvisioningPolicy(allowed_email_domains=("example.com",))
    policy.ensure_allowed(_claims(email="Taro@Example.COM"))


def test_a_subdomain_is_not_the_allowed_domain() -> None:
    policy = ProvisioningPolicy(allowed_email_domains=("example.com",))
    with pytest.raises(AccessDeniedError):
        policy.ensure_allowed(_claims(email="taro@evil.example.com"))


def test_policy_without_email_cannot_be_applied() -> None:
    with pytest.raises(AccessDeniedError):
        ProvisioningPolicy().ensure_allowed(_claims(email=None, email_verified=True))


def test_open_policy_lets_an_emailless_identity_through() -> None:
    policy = ProvisioningPolicy(require_verified_email=False)
    policy.ensure_allowed(_claims(email=None, email_verified=False))


def test_provisioning_can_be_switched_off() -> None:
    with pytest.raises(AccessDeniedError):
        ProvisioningPolicy(auto_provision=False).ensure_can_provision(_claims())


def test_provisioning_needs_an_email_address() -> None:
    with pytest.raises(AccessDeniedError):
        ProvisioningPolicy().ensure_can_provision(_claims(email=None))
