"""환경 설정. .env에서 읽어온다."""

import logging

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

    # ---------------------------------------------------------- 카카오 로그인
    #
    # ⚠️ 로그인은 **서명 단계에서만** 요구한다.
    #    사진 업로드·판정·문구 복사는 로그인 없이 된다.
    #    열여섯 살이 첫 계약서를 확인하려고 가입부터 해야 한다면
    #    그 벽을 넘지 못한다. 로그인은 "내 문서"를 구분해야 하는
    #    시점에만 필요하다.
    #
    # ⚠️ 이메일 동의항목은 쓰지 않는다. 비즈 앱 심사가 필요하고,
    #    서명받을 이메일은 사용자가 화면에서 직접 입력한다.
    #    우리가 카카오에서 받는 것은 회원번호와 닉네임뿐이다.
    kakao_rest_api_key: str = ""  # 앱 설정 → 앱 키 → REST API 키 (client_id)
    kakao_client_secret: str = ""  # 카카오 로그인 → 보안 → 코드 (활성화 필요)

    # 프론트엔드 콜백 주소. 카카오 콘솔 등록값과 **정확히** 일치해야 한다.
    #
    # ⚠️ 값은 **하나**다. CORS_ORIGINS 와 헷갈리기 쉽다.
    #      CORS_ORIGINS       허용 목록  → 쉼표로 여러 개
    #      KAKAO_REDIRECT_URI 돌아올 곳  → 하나만
    #
    #    실제로 두 도메인을 쉼표로 이어 넣어 KOE006(Redirect URI 불일치)이
    #    났다. 카카오는 "a,b" 라는 주소를 모르기 때문이다.
    #    실수해도 로그인이 통째로 막히지는 않도록 첫 번째만 쓰고 경고를 남긴다.
    #    (여러 도메인을 받고 싶으면 카카오 콘솔에 여러 개 등록하고,
    #     여기에는 그중 실제로 쓸 하나만 넣는다)
    kakao_redirect_uri: str = ""

    # 우리 세션 토큰 서명 키. 생성: openssl rand -hex 32
    #
    # ⚠️ 비어 있으면 로그인 기능 전체를 끈다. 서명 키 없이 토큰을 발급하면
    #    누구나 위조할 수 있어 로그인이 없느니만 못하다.
    jwt_secret: str = ""

    # 세션 유효 기간(시간). 계약서 한 건을 끝내기에 충분하면 된다.
    jwt_ttl_hours: int = 12

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

    @property
    def kakao_callback_url(self) -> str:
        """
        카카오에 보낼 Redirect URI. 반드시 **하나**여야 한다.

        쉼표가 들어오면 첫 번째만 쓴다. 설정 실수로 로그인이 통째로
        막히는 것보다 낫고, 무엇이 잘못됐는지는 경고 로그와
        GET /health 의 kakao_redirect_uri 로 드러낸다.

        ⚠️ 조용히 고치지 않는다. 조용한 폴백이 가장 나쁘다.
        """
        raw = self.kakao_redirect_uri.strip()
        if "," not in raw:
            return raw

        first = raw.split(",")[0].strip()
        logging.getLogger(__name__).warning(
            "KAKAO_REDIRECT_URI 에 값이 여러 개입니다. 카카오는 하나만 받으므로 "
            "첫 번째만 사용합니다. 환경변수를 하나로 고쳐 주세요. "
            "(여러 도메인은 카카오 콘솔 Redirect URI 목록에 등록하세요)"
        )
        return first

    @property
    def kakao_configured(self) -> bool:
        """
        로그인을 켤 수 있는가.

        ⚠️ 넷 중 하나라도 없으면 끈다. 반쯤 켜진 로그인은 가장 나쁘다 —
           사용자는 로그인했다고 믿는데 실제로는 아무것도 보호되지 않는다.
           설정 여부는 GET /health 의 kakao_login 으로 확인한다.
        """
        return bool(
            self.kakao_rest_api_key
            and self.kakao_client_secret
            and self.kakao_callback_url
            and self.jwt_secret
        )


settings = Settings()
