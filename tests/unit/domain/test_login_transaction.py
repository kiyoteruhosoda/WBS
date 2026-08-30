from datetime import datetime, timedelta

import pytest

from src.domain.entities.login_transaction import LoginTransaction
from src.domain.exceptions import ValidationError
from src.domain.value_objects.redirect_target import RedirectTarget

NOW = datetime(2026, 8, 30, 12, 0, 0)


def _issue(**overrides) -> LoginTransaction:
    kwargs = {
        "state": "s",
        "nonce": "n",
        "code_verifier": "v",
        "redirect_target": RedirectTarget.parse("/tasks"),
        "now": NOW,
    }
    kwargs.update(overrides)
    return LoginTransaction.issue(**kwargs)


def test_expires_after_the_ttl() -> None:
    transaction = _issue(ttl=timedelta(minutes=10))
    assert not transaction.is_expired(NOW + timedelta(minutes=9))
    assert transaction.is_expired(NOW + timedelta(minutes=10))


@pytest.mark.parametrize("missing", ["state", "nonce", "code_verifier"])
def test_all_three_secrets_are_required(missing: str) -> None:
    with pytest.raises(ValidationError):
        _issue(**{missing: ""})
