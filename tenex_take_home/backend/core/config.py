from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    SESSION_SECRET: str = "dev-secret-change-me"
    ANTHROPIC_API_KEY: str
    GOOGLE_API_KEY: str = ""
    DEBUG: bool = False


settings = Settings()
