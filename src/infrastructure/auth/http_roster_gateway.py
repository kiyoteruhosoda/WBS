"""Implementation that fetches the IdP roster (input for the periodic reconciliation).

```
GET {issuer}/admin/applications/self/users?subs=...
```

⚠ **Do not put the app in the path.** Which app's roster to return is decided **by the IdP** from the
calling service account (the token's identity). Sending a ``client_id`` to declare "I am this
app" is backwards, and a mismatch between identity and declaration would go unnoticed.

⚠ **403 means "this service account is not yet bound as the app's identity".**
It is not an outage, so it is reported separately.

⚠ **Stop with an exception if it cannot be fetched.** Returning an empty roster makes the caller read "everyone left".
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

#: How many ``sub`` values can be asked at once. ⚠ Exceeding it gives 400, so ask in chunks.
SUBJECTS_PER_REQUEST = 100


class HttpRosterGateway(RosterGateway):
    def __init__(self, tokens: AdminToken, *, timeout_seconds: float = 10.0) -> None:
        self._tokens = tokens
        self._timeout = timeout_seconds

    def fetch(self, *, issuer: str, subjects: tuple[str, ...]) -> Roster:
        # ⚠ **Return only after every chunk has been fetched.** A failure midway stops with an exception, so
        #   reconciliation never proceeds on half a roster.
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
            # Even before expiry, it stops working if the IdP side disabled the client or rotated the key.
            self._tokens.invalidate()
        if response.status_code == 403:
            # ⚠ This is hit on every cycle until bound. Do not spam warnings (the caller logs one line).
            raise MachineNotBoundToApplicationError(
                "the machine client is not bound to an application"
            )
        if response.status_code != 200:
            # ⚠ Not the same as an empty roster, so **stop here**. Do not log the body.
            logger.warning(
                "failed to fetch the IdP roster",
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
