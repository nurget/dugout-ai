import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_reject_jwt_secret_shorter_than_32_characters():
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://localhost/test",
            jwt_secret_key="short-secret",
        )


def test_settings_accept_jwt_secret_with_at_least_32_characters():
    settings = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        jwt_secret_key="x" * 32,
    )

    assert len(settings.jwt_secret_key) == 32
