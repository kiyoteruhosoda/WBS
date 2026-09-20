"""IdP からの停止の通知を受け取る（OpenID Connect Back-Channel Logout 1.0）。

この口が呼ばれるのは**利用者のブラウザからではない**。IdP のサーバーが直接叩く
サーバー間の経路で、届いた ``logout_token`` の署名だけが相手の証明になる。

やることは 1 つ ——**宛名の合うセッションの行を消す**。このアプリのセッションは
DB の行で、毎リクエストで引き直している（ADR-0002）ので、消した時点で効く。
手元に控えの無いトークンを配っていないぶん、他の RP のように「失効の記録を残して
次の更新で弾く」手当ては要らない。

⚠ **利用者そのもの（``users.is_active``）には触らない。** 止めたのは IdP であって、
このアプリの管理者ではない。IdP で戻せば、そのまま入り直せる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.ports.identity_provider import IdentityProvider
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.domain.repositories.logout_delivery_repository import LogoutDeliveryRepository
from src.domain.value_objects.logout_notice import LogoutNotice

logger = logging.getLogger(__name__)

#: 配送の記録を残しておく既定の長さ。**セッションの寿命より長ければよい**
#: ——それを過ぎれば、再送が落とせるセッションはもう自力で期限切れになっている。
DEFAULT_DELIVERY_RETENTION = timedelta(days=1)


@dataclass(frozen=True)
class ReceivedLogout:
    """受け取った結果（記録と試験のための数）。"""

    notice: LogoutNotice
    #: 初めて届いた通知か。⚠ 再送は ``False`` で、このときセッションは消していない。
    first_delivery: bool
    ended_sessions: int


class ReceiveBackchannelLogout:
    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        sessions: AuthSessionRepository,
        deliveries: LogoutDeliveryRepository,
        delivery_retention: timedelta = DEFAULT_DELIVERY_RETENTION,
    ) -> None:
        self._idp = identity_provider
        self._sessions = sessions
        self._deliveries = deliveries
        self._delivery_retention = delivery_retention

    def execute(self, *, logout_token: str, now: datetime) -> ReceivedLogout:
        claims = self._idp.verify_logout_token(logout_token)
        notice = LogoutNotice.from_claims(claims, issuer=self._idp.federated_issuer)
        self._deliveries.delete_expired(now - self._delivery_retention)
        # ⚠ **再送では消さない。** 送り手は再送でも同じ ``jti`` を使うので、ここを
        #   素通りさせると、古い通知の再送で**入り直したあとのセッション**が消える。
        if not self._deliveries.record(jti=notice.jti, now=now):
            logger.info(
                "停止の通知を再送として受け流しました",
                extra={"event": "auth.oidc.logout_replayed", "scope": notice.scope},
            )
            return ReceivedLogout(notice=notice, first_delivery=False, ended_sessions=0)
        ended = self._end_sessions(notice)
        logger.info(
            "IdP からの停止の通知でセッションを終了しました",
            extra={
                "event": "auth.oidc.logout_received",
                "scope": notice.scope,
                "ended_sessions": ended,
            },
        )
        return ReceivedLogout(notice=notice, first_delivery=True, ended_sessions=ended)

    def _end_sessions(self, notice: LogoutNotice) -> int:
        if notice.identity is not None:
            return self._sessions.delete_for_identity(
                notice.identity, idp_session_id=notice.session_id
            )
        # ``sub`` が無く ``sid`` だけの通知（仕様上ありうる）。発行者と組にして引く。
        assert notice.session_id is not None  # LogoutNotice がどちらか一方を保証する
        return self._sessions.delete_for_idp_session(
            issuer=self._idp.federated_issuer, idp_session_id=notice.session_id
        )


__all__ = ["DEFAULT_DELIVERY_RETENTION", "ReceiveBackchannelLogout", "ReceivedLogout"]
