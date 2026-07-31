"""
세션 토큰 발급·검증 (C 담당)

카카오는 "이 사람이 누구인가"만 알려준다. 그 뒤로 우리 API를 부를 때마다
카카오에 다시 묻지 않으려고 우리가 서명한 토큰을 발급한다.

--- 왜 쿠키가 아니라 Bearer 토큰인가 ---

프론트(vercel.app)와 백엔드(railway.app)가 다른 도메인이다.
쿠키를 쓰려면 SameSite=None; Secure 인 서드파티 쿠키가 되는데,
Safari·브라우저 추적 방지 정책에 따라 조용히 차단된다.
데모 중에 "내 폰에서만 로그인이 안 되는" 상황을 만들 수 없다.

대신 Authorization: Bearer 헤더로 보낸다. 저장은 sessionStorage —
탭을 닫으면 사라지므로 공용 PC에서 로그인이 남지 않는다.
(localStorage 는 탭을 닫아도 남는다. 알바생이 PC방에서 쓸 수 있다.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

log = logging.getLogger(__name__)

ALGORITHM = "HS256"

# 토큰 용도. 로그인 세션과 OAuth state 는 같은 키로 서명하지만
# 서로 바꿔 쓸 수 없어야 한다.
#
# ⚠️ 용도 구분이 없으면 state 토큰을 세션 토큰으로 제출하는 공격이 가능하다.
PURPOSE_SESSION = "session"
PURPOSE_OAUTH_STATE = "oauth_state"


class SessionError(Exception):
    """토큰이 없거나, 만료됐거나, 위조됐다."""


def _secret() -> str:
    if not settings.jwt_secret:
        # 키 없이 토큰을 발급하면 누구나 위조할 수 있다.
        # 로그인이 없느니만 못하므로 여기서 멈춘다.
        raise SessionError("JWT_SECRET 미설정")
    return settings.jwt_secret


def issue(
    subject: str,
    *,
    purpose: str = PURPOSE_SESSION,
    ttl: timedelta | None = None,
    **claims,
) -> str:
    """서명된 토큰을 만든다. subject 는 우리 내부 사용자 ID."""
    now = datetime.now(timezone.utc)
    expires = ttl or timedelta(hours=settings.jwt_ttl_hours)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "iat": now,
        "exp": now + expires,
        **claims,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def verify(token: str, *, purpose: str = PURPOSE_SESSION) -> dict:
    """
    토큰을 검증하고 payload 를 돌려준다.

    ⚠️ 실패 원인을 호출자에게 그대로 노출하지 않는다.
       "만료됨"과 "서명 불일치"를 구분해 알려주면 공격자에게 정보를 준다.
       사용자에게는 "다시 로그인해 주세요" 하나면 충분하다.
    """
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise SessionError("세션이 만료되었습니다") from None
    except jwt.InvalidTokenError:
        log.warning("세션 토큰 검증 실패")
        raise SessionError("세션을 확인할 수 없습니다") from None

    if payload.get("purpose") != purpose:
        # 예: OAuth state 토큰을 세션 토큰으로 제출한 경우
        log.warning(
            "토큰 용도 불일치: 기대=%s 실제=%s", purpose, payload.get("purpose")
        )
        raise SessionError("세션을 확인할 수 없습니다")

    if not payload.get("sub"):
        raise SessionError("세션을 확인할 수 없습니다")

    return payload
