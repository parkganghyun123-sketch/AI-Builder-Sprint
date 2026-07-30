"""
인증 의존성 (C 담당)

--- 로그인을 언제 요구하는가 ---

  로그인 없이 가능:  사진 업로드 · 조건 확인 · 법정 기준 판정 ·
                    말 꺼내기 문구 복사 · PDF 미리보기
  로그인 필요:       서명 발송 · 문서 상태 조회 · 보관함

⚠️ 판정까지 로그인을 요구하지 않는 것은 편의가 아니라 설계다.
   열여섯 살이 첫 계약서를 확인하려고 가입부터 해야 한다면
   그 벽을 넘지 못한다. 로그인은 "내 문서"를 구분해야 하는
   시점에서 처음 필요해진다.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.auth import session, users

log = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def optional_user(request: Request) -> dict | None:
    """
    토큰이 있으면 사용자를, 없거나 잘못됐으면 None.

    로그인 없이도 되는 화면에서 "로그인했으면 이름을 보여주는" 정도에 쓴다.
    ⚠️ 접근 통제에 쓰지 말 것. 통제에는 require_user 를 쓴다.
    """
    token = _bearer_token(request)
    if token is None:
        return None
    try:
        payload = session.verify(token)
    except session.SessionError:
        return None
    return await users.get(payload["sub"])


async def require_user(request: Request) -> dict:
    """
    로그인한 사용자. 없으면 401.

    ⚠️ 401 과 함께 code 를 준다. 프론트엔드가 "로그인이 필요합니다" 화면과
       "세션이 만료됐습니다" 화면을 구분해 보여줄 수 있어야 한다.
       둘 다 "요청 실패"로 뭉뚱그리면 사용자는 무엇을 해야 할지 모른다.
    """
    token = _bearer_token(request)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "LOGIN_REQUIRED",
                "message": "이 단계는 로그인이 필요합니다.",
            },
        )

    try:
        payload = session.verify(token)
    except session.SessionError as error:
        raise HTTPException(
            status_code=401,
            detail={"code": "SESSION_INVALID", "message": str(error)},
        ) from None

    user = await users.get(payload["sub"])
    if user is None:
        # 토큰은 유효한데 사용자가 없다. DB를 비웠거나 탈퇴한 경우.
        log.warning("세션은 유효하나 사용자 없음")
        raise HTTPException(
            status_code=401,
            detail={
                "code": "SESSION_INVALID",
                "message": "세션을 확인할 수 없습니다. 다시 로그인해 주세요.",
            },
        )
    return user


CurrentUser = Annotated[dict, Depends(require_user)]
OptionalUser = Annotated[dict | None, Depends(optional_user)]
