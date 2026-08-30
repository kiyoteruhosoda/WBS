import pytest

from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity

KEYCLOAK = "https://idp.example.com/realms/wbs"
ENTRA = "https://login.microsoftonline.com/tenant/v2.0"


def _user(**overrides) -> UserAccount:
    kwargs = {"id": 1, "email": "taro@example.com", "display_name": "Taro"}
    kwargs.update(overrides)
    return UserAccount(**kwargs)


def test_linking_the_same_identity_twice_is_a_no_op() -> None:
    user = _user()
    identity = FederatedIdentity(issuer=KEYCLOAK, subject="abc")
    user.link_identity(identity)
    user.link_identity(identity)
    assert user.identities == [identity]


def test_a_second_subject_on_the_same_issuer_is_rejected() -> None:
    user = _user()
    user.link_identity(FederatedIdentity(issuer=KEYCLOAK, subject="abc"))
    with pytest.raises(ValidationError):
        user.link_identity(FederatedIdentity(issuer=KEYCLOAK, subject="different"))


def test_identities_on_different_issuers_can_coexist() -> None:
    user = _user()
    user.link_identity(FederatedIdentity(issuer=KEYCLOAK, subject="abc"))
    user.link_identity(FederatedIdentity(issuer=ENTRA, subject="abc"))
    assert len(user.identities) == 2


def test_apply_profile_reports_whether_anything_changed() -> None:
    user = _user()
    assert user.apply_profile(email="taro@example.com", display_name="Taro") is False
    assert user.apply_profile(email="taro@example.co.jp", display_name="Taro") is True
    assert user.email == "taro@example.co.jp"


def test_apply_profile_keeps_app_side_preferences() -> None:
    user = _user(timezone="Europe/Berlin", language="en")
    user.apply_profile(email="taro@example.com", display_name="Taro Yamada")
    # タイムゾーンと言語は設定画面で選ぶもの。IdP のログインで戻されては困る。
    assert user.timezone == "Europe/Berlin"
    assert user.language == "en"


def test_apply_profile_ignores_missing_idp_values() -> None:
    user = _user()
    user.apply_profile(email=None, display_name=None)
    assert user.email == "taro@example.com"
    assert user.display_name == "Taro"


def test_deactivated_user_cannot_sign_in() -> None:
    with pytest.raises(ValidationError):
        _user(is_active=False).ensure_can_sign_in()


@pytest.mark.parametrize("issuer,subject", [("", "abc"), (KEYCLOAK, ""), ("  ", "abc")])
def test_identity_requires_both_parts(issuer: str, subject: str) -> None:
    with pytest.raises(ValidationError):
        FederatedIdentity(issuer=issuer, subject=subject)
