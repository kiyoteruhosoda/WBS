"""Android App Links の検証ファイル（ADR-0019。打刻アプリ task #167）。

打刻アプリは assay でのログインを ``https://<このホスト>/app/oauth2redirect`` で受け取る。
Android（と Chrome の Auth Tab）がこの戻り先を**ブラウザではなくアプリへ**渡すのは、
このファイルでホストとアプリの結び付きを確かめられたときだけである。

⚠ **中身は環境変数だけで決める**（``ANDROID_APP_PACKAGE`` / ``ANDROID_APP_CERT_FINGERPRINTS``）。
書き換えられると、別のアプリに認可コードを渡す宣言になる。
⚠ 画面の nginx は ``/api/`` しか裏へ渡さないので、この 1 本だけ ``frontend/nginx.conf.template`` で
裏へ通している。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["app-links"])


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks(request: Request) -> list[dict[str, object]]:
    settings = request.app.state.auth_settings
    package = settings.android_app_package
    fingerprints = list(settings.android_app_cert_fingerprints)
    if not (package and fingerprints):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App Links are not configured")
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]


__all__ = ["router"]
