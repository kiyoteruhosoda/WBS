"""IdP の名簿を引く実装。⚠ **「引けなかった」を「誰も居ない」にしないこと。**"""

import httpx
import pytest

from src.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
)
from src.domain.value_objects.roster import RosterState
from src.infrastructure.auth.http_roster_gateway import (
    SUBJECTS_PER_REQUEST,
    HttpRosterGateway,
)

ISSUER = "https://idp.example.com/realms/wbs"


class FakeTokens:
    def __init__(self) -> None:
        self.invalidated = 0

    def token(self) -> str:
        return "machine-token"

    def invalidate(self) -> None:
        self.invalidated += 1


def gateway(monkeypatch, responder):
    calls: list[httpx.Request] = []

    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url, params=kwargs.get("params"), headers=kwargs.get("headers"))
        calls.append(request)
        return responder(request)

    monkeypatch.setattr(httpx, "get", fake_get)
    tokens = FakeTokens()
    return HttpRosterGateway(tokens), tokens, calls


def json_response(request: httpx.Request, payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=request)


def test_the_roster_is_read_into_states(monkeypatch) -> None:
    roster, _, calls = gateway(
        monkeypatch,
        lambda request: json_response(
            request,
            {"users": [{"sub": "taro", "state": "blocked"}, {"sub": "hanako", "state": "allowed"}]},
        ),
    )
    answers = roster.fetch(issuer=ISSUER, subjects=("taro", "hanako"))

    assert answers.state_of("taro") is RosterState.BLOCKED
    assert answers.state_of("hanako") is RosterState.ALLOWED
    # ⚠ **経路にアプリを書かない。** どのアプリの名簿かは名乗りから IdP が決める。
    assert calls[0].url.path.endswith("/admin/applications/self/users")
    assert calls[0].headers["Authorization"] == "Bearer machine-token"


def test_a_long_list_is_asked_in_chunks(monkeypatch) -> None:
    subjects = tuple(f"user-{index}" for index in range(SUBJECTS_PER_REQUEST + 5))
    roster, _, calls = gateway(
        monkeypatch,
        lambda request: json_response(
            request, {"users": [{"sub": sub, "state": "allowed"} for sub in subjects[:1]]}
        ),
    )
    roster.fetch(issuer=ISSUER, subjects=subjects)

    assert len(calls) == 2


def test_a_machine_that_is_not_bound_is_told_apart(monkeypatch) -> None:
    """⚠ 403 は準備待ち。障害と同じ扱いにすると、毎周回 warning が出続ける。"""
    roster, _, _ = gateway(monkeypatch, lambda request: json_response(request, {}, 403))
    with pytest.raises(MachineNotBoundToApplicationError):
        roster.fetch(issuer=ISSUER, subjects=("taro",))


def test_an_expired_token_is_thrown_away(monkeypatch) -> None:
    """期限内でも、向こうで止められれば通らなくなる。控えを捨てて取り直させる。"""
    roster, tokens, _ = gateway(monkeypatch, lambda request: json_response(request, {}, 401))
    with pytest.raises(IdentityProviderUnavailableError):
        roster.fetch(issuer=ISSUER, subjects=("taro",))
    assert tokens.invalidated == 1


@pytest.mark.parametrize(
    "responder",
    [
        lambda request: json_response(request, {}, 500),
        lambda request: json_response(request, {"nobody": []}),  # users が無い
        lambda request: httpx.Response(200, text="not json", request=request),
    ],
    ids=["server-error", "no-users", "not-json"],
)
def test_a_roster_we_cannot_read_raises(monkeypatch, responder) -> None:
    roster, _, _ = gateway(monkeypatch, responder)
    with pytest.raises(IdentityProviderUnavailableError):
        roster.fetch(issuer=ISSUER, subjects=("taro",))


def test_an_unreachable_idp_raises(monkeypatch) -> None:
    def explode(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "get", explode)
    with pytest.raises(IdentityProviderUnavailableError):
        HttpRosterGateway(FakeTokens()).fetch(issuer=ISSUER, subjects=("taro",))
