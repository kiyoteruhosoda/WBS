"""SSO ログインの筋書きを、IdP も DB も使わずに確かめる。"""

from datetime import datetime, timedelta

import pytest

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.application.ports.secret_generator import SecretGenerator
from src.application.use_cases.authentication_use_cases import (
    SessionAuthenticationUseCases,
    SsoLoginUseCases,
)
from src.domain.entities.auth_session import AuthSession
from src.domain.entities.login_transaction import LoginTransaction
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import AccessDeniedError, AuthenticationError
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy

NOW = datetime(2026, 8, 30, 12, 0, 0)
ISSUER = "https://idp.example.com/realms/wbs"


class InMemoryUsers(UserAccountRepository):
    def __init__(self, users: list[UserAccount] | None = None) -> None:
        self.users = users or []
        self._next_id = max((u.id or 0) for u in self.users) + 1 if self.users else 1

    def find_by_id(self, user_id):
        return next((u for u in self.users if u.id == user_id), None)

    def find_by_identity(self, identity):
        return next((u for u in self.users if identity in u.identities), None)

    def find_by_email(self, email):
        return next((u for u in self.users if u.email == email), None)

    def save(self, user):
        if user.id is None:
            user.id = self._next_id
            self._next_id += 1
            self.users.append(user)
        return user


class InMemorySessions(AuthSessionRepository):
    def __init__(self) -> None:
        self.sessions: list[AuthSession] = []

    def add(self, session):
        session.id = len(self.sessions) + 1
        self.sessions.append(session)
        return session

    def find_by_token(self, token):
        return next((s for s in self.sessions if s.matches(token)), None)

    def update(self, session):
        return None

    def delete_by_token(self, token):
        self.sessions = [s for s in self.sessions if not s.matches(token)]

    def delete_expired(self, now):
        before = len(self.sessions)
        self.sessions = [s for s in self.sessions if not s.is_expired(now)]
        return before - len(self.sessions)


class InMemoryTransactions(LoginTransactionRepository):
    def __init__(self) -> None:
        self.transactions: list[LoginTransaction] = []

    def add(self, transaction):
        self.transactions.append(transaction)
        return transaction

    def consume(self, state):
        found = next((t for t in self.transactions if t.state == state), None)
        if found is not None:
            self.transactions.remove(found)
        return found

    def delete_expired(self, now):
        before = len(self.transactions)
        self.transactions = [t for t in self.transactions if not t.is_expired(now)]
        return before - len(self.transactions)


class CountingSecrets(SecretGenerator):
    """呼ぶたびに違う、しかし予測できる値を返す（検証を目で追えるように）。"""

    def __init__(self) -> None:
        self.count = 0

    def generate(self) -> str:
        self.count += 1
        return f"secret-{self.count}"


class FakeIdentityProvider(IdentityProvider):
    def __init__(self, claims: IdentityClaims | None = None) -> None:
        self._claims = claims or IdentityClaims(
            identity=FederatedIdentity(issuer=ISSUER, subject="abc"),
            email="taro@example.com",
            email_verified=True,
            display_name="Taro",
        )
        self.exchanged: list[tuple[str, str, str]] = []

    @property
    def display_name(self):
        return "Test IdP"

    def build_authorization_request(self, *, state, nonce, code_verifier):
        return AuthorizationRequest(
            authorization_url=f"{ISSUER}/auth?state={state}&nonce={nonce}",
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )

    def exchange_code(self, *, code, code_verifier, nonce):
        self.exchanged.append((code, code_verifier, nonce))
        return self._claims

    def build_end_session_url(self, *, post_logout_redirect_uri):
        return f"{ISSUER}/logout"


def build(idp=None, users=None, policy=None):
    users_repo = InMemoryUsers(users)
    sessions = InMemorySessions()
    transactions = InMemoryTransactions()
    sso = SsoLoginUseCases(
        identity_provider=idp or FakeIdentityProvider(),
        users=users_repo,
        sessions=sessions,
        transactions=transactions,
        secrets=CountingSecrets(),
        policy=policy or ProvisioningPolicy(),
    )
    session_auth = SessionAuthenticationUseCases(users=users_repo, sessions=sessions)
    return sso, session_auth, users_repo, sessions, transactions


def login(sso, *, code="auth-code", now=NOW, redirect_path=None):
    sso.start_login(redirect_path=redirect_path, now=now)
    return sso


# ── ログイン開始 ───────────────────────────────────────────────────────────
def test_start_login_remembers_state_nonce_and_verifier() -> None:
    sso, _, _, _, transactions = build()
    started = sso.start_login(redirect_path="/tasks", now=NOW)
    assert len(transactions.transactions) == 1
    transaction = transactions.transactions[0]
    assert transaction.state in started.authorization_url
    assert transaction.nonce in started.authorization_url
    # PKCE の verifier は IdP へ送る URL には出さない（challenge だけを預ける）
    assert transaction.code_verifier not in started.authorization_url


def test_start_login_keeps_the_requested_page() -> None:
    sso, _, _, _, transactions = build()
    sso.start_login(redirect_path="/gantt", now=NOW)
    assert transactions.transactions[0].redirect_target.path == "/gantt"


def test_start_login_drops_an_external_redirect() -> None:
    sso, _, _, _, transactions = build()
    sso.start_login(redirect_path="https://evil.example", now=NOW)
    assert transactions.transactions[0].redirect_target.path == "/"


def test_start_login_sweeps_expired_transactions() -> None:
    sso, _, _, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    sso.start_login(redirect_path=None, now=NOW + timedelta(hours=1))
    assert len(transactions.transactions) == 1


# ── コールバック ───────────────────────────────────────────────────────────
def test_completing_a_login_creates_the_user_and_a_session() -> None:
    sso, _, users, sessions, transactions = build()
    sso.start_login(redirect_path="/inbox", now=NOW)
    state = transactions.transactions[0].state

    completed = sso.complete_login(code="auth-code", state=state, now=NOW)

    assert completed.redirect_path == "/inbox"
    assert len(users.users) == 1
    assert users.users[0].email == "taro@example.com"
    assert users.users[0].identities == [FederatedIdentity(issuer=ISSUER, subject="abc")]
    assert len(sessions.sessions) == 1
    assert sessions.sessions[0].matches(completed.session_token)


def test_the_stored_verifier_and_nonce_are_handed_to_the_idp() -> None:
    idp = FakeIdentityProvider()
    sso, _, _, _, transactions = build(idp=idp)
    sso.start_login(redirect_path=None, now=NOW)
    transaction = transactions.transactions[0]

    sso.complete_login(code="auth-code", state=transaction.state, now=NOW)

    assert idp.exchanged == [("auth-code", transaction.code_verifier, transaction.nonce)]


def test_an_unknown_state_is_refused() -> None:
    sso, _, _, _, _ = build()
    with pytest.raises(AuthenticationError):
        sso.complete_login(code="auth-code", state="never-issued", now=NOW)


def test_a_state_cannot_be_replayed() -> None:
    sso, _, _, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    state = transactions.transactions[0].state
    sso.complete_login(code="auth-code", state=state, now=NOW)
    with pytest.raises(AuthenticationError):
        sso.complete_login(code="auth-code", state=state, now=NOW)


def test_an_expired_login_must_be_restarted() -> None:
    sso, _, _, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    state = transactions.transactions[0].state
    with pytest.raises(AuthenticationError):
        sso.complete_login(code="auth-code", state=state, now=NOW + timedelta(minutes=11))


def test_a_second_login_reuses_the_same_user() -> None:
    idp = FakeIdentityProvider()
    sso, _, users, _, transactions = build(idp=idp)
    for _ in range(2):
        sso.start_login(redirect_path=None, now=NOW)
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    assert len(users.users) == 1


def test_an_existing_user_is_linked_by_verified_email() -> None:
    existing = UserAccount(id=7, email="taro@example.com", display_name="Old Name")
    sso, _, users, _, transactions = build(users=[existing])
    sso.start_login(redirect_path=None, now=NOW)
    sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    assert len(users.users) == 1
    assert users.users[0].id == 7
    assert users.users[0].identities == [FederatedIdentity(issuer=ISSUER, subject="abc")]
    # IdP 側の表示名を正とする
    assert users.users[0].display_name == "Taro"


def test_a_deactivated_user_cannot_sign_in() -> None:
    existing = UserAccount(id=7, email="taro@example.com", display_name="Taro", is_active=False)
    sso, _, _, _, transactions = build(users=[existing])
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(Exception):  # noqa: B017 - ValidationError / AccessDeniedError のどちらでも不可
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)


def test_an_unverified_email_is_turned_away() -> None:
    idp = FakeIdentityProvider(
        IdentityClaims(
            identity=FederatedIdentity(issuer=ISSUER, subject="abc"),
            email="taro@example.com",
            email_verified=False,
        )
    )
    sso, _, users, _, transactions = build(idp=idp)
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AccessDeniedError):
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    assert users.users == []


def test_an_unknown_user_is_refused_when_provisioning_is_off() -> None:
    sso, _, users, _, transactions = build(policy=ProvisioningPolicy(auto_provision=False))
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AccessDeniedError):
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    assert users.users == []


def test_an_invited_user_may_sign_in_when_provisioning_is_off() -> None:
    invited = UserAccount(id=3, email="taro@example.com", display_name="Taro")
    sso, _, users, _, transactions = build(
        users=[invited], policy=ProvisioningPolicy(auto_provision=False)
    )
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    assert completed.session_token
    assert len(users.users) == 1


def test_linking_by_email_is_refused_when_emails_are_not_verified() -> None:
    """検証済みメールを要求しない設定では、メール一致での紐付けを許さない。

    許すと「他人のメールを名乗れる IdP」で既存アカウントを乗っ取れる。
    """
    existing = UserAccount(id=7, email="taro@example.com", display_name="Taro")
    sso, _, _, _, transactions = build(
        users=[existing], policy=ProvisioningPolicy(require_verified_email=False)
    )
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AccessDeniedError):
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)


# ── セッション ─────────────────────────────────────────────────────────────
def test_the_issued_token_identifies_the_user() -> None:
    sso, session_auth, _, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    user = session_auth.authenticate(token=completed.session_token, now=NOW)
    assert user.email == "taro@example.com"


def test_no_token_means_not_authenticated() -> None:
    _, session_auth, _, _, _ = build()
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=None, now=NOW)


def test_an_unknown_token_is_refused() -> None:
    _, session_auth, _, _, _ = build()
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token="made-up", now=NOW)


def test_an_expired_session_is_refused_and_discarded() -> None:
    sso, session_auth, _, sessions, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=completed.session_token, now=NOW + timedelta(hours=13))
    assert sessions.sessions == []


def test_deactivating_a_user_ends_the_running_session() -> None:
    sso, session_auth, users, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    users.users[0].is_active = False
    with pytest.raises(AccessDeniedError):
        session_auth.authenticate(token=completed.session_token, now=NOW)


def test_revoking_a_token_ends_the_session() -> None:
    sso, session_auth, _, _, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    session_auth.revoke(token=completed.session_token)
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=completed.session_token, now=NOW)
