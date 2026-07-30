"""
로그인·세션 테스트.

⚠️ 카카오 서버를 실제로 호출하지 않는다. 토큰 교환과 프로필 조회는
   monkeypatch 로 대체하고, **우리 쪽 로직**만 검증한다.
   - state 서명 검증(CSRF)
   - 토큰 용도 분리
   - 세션 만료
   - 로그에 개인정보가 남지 않는가
"""

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import kakao, session, users
from app.config import settings
from app.main import app

client = TestClient(app)

KAKAO_ID = "1234567890"
NICKNAME = "가상닉네임"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """카카오 설정이 갖춰진 상태를 흉내낸다. 실제 키를 쓰지 않는다."""
    monkeypatch.setattr(settings, "kakao_rest_api_key", "test-rest-key")
    monkeypatch.setattr(settings, "kakao_client_secret", "test-client-secret")
    monkeypatch.setattr(
        settings, "kakao_redirect_uri", "http://localhost:3000/auth/kakao/callback"
    )
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-" + "0" * 40)
    users.clear_memory()
    yield
    users.clear_memory()


@pytest.fixture
def kakao_ok(monkeypatch):
    """카카오가 정상 응답하는 상태."""

    async def fake_exchange(code):
        assert code  # 코드가 실제로 전달되는지
        return "kakao-access-token"

    async def fake_profile(token):
        return {"kakao_id": KAKAO_ID, "nickname": NICKNAME}

    monkeypatch.setattr(kakao, "exchange_code", fake_exchange)
    monkeypatch.setattr(kakao, "fetch_profile", fake_profile)


def _state() -> str:
    return client.get("/auth/login-url").json()["authorize_url"].split("state=")[1]


# ============================================================
# 로그인 주소
# ============================================================


def test_로그인_주소에_비밀키가_들어가지_않는다():
    """
    ⚠️ client_id(REST API 키)는 공개돼도 되지만 client_secret 은 아니다.
       사용자 브라우저로 나가는 주소에 절대 들어가면 안 된다.
    """
    url = client.get("/auth/login-url").json()["authorize_url"]

    assert url.startswith("https://kauth.kakao.com/oauth/authorize")
    assert "test-rest-key" in url  # client_id 는 있어야 한다
    assert "test-client-secret" not in url  # 비밀키는 절대 안 된다


def test_닉네임만_요청한다():
    """
    ⚠️ 이메일·전화번호를 요청하지 않는다. 비즈 앱 심사가 필요할 뿐 아니라,
       우리에게 필요하지 않다. 서명받을 이메일은 사용자가 직접 입력한다.
       필요하지 않은 개인정보는 받지 않는 것이 가장 확실한 보호다.
    """
    url = client.get("/auth/login-url").json()["authorize_url"]

    assert "profile_nickname" in url
    assert "account_email" not in url


def test_설정이_없으면_로그인을_켜지_않는다(monkeypatch):
    """
    ⚠️ 반쯤 켜진 로그인이 가장 나쁘다. 사용자는 로그인했다고 믿는데
       실제로는 아무것도 보호되지 않는다.
    """
    monkeypatch.setattr(settings, "jwt_secret", "")

    res = client.get("/auth/login-url")

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "LOGIN_UNAVAILABLE"


# ============================================================
# 콜백
# ============================================================


def test_로그인_성공하면_세션_토큰을_준다(kakao_ok):
    res = client.post(
        "/auth/kakao/callback",
        json={"code": "test-code", "state": _state(), "role": "WORKER"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["nickname"] == NICKNAME
    assert body["user"]["user_id"] == f"kakao:{KAKAO_ID}"

    # 발급된 토큰으로 /auth/me 가 된다
    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["user_id"] == f"kakao:{KAKAO_ID}"


def test_우리가_발급하지_않은_state_는_거부한다(kakao_ok):
    """
    ⚠️ CSRF 방어. state 검증이 없으면 공격자가 자기 계정의 인가 코드로
       피해자를 로그인시킬 수 있다(로그인 CSRF).
    """
    res = client.post(
        "/auth/kakao/callback",
        json={"code": "test-code", "state": "attacker-made-this", "role": "WORKER"},
    )

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "INVALID_STATE"


def test_만료된_state_는_거부한다(kakao_ok):
    expired = session.issue(
        "nonce",
        purpose=session.PURPOSE_OAUTH_STATE,
        ttl=timedelta(seconds=-1),
    )

    res = client.post(
        "/auth/kakao/callback",
        json={"code": "test-code", "state": expired, "role": "WORKER"},
    )

    assert res.status_code == 400


def test_state_토큰을_세션_토큰으로_쓸_수_없다():
    """
    ⚠️ 두 토큰은 같은 키로 서명된다. 용도(purpose) 구분이 없으면
       수명이 짧은 state 토큰을 세션 토큰으로 제출할 수 있다.
    """
    state = session.issue(
        "nonce", purpose=session.PURPOSE_OAUTH_STATE, ttl=timedelta(minutes=10)
    )

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {state}"})

    assert res.status_code == 401


def test_위조된_토큰은_거부한다():
    forged = session.issue("kakao:침입자")
    tampered = forged[:-3] + ("aaa" if not forged.endswith("aaa") else "bbb")

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})

    assert res.status_code == 401


def test_카카오가_실패하면_502로_알린다(monkeypatch):
    async def boom(code):
        raise kakao.KakaoError("카카오 로그인에 실패했습니다. 다시 시도해 주세요")

    monkeypatch.setattr(kakao, "exchange_code", boom)

    res = client.post(
        "/auth/kakao/callback",
        json={"code": "test-code", "state": _state(), "role": "WORKER"},
    )

    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "KAKAO_FAILED"


# ============================================================
# 역할
# ============================================================


def test_재로그인해도_바꾼_역할이_유지된다(kakao_ok):
    """
    ⚠️ 로그인할 때마다 role 을 기본값으로 덮어쓰면
       사용자가 바꾼 역할이 계속 되돌아간다.
    """
    first = client.post(
        "/auth/kakao/callback",
        json={"code": "c1", "state": _state(), "role": "WORKER"},
    ).json()
    headers = {"Authorization": f"Bearer {first['access_token']}"}

    client.patch("/auth/me/role", json={"role": "EMPLOYER"}, headers=headers)

    second = client.post(
        "/auth/kakao/callback",
        json={"code": "c2", "state": _state(), "role": "WORKER"},
    ).json()

    assert second["user"]["role"] == "EMPLOYER"


# ============================================================
# 로그
# ============================================================


def test_로그인_로그에_회원번호와_닉네임이_남지_않는다(kakao_ok, caplog):
    """
    AGENTS.md: "API 키, 계약서 내용, 개인정보를 로그에 남기지 않습니다."
    """
    import logging

    with caplog.at_level(logging.INFO):
        client.post(
            "/auth/kakao/callback",
            json={"code": "test-code", "state": _state(), "role": "WORKER"},
        )

    assert KAKAO_ID not in caplog.text
    assert NICKNAME not in caplog.text


# ============================================================
# 세션 모듈 단위
# ============================================================


def test_세션은_만료된다():
    token = session.issue("kakao:1", ttl=timedelta(seconds=-1))

    with pytest.raises(session.SessionError):
        session.verify(token)


def test_비밀키가_없으면_토큰을_발급하지_않는다(monkeypatch):
    """
    ⚠️ 키 없이 발급하면 누구나 위조할 수 있다. 로그인이 없느니만 못하다.
    """
    monkeypatch.setattr(settings, "jwt_secret", "")

    with pytest.raises(session.SessionError):
        session.issue("kakao:1")


def test_사용자_ID에_제공자를_붙인다():
    """
    나중에 애플·구글 로그인이 붙어도 회원번호가 겹쳐
    다른 사람이 같은 계정이 되는 일이 없어야 한다.
    """
    assert users.kakao_user_id("123") == "kakao:123"


def test_사용자_기록에_이메일이_없다(kakao_ok):
    client.post(
        "/auth/kakao/callback",
        json={"code": "test-code", "state": _state(), "role": "WORKER"},
    )

    user = asyncio.run(users.get(f"kakao:{KAKAO_ID}"))

    assert set(user) == {
        "user_id",
        "provider",
        "nickname",
        "role",
        "created_at",
        "last_login_at",
    }
