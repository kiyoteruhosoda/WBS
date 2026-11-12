"""Decide whether a suspension notice "holds up as a logout notice".

Verification of signature, issuer, audience and expiry is the infrastructure layer's job (a JWT matter). What this looks at is
**the other 4 things**, and dropping any of them does real harm.
"""

import pytest

from src.domain.value_objects.logout_notice import (
    LOGOUT_EVENT,
    InvalidLogoutTokenError,
    LogoutNotice,
)

ISSUER = "https://idp.example.com/realms/wbs"


def claims(**overrides):
    base = {"sub": "taro", "jti": "delivery-1", "events": {LOGOUT_EVENT: {}}}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def test_a_notice_with_a_subject_addresses_that_person() -> None:
    notice = LogoutNotice.from_claims(claims(), issuer=ISSUER)
    assert notice.identity is not None
    assert (notice.identity.issuer, notice.identity.subject) == (ISSUER, "taro")
    assert notice.session_id is None
    assert notice.scope == "subject"


def test_a_notice_with_a_sid_addresses_one_login() -> None:
    notice = LogoutNotice.from_claims(claims(sid="taro-session"), issuer=ISSUER)
    assert notice.session_id == "taro-session"
    assert notice.scope == "session"


def test_a_sid_alone_is_a_valid_address() -> None:
    """The spec says either ``sub`` or ``sid`` is enough (§2.6)."""
    notice = LogoutNotice.from_claims(claims(sub=None, sid="taro-session"), issuer=ISSUER)
    assert notice.identity is None
    assert notice.session_id == "taro-session"


def test_an_id_token_is_not_a_logout_notice() -> None:
    """⚠ **Do not accept anything carrying a ``nonce``** (the spec says MUST NOT).

    An ID token and a ``logout_token`` share the signing key, issuer and audience, so **this one point
    alone** tells them apart. Dropping it would let anyone end someone else's session
    just by sending back a legitimately received ID token.
    """
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims(nonce="n-1"), issuer=ISSUER)


@pytest.mark.parametrize(
    "broken",
    [
        {"events": None},  # no events = not a logout notice
        {"events": {"http://example.com/other": {}}},  # a different event
        {"jti": None},  # no key to reject replays
        {"sub": None},  # neither sub nor sid (cannot tell whom to stop)
    ],
    ids=["no-events", "other-event", "no-jti", "no-address"],
)
def test_a_notice_that_does_not_stand_up_is_refused(broken) -> None:
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims(**broken), issuer=ISSUER)


def test_the_issuer_spelling_comes_from_the_caller() -> None:
    """⚠ The audience issuer is held in **the spelling we kept locally** (the trailing ``/`` is dropped)."""
    notice = LogoutNotice.from_claims(claims(), issuer=f"{ISSUER}/")
    assert notice.identity is not None
    assert notice.identity.issuer == ISSUER
