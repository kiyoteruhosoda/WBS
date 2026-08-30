import pytest

from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims

IDENTITY = FederatedIdentity(issuer="https://idp.example.com", subject="abc")


def test_display_name_falls_back_through_the_available_claims() -> None:
    assert IdentityClaims(identity=IDENTITY, display_name="Taro").resolved_display_name() == "Taro"
    assert IdentityClaims(identity=IDENTITY, preferred_username="taro").resolved_display_name() == "taro"
    assert IdentityClaims(identity=IDENTITY, email="t@example.com").resolved_display_name() == "t@example.com"
    # 何も無ければ sub。名前無しの利用者を作れないと、ログイン自体が通らなくなる。
    assert IdentityClaims(identity=IDENTITY).resolved_display_name() == "abc"


def test_blank_names_are_skipped() -> None:
    claims = IdentityClaims(identity=IDENTITY, display_name="   ", preferred_username="taro")
    assert claims.resolved_display_name() == "taro"


def test_email_domain_is_lowercased() -> None:
    assert IdentityClaims(identity=IDENTITY, email="Taro@Example.COM").email_domain == "example.com"


def test_malformed_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IdentityClaims(identity=IDENTITY, email="not-an-email")
