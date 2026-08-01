"""
로그인 라우터 (C 담당)

  GET  /auth/login-url        카카오 로그인 주소 발급 (state 포함)
  POST /auth/kakao/callback   인가 코드 → 우리 세션 토큰
  GET  /auth/me               현재 로그인 사용자
  PATCH /auth/me/role         역할 변경 (WORKER / EMPLOYER)

⚠️ 프론트엔드에는 카카오 키를 두지 않는다. 로그인 주소를 백엔드가
   만들어 주므로 client_id·redirect_uri 가 한 곳에만 있다.
   두 곳에 두면 반드시 어긋난다(anchor 좌표에서 겪은 것과 같은 실수다).
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth import kakao, session, users
from app.auth.deps import CurrentUser
from app.auth.users import UserRole
from app.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# state 토큰 수명. 로그인 화면에서 머뭇거릴 시간은 충분하고,
# 훔친 state 를 나중에 쓰기에는 짧다.
STATE_TTL = timedelta(minutes=10)
KAKAO_CALLBACK_PATH = "/auth/kakao/callback"


def _require_configured() -> None:
    if not settings.kakao_configured:
        # ⚠️ 어떤 키가 없는지 알려주지 않는다. 설정 상태는 /health 에서 본다.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_UNAVAILABLE",
                "message": "로그인 기능이 아직 준비되지 않았습니다.",
            },
        )


class LoginUrlResponse(BaseModel):
    authorize_url: str


def _callback_url(redirect_uri: str | None) -> str:
    """카카오 콘솔에 등록할 수 있는 우리 프론트 콜백만 허용한다."""
    requested = (redirect_uri or settings.kakao_callback_url).strip()
    allowed = {
        f"{origin.rstrip('/')}{KAKAO_CALLBACK_PATH}"
        for origin in settings.allowed_origins
    }
    allowed.add(settings.kakao_callback_url)

    if requested not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REDIRECT_URI",
                "message": "이 주소에서는 로그인을 시작할 수 없습니다.",
            },
        )
    return requested


@router.get("/login-url", response_model=LoginUrlResponse)
async def login_url(redirect_uri: str | None = None) -> LoginUrlResponse:
    """
    카카오 로그인 주소를 만든다.

    state 는 우리가 서명한 짧은 토큰이다.
      · 콜백에서 서명을 검증하므로 제3자가 만든 state 로는 로그인할 수 없다(CSRF)
      · 10분 뒤 만료되므로 훔친 state 를 나중에 쓸 수 없다
      · 프론트엔드가 따로 저장할 필요가 없다 — 서명이 곧 증거다
    """
    _require_configured()
    callback_url = _callback_url(redirect_uri)
    state = session.issue(
        secrets.token_urlsafe(16),
        purpose=session.PURPOSE_OAUTH_STATE,
        ttl=STATE_TTL,
        redirect_uri=callback_url,
    )
    return LoginUrlResponse(
        authorize_url=kakao.build_authorize_url(state, callback_url)
    )


class CallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=2048)
    # 처음 로그인하는 사용자의 기본 역할. 이미 있는 사용자는 바뀌지 않는다.
    role: UserRole = UserRole.WORKER


class MeResponse(BaseModel):
    user_id: str
    nickname: str
    role: UserRole


class CallbackResponse(BaseModel):
    access_token: str
    user: MeResponse


@router.post("/kakao/callback", response_model=CallbackResponse)
async def kakao_callback(body: CallbackRequest) -> CallbackResponse:
    """
    인가 코드를 우리 세션 토큰으로 바꾼다.

    ⚠️ 인가 코드는 프론트엔드가 받아서 여기로 넘긴다. 코드 자체로는
       아무것도 할 수 없고, client_secret 이 있어야 토큰이 나온다.
       그 비밀은 백엔드에만 있다.
    """
    _require_configured()

    # 1) state 검증 — 우리가 발급한 것인가, 아직 유효한가
    try:
        state_payload = session.verify(
            body.state,
            purpose=session.PURPOSE_OAUTH_STATE,
        )
    except session.SessionError:
        log.warning("로그인 state 검증 실패")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_STATE",
                "message": "로그인 요청이 만료되었거나 올바르지 않습니다. 다시 시도해 주세요.",
            },
        ) from None

    # 2) 인가 코드 → 카카오 토큰 → 프로필
    callback_url = _callback_url(state_payload.get("redirect_uri"))

    try:
        access_token = await kakao.exchange_code(body.code, callback_url)
        profile = await kakao.fetch_profile(access_token)
    except kakao.KakaoError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "KAKAO_FAILED", "message": str(error)},
        ) from None

    # 3) 우리 사용자로 만들거나 갱신
    user_id = users.kakao_user_id(profile["kakao_id"])
    user = await users.upsert(
        user_id,
        provider="kakao",
        nickname=profile["nickname"],
        default_role=body.role,
    )

    # ⚠️ 로그에 회원번호나 닉네임을 남기지 않는다.
    log.info("로그인 성공 (provider=kakao)")

    return CallbackResponse(
        access_token=session.issue(user_id),
        user=MeResponse(
            user_id=user["user_id"],
            nickname=user["nickname"],
            role=UserRole(user["role"]),
        ),
    )


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        user_id=user["user_id"],
        nickname=user["nickname"],
        role=UserRole(user["role"]),
    )


class RoleRequest(BaseModel):
    role: UserRole


@router.patch("/me/role", response_model=MeResponse)
async def change_role(body: RoleRequest, user: CurrentUser) -> MeResponse:
    """
    역할 변경.

    ⚠️ 역할은 화면 흐름을 정할 뿐 권한이 아니다. 사업주로 바꿨다고
       남의 계약서를 볼 수 있게 되지 않는다. 접근 통제는 문서
       소유자(owner_id)로만 한다.
    """
    await users.set_role(user["user_id"], body.role)
    return MeResponse(
        user_id=user["user_id"],
        nickname=user["nickname"],
        role=body.role,
    )
