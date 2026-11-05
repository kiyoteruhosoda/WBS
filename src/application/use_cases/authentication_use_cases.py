"""SSO ログインの筋書き。

OIDC の認可コードフロー（PKCE 付き）を 2 つのユースケースに分ける。

- ``SsoLoginUseCases``          — IdP との往復（開始・コールバック・IdP 側ログアウト）
- ``SessionAuthenticationUseCases`` — 発行済みセッションから利用者を引く

分けているのは、リクエストごとの本人確認に IdP を要らなくするため。ログイン後の
毎リクエストは自前のトークンだけで済み、IdP が落ちていても操作を続けられる。

⚠ **アクセストークンの検証は DB を引かない。** 止める判定は、切れたログインを続ける往復の 1 点に集めてある
（IdP のログイン状態・利用者が止まっていないか。ADR-0071）。リフレッシュトークンはもう出さない。

プロトコルの詳細（ディスカバリ・JWKS・署名検証）は ``IdentityProvider`` の向こう側。
ここが知っているのは「誰を通すか」「誰を作るか」「セッションをどう始めて終えるか」。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from src.application.dto.auth_dto import (
    AuthenticatedUserDTO,
    CompletedLoginDTO,
    IssuedSessionDTO,
    StartedLoginDTO,
)
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import SecretGenerator
from src.application.ports.session_tokens import SessionTokens
from src.domain.entities.login_transaction import (
    DEFAULT_LOGIN_TRANSACTION_TTL,
    LoginPurpose,
    LoginTransaction,
)
from src.domain.entities.refresh_session import RefreshSession, new_identifier
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import AccessDeniedError, AuthenticationError, NotFoundError
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.continued_sign_in import ContinuedSignIn
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.domain.value_objects.redirect_target import RedirectTarget

logger = logging.getLogger(__name__)


class SessionAuthenticationUseCases:
    """自前のトークンから利用者を決める・出し直す・ログインを終わらせる（ADR-0069・ADR-0071）。"""

    def __init__(
        self,
        *,
        users: UserAccountRepository,
        sessions: RefreshSessionRepository,
        tokens: SessionTokens,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens

    def authenticate(self, *, token: str | None, now: datetime) -> AuthenticatedUserDTO:
        """⚠ **DB を引かない。** 止まっている利用者・消えた控えは、ここでは分からない。
        分かるのは切れて続けるときで、それまでの上限がアクセストークンの寿命になる。

        ⚠ **この緩さを引き受けられるのは、続ける往復（:meth:`SsoLoginUseCases.complete_renewal`）が
        IdP と DB で引き締めているからである**（ADR-0071）。
        """
        contents = self._tokens.read_access(token, now=now) if token else None
        if contents is None:
            raise AuthenticationError("Not authenticated")
        return contents.user

    def reissue_access(self, *, token: str | None, now: datetime) -> str | None:
        """利用者の設定を変えた直後に、新しい値でアクセストークンを出し直す。

        ⚠ **新しいトークンを出す経路なので DB を引く。** 引かないと、止められた人が続ける往復を断られた後も
        設定を保存し続けるだけで入っていられる。
        """
        contents = self._tokens.read_access(token, now=now) if token else None
        if contents is None or self._sessions.find(contents.session_id) is None:
            return None
        user = self._users.find_by_id(contents.user.user_id)
        if user is None or not user.is_active:
            return None
        return self._tokens.access_token(_to_dto(user), session_id=contents.session_id, now=now)

    def continuation_of(self, *, token: str | None, now: datetime) -> ContinuedSignIn | None:
        """手元に残った（期限切れでもよい）アクセストークンから、続けるログインを読む（ADR-0071）。⚠ 認証ではない。"""
        return self._tokens.continuation_of(token, now=now) if token else None

    def revoke(self, *, token: str | None, now: datetime) -> None:
        """このログインだけを終わらせる（ほかの端末は続く）。読めないトークンは何もしない。

        アクセストークンが切れていても、控えを残す長さのうちなら読む（ADR-0071。ログアウトの札はもう無い）。
        """
        continued = self.continuation_of(token=token, now=now)
        if continued is None:
            return
        session = self._sessions.find(continued.session_id)
        if session is not None and session.user_id == continued.user_id:
            self._sessions.delete(session.id)


class MachineReaderAuthenticationUseCases:
    """ほかのアプリのサーバーが、利用者の代わりに読み書きしに来たときの利用者（ADR-0056。Scheduler の ADR-0056 と同じ形）。

    受け取る条件（どれか 1 つでも外れたら 401）:

    - 署名・``typ``・発行者・宛先（``MACHINE_AUDIENCE``）・期限（``IdentityProvider.verify_machine_token``）
    - ``sub_type`` が**ある**（機械のトークン。人のログインのトークンでは通らない）
    - ``client_id`` が読んでよいアプリの機械のもの（``MACHINE_READER_CLIENT_IDS``）

    利用者は呼び手が渡す ``(iss, sub)`` で引く。⚠ **ここでも利用者を作らない。** 結び付きが無ければ 404
    （呼び手は「WBS に一度ログインしてください」と出す）。止めた利用者は 403。
    宛名も許可リストも空なら閉じる（既定）。
    """

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        users: UserAccountRepository,
        audience: str,
        accepted_client_ids: frozenset[str],
    ) -> None:
        self._idp = identity_provider
        self._users = users
        self._audience = audience
        self._accepted_client_ids = accepted_client_ids

    def authenticate(self, *, token: str, issuer: str, subject: str) -> AuthenticatedUserDTO:
        if not self._audience or not self._accepted_client_ids:
            raise AuthenticationError("Machine readers are not accepted by this deployment")
        claims = self._idp.verify_machine_token(token, audience=self._audience)
        if "sub_type" not in claims:
            # 人のログインのトークン（宛名が合っても）はこの口を通さない
            raise AuthenticationError("Only machine tokens are accepted here")
        client_id = str(claims.get("client_id") or "")
        if client_id not in self._accepted_client_ids:
            raise AuthenticationError("Machine token was issued to an application not accepted here")
        if issuer != self._idp.federated_issuer or not subject.strip():
            raise NotFoundError("user", subject)
        user = self._users.find_by_identity(FederatedIdentity(issuer=issuer, subject=subject))
        if user is None:
            raise NotFoundError("user", subject)
        if not user.is_active:
            raise AccessDeniedError(f"User account is deactivated: {user.email}")
        logger.info("machine_reader_call", extra={"client_id": client_id, "user_id": user.id})
        return replace(_to_dto(user), machine_client_id=client_id)


class SsoLoginUseCases:
    """IdP との認可コードフローを進め、成功したらセッションを発行する。"""

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        users: UserAccountRepository,
        sessions: RefreshSessionRepository,
        tokens: SessionTokens,
        transactions: LoginTransactionRepository,
        secrets: SecretGenerator,
        policy: ProvisioningPolicy,
        sign_in_carry: timedelta,
        transaction_ttl: timedelta = DEFAULT_LOGIN_TRANSACTION_TTL,
    ) -> None:
        self._idp = identity_provider
        self._users = users
        self._sessions = sessions
        self._transactions = transactions
        self._secrets = secrets
        self._policy = policy
        self._tokens = tokens
        self._transaction_ttl = transaction_ttl
        #: ログインの控えを残す長さ（ADR-0071）。続けるたびに延びる
        self._sign_in_carry = sign_in_carry

    @property
    def provider_name(self) -> str:
        return self._idp.display_name

    # ── 1. ログイン開始 ────────────────────────────────────────────────
    def start_login(
        self, *, redirect_path: str | None, now: datetime, silent: bool = False
    ) -> StartedLoginDTO:
        """``silent`` は IdP に画面を出させずに「もう入っているか」を確かめる往復（ADR-0062）。"""
        return self._start(RedirectTarget.parse(redirect_path), now=now, silent=silent)

    def start_renewal(self, *, continued: ContinuedSignIn | None, now: datetime) -> StartedLoginDTO:
        """切れたログインを画面を出さずに続ける往復（見えない枠の中。ADR-0071）。常に ``prompt=none``。

        ``continued`` は手元に残っていた期限切れのトークンから読んだもの。戻ってきた人が同じなら、
        その控えを引き継ぐ。読めなければ ``None``（新しいログインとして入る）。
        """
        return self._start(
            RedirectTarget.parse(None), now=now, silent=True, purpose=LoginPurpose.RENEW, continued=continued
        )

    def _start(
        self,
        target: RedirectTarget,
        *,
        now: datetime,
        silent: bool,
        purpose: LoginPurpose = LoginPurpose.LOGIN,
        continued: ContinuedSignIn | None = None,
    ) -> StartedLoginDTO:
        state = self._secrets.generate()
        nonce = self._secrets.generate()
        code_verifier = self._secrets.generate()
        transaction = LoginTransaction.issue(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_target=target,
            now=now,
            ttl=self._transaction_ttl,
            silent=silent,
            purpose=purpose,
            continued=continued,
        )
        # 中断されたログイン（コールバックが返ってこなかった往復）を溜めない
        self._transactions.delete_expired(now)
        self._transactions.add(transaction)
        request = self._idp.build_authorization_request(
            state=state, nonce=nonce, code_verifier=code_verifier, silent=silent
        )
        # ``browser_binding`` は Presentation 層が短命な Cookie に載せ、コールバックで
        # 突き合わせる。DB に state があるだけだと、攻撃者が自分で始めたログインの
        # コールバック URL を被害者に踏ませて「攻撃者としてログイン済み」の状態に
        # できてしまう（ログイン CSRF）。
        return StartedLoginDTO(
            authorization_url=request.authorization_url, browser_binding=state
        )

    # ── 2. コールバック ───────────────────────────────────────────────
    def purpose_of(self, state: str) -> LoginPurpose | None:
        """戻りをどの後始末に回すか（往復は消さない）。覚えのない ``state`` なら ``None``。"""
        transaction = self._transactions.find(state)
        return None if transaction is None else transaction.purpose

    def complete_login(self, *, code: str, state: str, now: datetime) -> CompletedLoginDTO:
        transaction, claims = self._redeem(code=code, state=state, now=now, purpose=LoginPurpose.LOGIN)
        user = self._resolve_user(claims)
        user.ensure_can_sign_in()
        # 期限の切れた控えはここで掃除する（定期実行を持たない）
        self._sessions.delete_expired(now)
        session_id = self._new_sign_in(user.id, claims, now)
        return CompletedLoginDTO(
            session=IssuedSessionDTO(
                access_token=self._tokens.access_token(_to_dto(user), session_id=session_id, now=now)
            ),
            redirect_path=transaction.redirect_target.path,
        )

    def complete_renewal(self, *, code: str, state: str, now: datetime) -> IssuedSessionDTO | None:
        """続ける往復の戻り（ADR-0071）。続けられなければ ``None``（画面はログイン画面へ送る）。

        続けないのは: 別の人が戻ってきた（IdP で別の人に入り直していた）・利用者が止まっている・
        入れる人の決まりに外れた。往復が壊れた・IdP と話せないときは例外（呼ぶ側が ``failed`` にする）。

        ⚠ **続けるのは入り直しではない。** 同じ人の控えが残っていれば、それを延ばして引き継ぐ。
        控えが消えていれば（停止の通知・定期照合・ログアウト）新しい控えを作る ——IdP がまだ入っていると
        答えたので、新しいログインとして入れてよい。
        """
        transaction, claims = self._redeem(code=code, state=state, now=now, purpose=LoginPurpose.RENEW)
        try:
            self._policy.ensure_allowed(claims)
        except AccessDeniedError:
            return None
        user = self._users.find_by_identity(claims.identity)
        continued = transaction.continued
        if user is None or not user.is_active:
            return None
        if continued is not None and continued.user_id != user.id:
            logger.info("sso_renewal_switched_user", extra={"event": "auth.sso.renewal_switched_user"})
            return None
        if user.apply_profile(email=claims.email, display_name=claims.resolved_display_name()):
            user = self._users.save(user)
        session_id = self._continue_sign_in(continued, user.id, claims, now)
        return IssuedSessionDTO(
            access_token=self._tokens.access_token(_to_dto(user), session_id=session_id, now=now)
        )

    def _redeem(
        self, *, code: str, state: str, now: datetime, purpose: LoginPurpose
    ) -> tuple[LoginTransaction, IdentityClaims]:
        transaction = self._transactions.consume(state)
        if transaction is None or transaction.purpose is not purpose:
            # 覚えのない state。CSRF か、コールバックの二重送信（consume は 1 回きり）。
            raise AuthenticationError("Unknown or already used login state")
        if transaction.is_expired(now):
            raise AuthenticationError("Login request has expired; please sign in again")
        claims = self._idp.exchange_code(
            code=code, code_verifier=transaction.code_verifier, nonce=transaction.nonce
        )
        if purpose is LoginPurpose.LOGIN:
            self._policy.ensure_allowed(claims)
        return transaction, claims

    def _new_sign_in(self, user_id: int, claims: IdentityClaims, now: datetime) -> str:
        session_id = new_identifier()
        self._sessions.add(
            RefreshSession(
                id=session_id,
                user_id=user_id,
                expires_at=now + self._sign_in_carry,
                created_at=now,
                # IdP 側のログイン（``sid``）を覚えておく。停止の通知が「その端末の
                # ログインだけ」を指して届いたときに、そこだけを終わらせられる。
                idp_session_id=claims.session_id,
            )
        )
        return session_id

    def _continue_sign_in(
        self, continued: ContinuedSignIn | None, user_id: int, claims: IdentityClaims, now: datetime
    ) -> str:
        if continued is not None:
            session = self._sessions.find(continued.session_id)
            if session is not None and session.user_id == user_id and self._sessions.extend(
                session.id, idp_session_id=claims.session_id, expires_at=now + self._sign_in_carry
            ):
                return session.id
        return self._new_sign_in(user_id, claims, now)

    def decline_silent_login(self, *, state: str, now: datetime) -> str | None:
        """黙って確かめた往復に、IdP が「入っていない」と答えた（ADR-0062）。

        往復を使い切り、それが黙って確かめた往復なら戻り先を返す（画面はエラー無しで
        ログイン画面へ戻す）。そうでなければ ``None``（呼ぶ側は今まで通りエラーとして扱う）。
        """
        transaction = self._transactions.consume(state)
        if transaction is None or not transaction.silent or transaction.is_expired(now):
            return None
        return transaction.redirect_target.path

    def decline_renewal(self, *, state: str, now: datetime) -> bool:
        """続ける往復に、IdP が「入っていない」と答えた（ADR-0071）。往復を使い切り、続ける往復だったかを返す。"""
        transaction = self._transactions.consume(state)
        return (
            transaction is not None
            and transaction.purpose is LoginPurpose.RENEW
            and not transaction.is_expired(now)
        )

    # ── 3. IdP 側のログアウト ─────────────────────────────────────────
    def end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        return self._idp.build_end_session_url(post_logout_redirect_uri=post_logout_redirect_uri)

    # ── 利用者の突き合わせ・作成 ───────────────────────────────────────
    def _resolve_user(self, claims: IdentityClaims) -> UserAccount:
        """``(iss, sub)`` で引き、無ければメールで既存利用者に結び付け、それも無ければ作る。"""
        user = self._users.find_by_identity(claims.identity)
        if user is not None:
            if user.apply_profile(email=claims.email, display_name=claims.resolved_display_name()):
                user = self._users.save(user)
            return user

        if claims.email is not None:
            existing = self._users.find_by_email(claims.email)
            if existing is not None:
                # SSO 導入前から居る利用者、あるいは別 IdP で入っていた利用者。
                # ⚠ **メールアドレスは本人の証明ではない**ので、既定では寄せない
                #   （`ProvisioningPolicy.link_by_email`）。寄せると決めた配備でも、
                #   検証済みのアドレスでなければ通さない。
                self._policy.ensure_can_link_by_email(claims)
                existing.ensure_can_sign_in()
                existing.link_identity(claims.identity)
                existing.apply_profile(
                    email=claims.email, display_name=claims.resolved_display_name()
                )
                return self._users.save(existing)

        self._policy.ensure_can_provision(claims)
        created = UserAccount(
            id=None,
            email=claims.email,
            display_name=claims.resolved_display_name(),
            identities=[claims.identity],
        )
        return self._users.save(created)


def _to_dto(user: UserAccount) -> AuthenticatedUserDTO:
    return AuthenticatedUserDTO(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        language=user.language,
        can_create_projects=user.can_create_projects,
    )
