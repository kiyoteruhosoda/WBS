"""停止の伝播（IdP → このアプリ）が効いているか。

IdP との通信はプロバイダを差し替えて止める。ここで確かめたいのは、**届いた通知が
実際にセッションを終わらせること**と、終わらせる範囲を間違えないことである。

このアプリのセッションは DB の行で、毎リクエストで引き直している（ADR-0002）。
だから停止は**次のリクエストで効く** ——手元に控えの無いトークンを配っていないぶん、
「寿命のあいだは通る」という緩みが無い。
"""

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    COOKIE,
    sign_in,
    sso_client,
    sso_provider,
)

LOGOUT = "/api/auth/backchannel-logout"


def post_logout(client: TestClient, logout_token: str) -> int:
    """IdP のサーバーが叩く経路。**Cookie も資格情報も持たない。**"""
    return client.post(LOGOUT, data={"logout_token": logout_token}).status_code


def test_a_stop_from_the_idp_ends_the_session(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200

    # ⚠ **次のリクエストでもう通らない**（セッションの行が消えている）。
    assert sso_client.get("/api/auth/me").status_code == 401


def test_a_stop_without_a_sid_ends_every_session_of_that_user(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert post_logout(sso_client, "taro||delivery-1") == 200
    assert sso_client.get("/api/auth/me").status_code == 401


def test_a_stop_for_another_person_leaves_this_session_alone(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert post_logout(sso_client, "hanako|hanako-session|delivery-1") == 200
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_stop_for_another_login_of_the_same_person_leaves_this_one_alone(sso_client) -> None:  # noqa: F811
    """⚠ **``sid`` まで分かっている通知は、その端末のログインだけを終わらせる。**

    ここが効いていないと、よその端末でサインアウトしただけで全部の端末が落ちる。
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|another-device|delivery-1") == 200
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_replayed_notice_does_not_end_a_session_started_afterwards(sso_client) -> None:  # noqa: F811
    """⚠ **再送で、入り直したあとのセッションを消さない。**

    送り手は再送でも同じ ``jti`` を使う。弾かずに毎回効かせると、IdP で戻して
    入り直した直後の再送が、その**新しいセッション**を落とす。
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200
    assert sso_client.get("/api/auth/me").status_code == 401

    sign_in(sso_client)  # IdP で戻され、入り直した
    assert sso_client.get("/api/auth/me").status_code == 200

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200  # 同じ jti の再送
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_new_notice_for_the_same_login_still_lands(sso_client) -> None:  # noqa: F811
    """⚠ **再送を弾くのは ``jti`` であって、「2 回目だから」ではない。**

    止められ、戻され、また止められたときは新しい ``jti`` で届く。ここまで弾くと、
    2 回目の停止が効かなくなる。
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-2") == 200
    assert sso_client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},  # logout_token が無い
        {"logout_token": ""},  # 空
        {"logout_token": ["a|b|c", "d|e|f"]},  # 2 本
    ],
    ids=["missing", "empty", "two"],
)
def test_a_malformed_body_is_refused(sso_client, body) -> None:  # noqa: F811
    assert sso_client.post(LOGOUT, data=body).status_code == 400


def test_a_forged_token_is_refused_and_leaves_the_session(sso_client, sso_provider) -> None:  # noqa: F811
    """⚠ **署名が相手の証明のすべて。** 通らないものは理由を返さずに 400。"""
    sign_in(sso_client)
    # 形としては通る綴り（sub / sid / jti が揃っている）。断る理由は署名だけにする。
    sso_provider.rejected.add("taro|taro-session|delivery-1")

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 400
    assert sso_client.get("/api/auth/me").status_code == 200


def test_the_notice_needs_no_cookie(sso_client) -> None:  # noqa: F811
    """⚠ 送ってくるのは IdP のサーバーで、ブラウザではない（Cookie は付かない）。"""
    sign_in(sso_client)
    cookie = sso_client.cookies.get(COOKIE)
    assert cookie  # 前提: ログインできている
    sso_client.cookies.clear()

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200

    sso_client.cookies.set(COOKIE, cookie)
    assert sso_client.get("/api/auth/me").status_code == 401

