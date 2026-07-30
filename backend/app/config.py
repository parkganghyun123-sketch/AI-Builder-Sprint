"""환경 설정. .env에서 읽어온다."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env", env_file_encoding="utf-8", extra="ignore"
    )

    # 모두싸인
    modusign_email: str = ""
    modusign_api_key: str = ""

    # 웹훅 URL에 넣는 무작위 토큰.
    #
    # 모두싸인은 웹훅 서명(HMAC) 기능을 제공하지 않는다.
    # (워크스페이스 → Webhook 설정에 시크릿 항목이 없음)
    # 그래서 URL 자체를 비밀로 삼아 아무나 호출하지 못하게 한다.
    #
    # 값을 비워두면 검증하지 않는다 — 로컬 개발용.
    #   생성: openssl rand -hex 16
    #
    # ⚠️ MODUSIGN_WEBHOOK_SECRET 도 같은 값으로 읽는다.
    #    설계가 HMAC(시크릿) → URL 경로 토큰으로 바뀌면서 이름도 바뀌었는데
    #    .env 와 배포 환경에는 옛 이름이 남아 있었다. 그래서 실제 운영에서
    #    이 값이 항상 빈 문자열이었고, 토큰 검증이 조용히 꺼져 있었다.
    #    두 이름을 모두 받아 그 사고가 다시 나지 않게 한다.
    #    (새로 설정할 때는 WEBHOOK_PATH_TOKEN 을 쓸 것)
    webhook_path_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WEBHOOK_PATH_TOKEN",
            "MODUSIGN_WEBHOOK_SECRET",
        ),
    )

    # Upstage
    upstage_api_key: str = ""

    # 인프라
    database_url: str = ""

    # 프론트 도메인. 쉼표로 여러 개.
    #   CORS_ORIGINS=https://fairsign.vercel.app,https://www.fairsign.kr
    #
    # ⚠️ 비워두면 로컬 개발용 기본값만 허용한다.
    #    프론트를 배포한 뒤 이 값을 안 넣으면 브라우저가 모든 요청을 막는다.
    cors_origins: str = ""

    @property
    def allowed_origins(self) -> list[str]:
        extra = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return [
            "http://localhost:3000",  # Next.js 개발 서버
            "http://127.0.0.1:3000",
            *extra,
        ]

    @property
    def modusign_configured(self) -> bool:
        return bool(self.modusign_email and self.modusign_api_key)


settings = Settings()
