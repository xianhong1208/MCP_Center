"""RS256 JWT 簽 / 驗原語。"""

import json
from typing import Optional

import jwt


class JWTVerifyError(Exception):
    pass


def sign_rs256(payload: dict, private_pem: str, kid: str, typ: str = "at+jwt") -> str:
    """簽發 JWT;header 帶 kid(讓驗證端從 JWKS 挑對應公鑰)與 typ(RFC 9068)。"""
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid, "typ": typ})


def unverified_header(token: str) -> dict:
    try:
        return jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise JWTVerifyError(f"malformed token: {e}")


def decode_rs256(token: str, public_jwk: dict, *, issuer: Optional[str] = None,
                 audience: Optional[str] = None, leeway: int = 10) -> dict:
    """用公鑰 JWK 驗簽 + exp(+ iss / aud 若指定)。"""
    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(public_jwk))
        options = {}
        kwargs = {"algorithms": ["RS256"], "leeway": leeway}
        if audience is not None:
            kwargs["audience"] = audience
        else:
            options["verify_aud"] = False
        if issuer is not None:
            kwargs["issuer"] = issuer
        return jwt.decode(token, public_key, options=options, **kwargs)
    except jwt.ExpiredSignatureError:
        raise JWTVerifyError("token expired")
    except jwt.InvalidTokenError as e:
        raise JWTVerifyError(f"invalid token: {e}")


def unverified_claims(token: str) -> dict:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return {}
