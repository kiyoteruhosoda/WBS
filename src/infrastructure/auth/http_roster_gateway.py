"""IdP の名簿を引く実装（定期照合の材料）。

```
GET {issuer}/admin/applications/self/users?subs=...
```

⚠ **経路にアプリを書かない。** どのアプリの名簿を返すかは、呼んできたサービスアカウント
（トークンの名乗り）から **IdP が決める**。こちらが ``client_id`` を載せて「自分はこの
アプリだ」と申告する形は向きが逆で、名乗りと申告が食い違ったときに気付けない。

⚠ **403 は「このサービスアカウントがまだアプリの名乗りとして結び付いていない」。**
障害ではないので分けて知らせる。

⚠ **引けなかったら例外で止める。** 空の名簿として返すと、呼び出し側は「全員辞めた」と読む。
"""

from __future__ import annotations

import logging

import httpx

from src.application.ports.roster_gateway import RosterGateway
from src.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
)
from src.domain.value_objects.roster import Roster, RosterEntry
from src.infrastructure.auth.admin_api_token import AdminToken
from src.infrastructure.auth.idp_http import IDP_HEADERS

logger = logging.getLogger(__name__)

#: 一度に聞ける ``sub`` の数。⚠ 超えると 400 になるので、分けて聞く。
SUBJECTS_PER_REQUEST = 100


class HttpRosterGateway(RosterGateway):
    def __init__(self, tokens: AdminToken, *, timeout_seconds: float = 10.0) -> None:
        self._tokens = tokens
        self._timeout = timeout_seconds

    def fetch(self, *, issuer: str, subjects: tuple[str, ...]) -> Roster:
        # ⚠ **全部の塊が引けてから返す。** 途中で失敗したら例外で止まり、半分だけの
        #   名簿で照合を進めない。
        entries: list[RosterEntry] = []
        for index in range(0, len(subjects), SUBJECTS_PER_REQUEST):
            entries.extend(
                self._fetch_chunk(issuer, subjects[index : index + SUBJECTS_PER_REQUEST])
            )
        return Roster(entries=tuple(entries))

    def _fetch_chunk(self, issuer: str, subjects: tuple[str, ...]) -> list[RosterEntry]:
        url = f"{issuer.rstrip('/')}/admin/applications/self/users"
        payload = self._get(url, params={"subs": ",".join(subjects)})
        users = payload.get("users")
        if not isinstance(users, list):
            raise IdentityProviderUnavailableError("the roster response has no users")
        return [
            entry
            for entry in (RosterEntry.of(user) for user in users if isinstance(user, dict))
            if entry
        ]

    def _get(self, url: str, *, params: dict[str, str]) -> dict[str, object]:
        try:
            response = httpx.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    **IDP_HEADERS,
                    "Authorization": f"Bearer {self._tokens.token()}",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(
                f"the roster is unreachable: {type(error).__name__}"
            ) from error
        if response.status_code == 401:
            # 期限内でも、向こうでクライアントを止めた・鍵を替えたときは通らなくなる。
            self._tokens.invalidate()
        if response.status_code == 403:
            # ⚠ 結び付けるまで毎周回ここへ来る。警告を撒かない（記録は呼び出し側で 1 行）。
            raise MachineNotBoundToApplicationError(
                "the machine client is not bound to an application"
            )
        if response.status_code != 200:
            # ⚠ 名簿が空なのとは違うので、**ここで止める**。本文は出さない。
            logger.warning(
                "IdP の名簿を引けませんでした",
                extra={
                    "event": "auth.oidc.roster_request_failed",
                    "status_code": response.status_code,
                },
            )
            raise IdentityProviderUnavailableError(f"the roster returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the roster response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = ["SUBJECTS_PER_REQUEST", "HttpRosterGateway"]
