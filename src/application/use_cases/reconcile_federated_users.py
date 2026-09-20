"""IdP へ聞き直して、使えなくなった人のセッションを止める（定期照合）。

停止の通知の受け口は、**通知が届いたときにしか効かない**。IdP が送れなかった・
こちらが落ちていた・送り先が登録されていなかった ——どれも取りこぼしがそのまま残る。
ここはその 2 段目で、毎時 IdP に名簿を聞き直して差を埋める。

止める範囲は受け口と同じ ——**このアプリのセッションだけ**で、利用者そのもの
（``users.is_active``）には触らない。範囲を揃えておかないと、「届いたとき」と
「取りこぼしたとき」で止まる範囲が違う、という分かりにくい状態になる。

⚠ **引けなかったときは何もしない。** 名簿が引けないことと、名簿が空であることを
混ぜない ——混ぜると、IdP が不調なだけで全員を止める。

⚠ **何度走らせても結果が同じになるように書く。** 同じ仕事がワーカーの数だけ、
同じ時刻に走る。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from src.application.ports.roster_gateway import RosterGateway
from src.domain.entities.identity_link import IdentityLink
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.domain.value_objects.roster import Roster, RosterState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationOutcome:
    """1 回の照合で何が起きたか（記録と試験のための数）。"""

    checked: int = 0
    #: セッションを終わらせた人数。⚠ **既に 1 本も無かった人は数えない**（毎時 0 に戻る）。
    revoked: int = 0
    unlinked: int = 0
    #: ⚠ **全員が ``unknown`` で返ったので見送った**か。真のときは何も変えていない。
    held_back: bool = False


@dataclass(frozen=True)
class ReconcileFederatedUsers:
    #: ⚠ ログインで結び付けたときと**同じ綴り**の発行者。1 文字ずれると 1 件も当たらず、
    #: 何も確かめないまま「異常なし」で終わる。
    issuer: str
    links: IdentityLinkRepository
    sessions: AuthSessionRepository
    roster: RosterGateway

    def execute(self) -> ReconciliationOutcome:
        links = self.links.list_for_issuer(self.issuer)
        if not links:
            return ReconciliationOutcome()
        # ⚠ 名指しで聞く。候補の一覧では「向こうに居ない（消えた）」が分からない。
        answers = self.roster.fetch(
            issuer=self.issuer, subjects=tuple(link.subject for link in links)
        )
        outcome = ReconciliationOutcome(checked=len(links))
        if _everyone_is_unknown(links, answers):
            # ⚠ テナントの取り違えやアプリの付け替えでも、この形で返りうる。
            #   全員分の結び付きを外す前に止まる。
            logger.warning(
                "IdP の名簿が全員 unknown だったため照合を見送りました",
                extra={
                    "event": "auth.oidc.reconciliation.everyone_unknown",
                    "checked": len(links),
                },
            )
            return replace(outcome, held_back=True)
        for link in links:
            outcome = self._apply(link, answers.state_of(link.subject), outcome)
        return outcome

    def _apply(
        self, link: IdentityLink, state: RosterState, outcome: ReconciliationOutcome
    ) -> ReconciliationOutcome:
        """1 人ぶんの結果を反映する。⚠ **触らない側も明示的に返す。**"""
        if not state.ends_sessions:
            return outcome
        ended = self.sessions.delete_for_identity(link.identity)
        if ended:
            logger.info(
                "IdP で止まった人のセッションを終了しました",
                extra={
                    "event": "auth.oidc.reconciliation.revoked",
                    "user_id": link.user_id,
                    "ended_sessions": ended,
                },
            )
            outcome = replace(outcome, revoked=outcome.revoked + 1)
        if not state.drops_the_link:
            return outcome
        # 向こうに居ない＝結び付きの相手がもう存在しない。行を残すと、同じ ``sub`` が
        # 別人へ再利用されたときに他人へ繋がる（再利用しない約束だが、残す理由も無い）。
        self.links.unlink(link.id)
        logger.info(
            "IdP に居なくなった人の結び付きを外しました",
            extra={"event": "auth.oidc.reconciliation.unlinked", "user_id": link.user_id},
        )
        return replace(outcome, unlinked=outcome.unlinked + 1)


def _everyone_is_unknown(links: list[IdentityLink], answers: Roster) -> bool:
    """結び付きが 2 件以上あり、全員が ``unknown`` で返ったか。

    1 件だけのときは「その 1 人が消えた」と区別が付かないので、通常どおり扱う。
    """
    if len(links) < 2:
        return False
    return all(answers.state_of(link.subject) is RosterState.UNKNOWN for link in links)


__all__ = ["ReconcileFederatedUsers", "ReconciliationOutcome"]
