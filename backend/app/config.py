"""환경 설정. .env에서 읽어온다."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env", env_file_encoding="utf-8", extra="ignore"
    )

    # 모두싸인
    modusign_email: str = ""
    modusign_api_key: str = ""
    modusign_webhook_secret: str = ""

    # Upstage
    upstage_api_key: str = ""

    # 인프라
    database_url: str = ""

    @property
    def modusign_configured(self) -> bool:
        return bool(self.modusign_email and self.modusign_api_key)


settings = Settings()
