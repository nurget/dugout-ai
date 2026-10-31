from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    user_id: str,
    secret_key: str,
) -> str:
    if len(secret_key) < 32:
        raise ValueError(
            "JWT 비밀키는 최소 32자 이상이어야 합니다."
        )

    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token(
    token: str,
    secret_key: str,
) -> str:
    payload = jwt.decode(
        token,
        secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp", "iat", "nbf"]},
    )

    user_id = payload["sub"]

    if not isinstance(user_id, str) or not user_id:
        raise jwt.InvalidTokenError(
            "사용자 식별자가 올바르지 않습니다."
        )

    return user_id