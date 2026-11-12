"""Values attached to every outgoing HTTP request to the IdP.

⚠ **Always send a User-Agent.** With a WAF / CDN in front of the IdP, an HTTP library's
default UA (``Python-urllib/3.x`` etc.) may be rejected with 403 as an automation tool.

⚠ **JWKS takes a different path.** Discovery, token and userinfo are fetched with ``httpx``, but
JWKS is fetched by PyJWT's ``PyJWKClient`` via **``urllib``**. Adding the header only
on the httpx side does not affect JWKS.

How it actually broke (2026-08-30, behind Cloudflare):

* Discovery and the token exchange succeed (httpx's UA was let through)
* Only the JWKS fetch returns 403, so **ID token signature verification always fails**
* The screen only says "login failed", and no exception is left
    in the server log either (the callback swallows it and returns to the login screen)

It shows up as "tokens come through, yet login fails every time", which is hard to
isolate, so whenever you add a path, always send this header through it.
"""

from __future__ import annotations

USER_AGENT = "wbs-oidc/1.0"

IDP_HEADERS: dict[str, str] = {"User-Agent": USER_AGENT}
