"""定期照合の足回り（毎時、IdP に名簿を聞き直す）。

ユースケース（``ReconcileFederatedUsers``）へ、この配備のもの ——DB のセッション・
IdP の名乗り・発行者の綴り——を渡して回す。⚠ **判断はユースケース側にある。**
ここが持つのは「いつ走るか」と「引けなかったときに何を記録するか」だけ。

⚠ **web のプロセスで動く。** IdP と話す鍵を持っているのが web だけで、他に定期実行の
足回りが無いため。ワーカーが複数なら同じ周回が複数回走るが、照合は何度走らせても
結果が変わらない。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.application.ports.roster_gateway import RosterGateway
from src.application.use_cases.reconcile_federated_users import (
    ReconcileFederatedUsers,
    ReconciliationOutcome,
)
from src.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
)
from src.infrastructure.auth.admin_api_token import AdminApiTokenSource
from src.infrastructure.auth.auth_settings import AuthConfigurationError, AuthSettings
from src.infrastructure.auth.http_roster_gateway import HttpRosterGateway
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.auth_session_repository import (
    SqlAlchemyAuthSessionRepository,
)
from src.infrastructure.repositories.identity_link_repository import (
    SqlAlchemyIdentityLinkRepository,
)
from src.infrastructure.scheduling.interval_worker import IntervalWorker

logger = logging.getLogger(__name__)

WORKER_NAME = "sso-reconciliation"
#: 聞き直す間隔。⚠ **短くしても停止が速くなるわけではない**（速い経路は受け口のほう）。
#: ここは取りこぼしを拾う 2 段目なので、IdP への負荷と釣り合う程度でよい。
RECONCILE_INTERVAL_SECONDS = 3600.0
#: 起動から最初の 1 回まで。起動処理と取り合わない程度に置く。
FIRST_RUN_DELAY_SECONDS = 60.0

#: 見送ってよい失敗。⚠ **どれも「全員辞めた」ではない。**
_SKIPPABLE = (IdentityProviderUnavailableError, AuthConfigurationError)


def build_roster_gateway(settings: AuthSettings) -> RosterGateway:
    return HttpRosterGateway(
        AdminApiTokenSource(settings), timeout_seconds=settings.http_timeout_seconds
    )


def reconcile_once(
    settings: AuthSettings, roster: RosterGateway | None = None
) -> ReconciliationOutcome | None:
    """1 周回ぶん走らせる。見送ったら ``None``。"""
    if not settings.reconciliation_enabled:
        return None
    session = get_db_session()
    try:
        outcome = _reconcile(session, settings, roster or build_roster_gateway(settings))
    finally:
        session.close()
    if outcome is not None:
        logger.info(
            "SSO の定期照合が終わりました",
            extra={
                "event": "auth.oidc.reconciliation.finished",
                "checked": outcome.checked,
                "revoked": outcome.revoked,
                "unlinked": outcome.unlinked,
                "held_back": outcome.held_back,
            },
        )
    return outcome


def _reconcile(
    session: Session, settings: AuthSettings, roster: RosterGateway
) -> ReconciliationOutcome | None:
    try:
        return ReconcileFederatedUsers(
            # ⚠ ログインで結び付けたときと**同じ綴り**（受け口も同じ）。
            issuer=settings.issuer,
            links=SqlAlchemyIdentityLinkRepository(session),
            sessions=SqlAlchemyAuthSessionRepository(session),
            roster=roster,
        ).execute()
    except MachineNotBoundToApplicationError:
        # ⚠ 準備待ちであって障害ではない。結び付けるまで毎時来るので警告にしない。
        logger.info(
            "機械の名乗りがまだアプリに結び付いていません",
            extra={"event": "auth.oidc.reconciliation.not_bound"},
        )
        return None
    except _SKIPPABLE as error:
        logger.warning(
            "SSO の定期照合を見送りました",
            extra={
                "event": "auth.oidc.reconciliation.skipped",
                "reason": type(error).__name__,
            },
        )
        return None


def start_reconciliation_worker(settings: AuthSettings) -> IntervalWorker | None:
    """定期照合を開始する（``AUTH_MODE=oidc`` ＋ ``MACHINE_CLIENT_ID`` のときだけ）。"""
    if not settings.reconciliation_enabled:
        return None
    worker = IntervalWorker(
        WORKER_NAME,
        lambda: reconcile_once(settings),
        interval_seconds=RECONCILE_INTERVAL_SECONDS,
        first_delay_seconds=FIRST_RUN_DELAY_SECONDS,
    )
    worker.start()
    return worker


__all__ = [
    "FIRST_RUN_DELAY_SECONDS",
    "RECONCILE_INTERVAL_SECONDS",
    "WORKER_NAME",
    "build_roster_gateway",
    "reconcile_once",
    "start_reconciliation_worker",
]
