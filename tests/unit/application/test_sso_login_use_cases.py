"""Check the SSO sign-in scenarios without the IdP or a DB."""

from datetime import datetime, timedelta

import pytest

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.application.ports.secret_generator import SecretGenerator
from src.application.use_cases.authentication_use_cases import (
    SessionAuthenticationUseCases,
    SsoLoginUseCases,
)
from src.domain.entities.login_transaction import LoginPurpose, LoginTransaction
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import AccessDeniedError, AuthenticationError
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.continued_sign_in import ContinuedSignIn
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.logout_notice import InvalidLogoutTokenError
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.infrastructure.auth.jwt_session_tokens import JwtSessionTokens

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


class InMemorySessions(RefreshSessionRepository):
    def __init__(self) -> None:
        self.sessions: list = []
        #: ``(issuer, subject)`` -> user. Used to look up whom a suspension is addressed to.
        self.user_ids_by_identity: dict[tuple[str, str], int] = {}

    def add(self, session):
        self.sessions.append(session)

    def find(self, session_id):
        return next((s for s in self.sessions if s.id == session_id), None)

    def delete(self, session_id):
        self.sessions = [s for s in self.sessions if s.id != session_id]

    def delete_expired(self, now):
        before = len(self.sessions)
        self.sessions = [s for s in self.sessions if not s.is_expired(now)]
        return before - len(self.sessions)

    def extend(self, session_id, *, idp_session_id, expires_at):
        session = self.find(session_id)
        if session is None:
            return False
        session.idp_session_id, session.expires_at = idp_session_id, expires_at
        return True

    def delete_for_identity(self, identity, *, idp_session_id=None):
        # The store has no user-to-link mapping, so look up the
        # ``user_ids_by_identity`` given by the test (by default "matches nobody").
        user_id = self.user_ids_by_identity.get((identity.issuer, identity.subject))
        if user_id is None:
            return 0
        matched = [
            s
            for s in self.sessions
            if s.user_id == user_id
            and (idp_session_id is None or s.idp_session_id == idp_session_id)
        ]
        self.sessions = [s for s in self.sessions if s not in matched]
        return len(matched)

    def delete_for_idp_session(self, *, issuer, idp_session_id):
        matched = [s for s in self.sessions if s.idp_session_id == idp_session_id]
        self.sessions = [s for s in self.sessions if s not in matched]
        return len(matched)


class InMemoryTransactions(LoginTransactionRepository):
    def __init__(self) -> None:
        self.transactions: list[LoginTransaction] = []

    def add(self, transaction):
        self.transactions.append(transaction)
        return transaction

    def find(self, state):
        return next((t for t in self.transactions if t.state == state), None)

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
    """Return a value that differs on each call but is predictable (so verification can be followed by eye)."""

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

    def build_authorization_request(self, *, state, nonce, code_verifier, silent=False):
        prompt = "&prompt=none" if silent else ""
        return AuthorizationRequest(
            authorization_url=f"{ISSUER}/auth?state={state}&nonce={nonce}{prompt}",
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )

    def exchange_code(self, *, code, code_verifier, nonce):
        self.exchanged.append((code, code_verifier, nonce))
        return self._claims

    def build_end_session_url(self, *, post_logout_redirect_uri):
        return f"{ISSUER}/logout"

    @property
    def federated_issuer(self):
        return ISSUER

    def verify_logout_token(self, token):
        raise InvalidLogoutTokenError("this fake does not serve logout tokens")

    def verify_machine_token(self, token, *, audience):
        raise AuthenticationError("this fake does not serve machine tokens")

    def verify_access_token(self, token):
        raise AuthenticationError("this fake does not serve access tokens")


TOKENS = JwtSessionTokens(
    signing_key="unit-test-signing-key-unit-test-signing-key",
    access_lifetime=timedelta(minutes=5),
    carry=timedelta(days=30),
)


def build(idp=None, users=None, policy=None):
    users_repo = InMemoryUsers(users)
    sessions = InMemorySessions()
    transactions = InMemoryTransactions()
    sso = SsoLoginUseCases(
        identity_provider=idp or FakeIdentityProvider(),
        users=users_repo,
        sessions=sessions,
        tokens=TOKENS,
        transactions=transactions,
        secrets=CountingSecrets(),
        policy=policy or ProvisioningPolicy(),
        sign_in_carry=timedelta(days=30),
    )
    session_auth = SessionAuthenticationUseCases(users=users_repo, sessions=sessions, tokens=TOKENS)
    return sso, session_auth, users_repo, sessions, transactions


def login(sso, *, code="auth-code", now=NOW, redirect_path=None):
    sso.start_login(redirect_path=redirect_path, now=now)
    return sso


# ── Starting sign-in ───────────────────────────────────────────────────────
def test_start_login_remembers_state_nonce_and_verifier() -> None:
    sso, _, _, _, transactions = build()
    started = sso.start_login(redirect_path="/tasks", now=NOW)
    assert len(transactions.transactions) == 1
    transaction = transactions.transactions[0]
    assert transaction.state in started.authorization_url
    assert transaction.nonce in started.authorization_url
    # The PKCE verifier does not appear in the URL sent to the IdP (only the challenge is handed over)
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


# ── Callback ───────────────────────────────────────────────────────────────
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
    assert sessions.sessions[0].user_id == users.users[0].id
    assert sessions.sessions[0].expires_at == NOW + timedelta(days=30)
    assert completed.session.access_token


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
    """⚠ Happens **only in deployments that chose to merge** (the default does not merge; see the test below)."""
    existing = UserAccount(id=7, email="taro@example.com", display_name="Old Name")
    sso, _, users, _, transactions = build(
        users=[existing], policy=ProvisioningPolicy(link_by_email=True)
    )
    sso.start_login(redirect_path=None, now=NOW)
    sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)

    assert len(users.users) == 1
    assert users.users[0].id == 7
    assert users.users[0].identities == [FederatedIdentity(issuer=ISSUER, subject="abc")]
    # The IdP's display name wins
    assert users.users[0].display_name == "Taro"


def test_a_deactivated_user_cannot_sign_in() -> None:
    existing = UserAccount(id=7, email="taro@example.com", display_name="Taro", is_active=False)
    sso, _, _, _, transactions = build(users=[existing])
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(Exception):  # noqa: B017 - either ValidationError or AccessDeniedError is fine
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
        users=[invited], policy=ProvisioningPolicy(auto_provision=False, link_by_email=True)
    )
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    assert completed.session.access_token
    assert len(users.users) == 1


def test_linking_by_email_is_refused_when_emails_are_not_verified() -> None:
    """When verified email is not required, linking by matching email is not allowed.

    Allowing it would let an "IdP that lets you claim someone else's email" take over existing accounts.
    """
    existing = UserAccount(id=7, email="taro@example.com", display_name="Taro")
    sso, _, _, _, transactions = build(
        users=[existing],
        policy=ProvisioningPolicy(link_by_email=True, require_verified_email=False),
    )
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AccessDeniedError):
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)


def test_linking_by_email_is_off_by_default() -> None:
    """⚠ **An email address is not proof of identity.**

    Even if ``email_verified`` is true, it means "the IdP can reach that address",
    not "this user is that person". Leaving merging open by default would let anyone who could claim
    someone's address at the IdP get into this app's existing account.
    """
    existing = UserAccount(id=7, email="taro@example.com", display_name="Taro")
    sso, _, users, _, transactions = build(users=[existing])
    sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AccessDeniedError):
        sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    # ⚠ The existing user stays **as is**. No new one is created either.
    assert [u.id for u in users.users] == [7]
    assert users.users[0].identities == []


# ── Tokens ─────────────────────────────────────────────────────────────────
def _signed_in():
    sso, session_auth, users, sessions, transactions = build()
    sso.start_login(redirect_path=None, now=NOW)
    completed = sso.complete_login(code="c", state=transactions.transactions[0].state, now=NOW)
    return session_auth, users, sessions, completed.session


def test_the_issued_token_identifies_the_user() -> None:
    session_auth, _, _, issued = _signed_in()
    user = session_auth.authenticate(token=issued.access_token, now=NOW)
    assert user.email == "taro@example.com"


def test_no_token_means_not_authenticated() -> None:
    _, session_auth, _, _, _ = build()
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=None, now=NOW)


def test_an_unknown_token_is_refused() -> None:
    _, session_auth, _, _, _ = build()
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token="made-up", now=NOW)


def test_a_token_signed_with_another_key_is_refused() -> None:
    session_auth, _, sessions, issued = _signed_in()
    other = JwtSessionTokens(
        signing_key="another-signing-key-another-signing-key",
        access_lifetime=timedelta(minutes=5),
        carry=timedelta(days=30),
    )
    user = session_auth.authenticate(token=issued.access_token, now=NOW)
    forged = other.access_token(user, session_id=sessions.sessions[0].id, now=NOW)
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=forged, now=NOW)
    assert session_auth.continuation_of(token=forged, now=NOW) is None
    session_auth.revoke(token=forged, now=NOW)
    assert len(sessions.sessions) == 1


def test_the_access_token_ends_at_its_lifetime_but_still_tells_whose_sign_in_it_was() -> None:
    session_auth, users, sessions, issued = _signed_in()
    later = NOW + timedelta(minutes=5)
    with pytest.raises(AuthenticationError):
        session_auth.authenticate(token=issued.access_token, now=later)
    continued = session_auth.continuation_of(token=issued.access_token, now=later)
    assert continued == ContinuedSignIn(user_id=users.users[0].id, session_id=sessions.sessions[0].id)


def test_the_continuation_is_read_only_while_the_cookie_is_kept() -> None:
    session_auth, _, _, issued = _signed_in()
    assert session_auth.continuation_of(token=issued.access_token, now=NOW + timedelta(days=29)) is not None
    assert session_auth.continuation_of(token=issued.access_token, now=NOW + timedelta(days=31)) is None


def test_revoking_ends_the_sign_in_even_after_the_token_expired() -> None:
    session_auth, _, sessions, issued = _signed_in()
    session_auth.revoke(token=issued.access_token, now=NOW + timedelta(hours=2))
    assert sessions.sessions == []


def test_reissuing_the_access_token_needs_a_live_sign_in() -> None:
    session_auth, users, sessions, issued = _signed_in()
    assert session_auth.reissue_access(token=issued.access_token, now=NOW)
    users.users[0].is_active = False
    assert session_auth.reissue_access(token=issued.access_token, now=NOW) is None
    users.users[0].is_active = True
    sessions.sessions.clear()
    assert session_auth.reissue_access(token=issued.access_token, now=NOW) is None


# ── Silent check (prompt=none; ADR-0062) ───────────────────────────────────
def test_a_silent_start_asks_without_a_screen() -> None:
    sso, _, _, _, transactions = build()
    started = sso.start_login(redirect_path="/gantt", now=NOW, silent=True)
    assert started.authorization_url.endswith("&prompt=none")
    assert transactions.transactions[0].silent is True


def test_declining_a_silent_start_returns_where_to_go() -> None:
    sso, _, _, _, transactions = build()
    started = sso.start_login(redirect_path="/gantt", now=NOW, silent=True)
    assert sso.decline_silent_login(state=started.browser_binding, now=NOW) == "/gantt"
    # Used up
    assert transactions.transactions == []


def test_declining_an_ordinary_start_is_not_silent() -> None:
    sso, _, _, _, _ = build()
    started = sso.start_login(redirect_path="/gantt", now=NOW)
    assert sso.decline_silent_login(state=started.browser_binding, now=NOW) is None


# ── Continue (prompt=none inside the hidden frame; ADR-0071) ───────────────
def _renewal(sso, transactions, continued):
    started = sso.start_renewal(continued=continued, now=NOW)
    return started, transactions.transactions[-1]


def test_a_renewal_asks_without_a_screen_and_remembers_whose_sign_in_it_continues() -> None:
    sso, session_auth, users, sessions, transactions = build()
    login(sso)
    issued = sso.complete_login(code="auth-code", state=transactions.transactions[0].state, now=NOW).session
    continued = session_auth.continuation_of(token=issued.access_token, now=NOW + timedelta(hours=1))
    started, transaction = _renewal(sso, transactions, continued)
    assert started.authorization_url.endswith("&prompt=none")
    assert transaction.purpose is LoginPurpose.RENEW
    assert transaction.continued == continued
    assert sso.purpose_of(transaction.state) is LoginPurpose.RENEW


def test_a_renewal_extends_the_same_sign_in() -> None:
    sso, session_auth, users, sessions, transactions = build()
    login(sso)
    issued = sso.complete_login(code="auth-code", state=transactions.transactions[0].state, now=NOW).session
    continued = session_auth.continuation_of(token=issued.access_token, now=NOW)
    later = NOW + timedelta(days=3)
    started = sso.start_renewal(continued=continued, now=later)
    renewed = sso.complete_renewal(code="auth-code", state=started.browser_binding, now=later)
    assert renewed is not None
    assert len(sessions.sessions) == 1
    assert sessions.sessions[0].expires_at == later + timedelta(days=30)
    assert session_auth.authenticate(token=renewed.access_token, now=later).email == "taro@example.com"


def test_a_renewal_for_someone_else_is_declined() -> None:
    sso, _, users, sessions, transactions = build()
    login(sso)
    sso.complete_login(code="auth-code", state=transactions.transactions[0].state, now=NOW)
    started = sso.start_renewal(continued=ContinuedSignIn(user_id=999, session_id="x"), now=NOW)
    assert sso.complete_renewal(code="auth-code", state=started.browser_binding, now=NOW) is None
    assert len(sessions.sessions) == 1


def test_a_renewal_for_a_stopped_user_is_declined() -> None:
    sso, _, users, _, transactions = build()
    login(sso)
    sso.complete_login(code="auth-code", state=transactions.transactions[0].state, now=NOW)
    users.users[0].is_active = False
    started = sso.start_renewal(continued=None, now=NOW)
    assert sso.complete_renewal(code="auth-code", state=started.browser_binding, now=NOW) is None


def test_a_renewal_does_not_create_an_account() -> None:
    sso, _, users, _, _ = build()
    started = sso.start_renewal(continued=None, now=NOW)
    assert sso.complete_renewal(code="auth-code", state=started.browser_binding, now=NOW) is None
    assert users.users == []


def test_a_login_state_cannot_complete_a_renewal_and_back() -> None:
    sso, _, _, _, _ = build()
    login_started = sso.start_login(redirect_path=None, now=NOW)
    with pytest.raises(AuthenticationError):
        sso.complete_renewal(code="auth-code", state=login_started.browser_binding, now=NOW)
    renewal_started = sso.start_renewal(continued=None, now=NOW)
    with pytest.raises(AuthenticationError):
        sso.complete_login(code="auth-code", state=renewal_started.browser_binding, now=NOW)


def test_declining_a_renewal_uses_it_up() -> None:
    sso, _, _, _, transactions = build()
    started = sso.start_renewal(continued=None, now=NOW)
    assert sso.decline_renewal(state=started.browser_binding, now=NOW) is True
    assert transactions.transactions == []
    login_started = sso.start_login(redirect_path=None, now=NOW, silent=True)
    assert sso.decline_renewal(state=login_started.browser_binding, now=NOW) is False


def test_declining_an_unknown_or_expired_start_is_not_silent() -> None:
    sso, _, _, _, _ = build()
    assert sso.decline_silent_login(state="unknown", now=NOW) is None
    started = sso.start_login(redirect_path="/gantt", now=NOW, silent=True)
    assert sso.decline_silent_login(state=started.browser_binding, now=NOW + timedelta(hours=1)) is None
