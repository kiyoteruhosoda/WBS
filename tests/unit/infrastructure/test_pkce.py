from src.infrastructure.auth.pkce import CODE_CHALLENGE_METHOD, code_challenge_from_verifier


def test_matches_the_rfc_7636_appendix_b_vector() -> None:
    # RFC 7636 Appendix B。IdP 側の実装と桁で食い違わないことをここで担保する。
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge_from_verifier(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_challenge_is_base64url_without_padding() -> None:
    challenge = code_challenge_from_verifier("a" * 43)
    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge
    assert len(challenge) == 43


def test_the_method_is_s256() -> None:
    # plain 方式は verifier がそのまま URL に出るため使わない
    assert CODE_CHALLENGE_METHOD == "S256"
