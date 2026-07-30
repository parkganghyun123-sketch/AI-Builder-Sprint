"""
카카오 로그인 연동 (C 담당)

--- 무엇을 받고 무엇을 받지 않는가 ---

받는 것:  회원번호(id), 닉네임
받지 않는 것: 이메일, 전화번호, 생년월일, 프로필 이미지

이메일 동의항목은 비즈 앱 전환(사업자등록번호 또는 담당자 심사)이 필요하고,
무엇보다 **우리에게 필요하지 않다.** 서명받을 이메일은 사용자가 화면에서
직접 입력한다. 근로자의 카카오 이메일과 계약서에 쓸 이메일이 같으리라는
보장도 없다.

⚠️ 필요하지 않은 개인정보는 받지 않는다. 받는 순간 보관 기간과 삭제 책임이
   생기고, 유출 시 피해 범위가 넓어진다.

참고: https://developers.kakao.com/docs/ko/kakaologin/rest-api
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.config import settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
PROFILE_URL = "https://kapi.kakao.com/v2/user/me"

# 닉네임만 요청한다. 콘솔의 동의항목 설정과 일치해야 한다.
SCOPE = "profile_nickname"


class KakaoError(Exception):
    pass


def build_authorize_url(state: str) -> str:
    """사용자를 보낼 카카오 로그인 주소."""
    if not settings.kakao_configured:
        raise KakaoError("카카오 로그인이 설정되지 않았습니다")

    query = urlencode(
        {
            "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            # ⚠️ state 는 CSRF 방어다. 우리가 서명한 토큰을 넣고
            #    콜백에서 서명을 검증한다(routers/auth.py 참고).
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def exchange_code(code: str) -> str:
    """
    인가 코드 → 카카오 액세스 토큰.

    ⚠️ client_secret 은 콘솔에서 '사용함' 으로 켜져 있을 때만 보내야 한다.
       설정과 어긋나면 KOE010 이 난다. 우리는 항상 켜두고 항상 보낸다.
    """
    if not settings.kakao_configured:
        raise KakaoError("카카오 로그인이 설정되지 않았습니다")

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "client_secret": settings.kakao_client_secret,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(TOKEN_URL, data=data)
    except httpx.HTTPError:
        raise KakaoError("카카오 인증 서버에 연결하지 못했습니다") from None

    if res.status_code >= 400:
        # ⚠️ 응답 본문에 client_secret 이 되비쳐 오지는 않지만,
        #    카카오 오류 코드는 진단에 필요하므로 로그에만 남긴다.
        #    사용자에게는 일반 문구를 준다.
        log.warning("카카오 토큰 교환 실패: HTTP %s", res.status_code)
        raise KakaoError("카카오 로그인에 실패했습니다. 다시 시도해 주세요")

    try:
        token = res.json()["access_token"]
    except (ValueError, KeyError, TypeError):
        raise KakaoError("카카오 응답을 확인하지 못했습니다") from None

    return token


async def fetch_profile(access_token: str) -> dict:
    """
    액세스 토큰 → {"kakao_id": str, "nickname": str}

    닉네임은 없을 수 있다(동의 거부). 그래도 로그인은 성립해야 하므로
    빈 문자열로 두고 화면에서 기본값을 쓴다.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                # 필요한 항목만 명시적으로 요청한다.
                params={"property_keys": '["kakao_account.profile"]'},
            )
    except httpx.HTTPError:
        raise KakaoError("카카오 사용자 정보를 가져오지 못했습니다") from None

    if res.status_code >= 400:
        log.warning("카카오 프로필 조회 실패: HTTP %s", res.status_code)
        raise KakaoError("카카오 사용자 정보를 가져오지 못했습니다")

    try:
        payload = res.json()
        kakao_id = str(payload["id"])
    except (ValueError, KeyError, TypeError):
        raise KakaoError("카카오 응답을 확인하지 못했습니다") from None

    nickname = ""
    account = payload.get("kakao_account") or {}
    profile = account.get("profile") or {}
    if isinstance(profile.get("nickname"), str):
        nickname = profile["nickname"].strip()[:50]

    return {"kakao_id": kakao_id, "nickname": nickname}
