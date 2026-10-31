import time
from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


SECRET = "test-only-secret-key-with-sufficient-length-123"


def test_password_hash():
    password = "local-test-password-123"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token():
    user_id = str(uuid4())

    token = create_access_token(
        user_id=user_id,
        secret_key=SECRET,
    )

    assert decode_access_token(
        token,
        SECRET,
    ) == user_id


def test_wrong_secret_is_rejected():
    token = create_access_token(
        user_id=str(uuid4()),
        secret_key=SECRET,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(
            token,
            "another-secret-key-with-sufficient-length-123",
        )


def test_expired_token_is_rejected():
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": int(time.time()) - 7200,
            "nbf": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        },
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, SECRET)