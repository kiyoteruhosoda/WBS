"""IdP へ出ていく HTTP に共通で付ける値。

⚠ **User-Agent を必ず名乗る。** IdP の前段に WAF / CDN が居ると、HTTP ライブラリの
既定の UA（``Python-urllib/3.x`` など）が自動化ツールとして 403 で弾かれることがある。

⚠ **JWKS だけ経路が違う。** ディスカバリ・トークン・userinfo は ``httpx`` で取るが、
JWKS は PyJWT の ``PyJWKClient`` が **``urllib``** で取りに行く。httpx 側にだけ
ヘッダを足しても JWKS には効かない。

実際に踏んだ壊れ方（2026-08-30・Cloudflare の前段）:

* ディスカバリとトークン交換は成功する（httpx の UA は通っていた）
* JWKS の取得だけが 403 になり、**ID トークンの署名検証で必ず落ちる**
* 画面には「ログインに失敗しました」としか出ず、サーバのログにも
  例外は残らない（コールバックが握ってログイン画面へ戻すため）

「トークンまでは通っているのに毎回ログインできない」という、切り分けの難しい
形になるので、経路を増やすときは必ずこのヘッダを通すこと。
"""

from __future__ import annotations

USER_AGENT = "wbs-oidc/1.0"

IDP_HEADERS: dict[str, str] = {"User-Agent": USER_AGENT}
