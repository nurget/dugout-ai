from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    openai_public_knowledge_vector_store_id: str | None = None
    jwt_secret_key: str
    allow_public_registration: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
