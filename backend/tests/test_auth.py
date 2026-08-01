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
from urllib.parse import parse_qs, urlparse

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

    async def fake_exchange(code, redirect_uri=None):
        assert code  # 코드가 실제로 전달되는지
        assert redirect_uri
        return "kakao-access-token"

    async def fake_profile(token):
        return {"kakao_id": KAKAO_ID, "nickname": NICKNAME}

    monkeypatch.setattr(kakao, "exchange_code", fake_exchange)
    monkeypatch.setattr(kakao, "fetch_profile", fake_profile)


def _state() -> str:
    url = client.get("/auth/login-url").json()["authorize_url"]
    return parse_qs(urlparse(url).query)["state"][0]


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


def test_로컬_콜백_주소로_로그인을_시작할_수_있다(monkeypatch):
    monkeypatch.setattr(
        settings,
        "kakao_redirect_uri",
        "https://fairsign.example/auth/kakao/callback",
    )
    redirect_uri = "http://localhost:3000/auth/kakao/callback"

    res = client.get("/auth/login-url", params={"redirect_uri": redirect_uri})

    assert res.status_code == 200
    query = parse_qs(urlparse(res.json()["authorize_url"]).query)
    assert query["redirect_uri"] == [redirect_uri]
    state = session.verify(
        query["state"][0],
        purpose=session.PURPOSE_OAUTH_STATE,
    )
    assert state["redirect_uri"] == redirect_uri


def test_허용되지_않은_콜백_주소는_거부한다():
    res = client.get(
        "/auth/login-url",
        params={
            "redirect_uri": "https://attacker.invalid/auth/kakao/callback",
        },
    )

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "INVALID_REDIRECT_URI"


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


def test_토큰_교환에도_로그인_시작과_같은_로컬_콜백을_쓴다(
    kakao_ok, monkeypatch
):
    monkeypatch.setattr(
        settings,
        "kakao_redirect_uri",
        "https://fairsign.example/auth/kakao/callback",
    )
    redirect_uri = "http://localhost:3000/auth/kakao/callback"
    received: dict[str, str | None] = {}

    async def fake_exchange(code, callback_url=None):
        received["code"] = code
        received["redirect_uri"] = callback_url
        return "kakao-access-token"

    monkeypatch.setattr(kakao, "exchange_code", fake_exchange)
    authorize_url = client.get(
        "/auth/login-url",
        params={"redirect_uri": redirect_uri},
    ).json()["authorize_url"]
    state = parse_qs(urlparse(authorize_url).query)["state"][0]

    res = client.post(
        "/auth/kakao/callback",
        json={"code": "local-code", "state": state, "role": "WORKER"},
    )

    assert res.status_code == 200, res.text
    assert received == {
        "code": "local-code",
        "redirect_uri": redirect_uri,
    }


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
    async def boom(code, redirect_uri=None):
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


# ============================================================
# 설정 방어 — KAKAO_REDIRECT_URI 는 하나여야 한다
# ============================================================


def test_리다이렉트_주소를_쉼표로_여러_개_넣어도_로그인이_막히지_않는다(
    monkeypatch, caplog
):
    """
    ⚠️ 실제로 겪은 사고다.

    CORS_ORIGINS 는 쉼표로 여러 개를 받는다. 그래서 KAKAO_REDIRECT_URI 에도
    두 도메인을 쉼표로 이어 넣었고, 카카오는 "a,b" 라는 주소를 모르므로
    KOE006(Redirect URI 불일치)이 났다. 로그인이 통째로 막혔다.

    설정 실수로 기능이 죽는 것보다는 첫 번째를 쓰고 경고를 남기는 편이 낫다.
    다만 **조용히** 고치지는 않는다 — 로그와 /health 에 드러낸다.
    """
    import logging

    first = "https://a.vercel.app/auth/kakao/callback"
    monkeypatch.setattr(
        settings,
        "kakao_redirect_uri",
        f"{first},https://b.vercel.app/auth/kakao/callback",
    )

    with caplog.at_level(logging.WARNING):
        url = client.get("/auth/login-url").json()["authorize_url"]

    # 카카오에는 하나만 나간다
    assert "%2C" not in url, "쉼표가 그대로 나가면 KOE006"
    assert "b.vercel.app" not in url
    # 무엇이 잘못됐는지 알려준다
    assert "여러 개" in caplog.text


def test_health_가_실제_리다이렉트_주소를_보여준다(monkeypatch):
    """
    카카오 콘솔 등록값과 한 글자라도 다르면 KOE006 이 난다.
    로그인 화면까지 가지 않고 여기서 대조할 수 있어야 한다.

    ⚠️ 비밀값이 아니다. 이 주소는 어차피 사용자 브라우저로 나간다.
    """
    monkeypatch.setattr(
        settings, "kakao_redirect_uri", "https://x.vercel.app/auth/kakao/callback"
    )

    body = client.get("/health").json()

    assert body["kakao_redirect_uri"] == "https://x.vercel.app/auth/kakao/callback"
    # 비밀값은 여전히 노출하지 않는다
    assert "test-client-secret" not in str(body)
    assert "jwt" not in str(body).lower()


# ============================================================
# 닉네임 읽기 — 카카오는 두 곳에 담는다
# ============================================================


@pytest.mark.parametrize(
    "payload,expected",
    [
        # 동의항목 기반 (현재 방식)
        ({"kakao_account": {"profile": {"nickname": "가상닉"}}}, "가상닉"),
        # 예전 방식. 앱 설정에 따라 이쪽에만 오는 경우가 있다
        ({"properties": {"nickname": "가상닉"}}, "가상닉"),
        # 둘 다 오면 동의항목 쪽을 쓴다
        (
            {
                "kakao_account": {"profile": {"nickname": "새이름"}},
                "properties": {"nickname": "옛이름"},
            },
            "새이름",
        ),
        # 동의를 거부하면 없다 — 그래도 로그인은 성립해야 한다
        ({}, ""),
        ({"kakao_account": {"profile": {}}}, ""),
        ({"kakao_account": {"profile": {"nickname": "   "}}}, ""),
        ({"properties": {"nickname": None}}, ""),
    ],
)
def test_닉네임을_두_위치에서_모두_찾는다(payload, expected):
    """
    ⚠️ 한 곳만 보면 앱 설정에 따라 닉네임이 비어 보인다.
       실제로 kakao_account.profile 만 읽다가 화면에 "님" 만 뜬 적이 있다.
    """
    assert kakao._read_nickname(payload) == expected


# ============================================================
# 로그인 왕복 전 구간 시뮬레이션
#
# 브라우저를 띄우지 않고 실제 화면이 하는 순서를 그대로 재현한다.
#   ① 로그인 없이 판정까지 된다
#   ② 서명 발송에서 401 로 막힌다
#   ③ 로그인 주소를 받아 state 를 들고 콜백에 온다
#   ④ 토큰으로 보호된 화면이 열린다
#
# ⚠️ 이 순서가 깨지면 사용자는 "로그인했는데 아무것도 안 된다"를 겪는다.
#    화면 코드는 이 계약을 그대로 따라야 한다.
# ============================================================


def _sample_terms() -> dict:
    def f(value=None):
        return {
            "value": value,
            "confidence": "NOT_FOUND" if value is None else "HIGH",
            "source_text": None,
        }

    return {
        "contract_start": f("2026-08-01"),
        "contract_end": f("2026-12-31"),
        "workplace": f("부산 금정구 가상카페"),
        "job_description": f("음료 제조"),
        "work_start_time": f("09:00"),
        "work_end_time": f("15:00"),
        "break_start_time": f("12:00"),
        "break_end_time": f("12:30"),
        "work_days_per_week": f(3),
        "weekly_holiday_day": f("일"),
        "wage_type": f("HOURLY"),
        "wage_amount": f(9500),
        "has_bonus": f("없음"),
        "other_allowance": f("없음"),
        "payday": f("매월 10일"),
        "payment_method": f("계좌입금"),
        "employer_business_name": f("가상카페"),
        "employer_phone": f(None),
        "employer_address": f(None),
        "employer_name": f("홍길동"),
        "worker_address": f(None),
        "worker_contact": f(None),
        "worker_name": f("김가상"),
    }


def test_로그인_왕복_전_구간이_이어진다(kakao_ok):
    from app.store import MemoryDocumentStore, set_store

    set_store(MemoryDocumentStore())
    terms = _sample_terms()

    # ① 로그인 없이 판정·문구까지 된다.
    #    여기서 로그인을 요구하면 열여섯 살이 벽을 넘지 못한다.
    for path in ("/contracts/validate", "/contracts/message"):
        assert client.post(path, json={"terms": terms}).status_code == 200, path

    # ② 서명 발송은 401. 화면은 이걸 보고 로그인 안내를 띄운다.
    blocked = client.post(
        "/contracts/analyze-sign",
        json={
            "terms": terms,
            "worker_name": "김가상",
            "worker_email": "w@example.com",
            "employer_name": "홍길동",
            "employer_email": "e@example.com",
            "entry_path": "PHOTO",
            "confirmed_fields": [],
            "proceed_with_violations": True,
        },
    )
    assert blocked.status_code == 401
    assert blocked.json()["detail"]["code"] == "LOGIN_REQUIRED"

    # ③ 로그인 주소를 받는다. 화면은 여기 담긴 state 를 그대로 되돌려준다.
    authorize_url = client.get("/auth/login-url").json()["authorize_url"]
    state = authorize_url.split("state=")[1]

    logged_in = client.post(
        "/auth/kakao/callback",
        json={"code": "kakao-returned-this", "state": state, "role": "WORKER"},
    )
    assert logged_in.status_code == 200, logged_in.text
    headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

    # ④ 이제 보호된 화면이 열린다.
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.get("/contracts", headers=headers).status_code == 200
    assert client.get("/contracts", headers=headers).json() == []


def test_같은_인가_코드로는_state_를_재사용할_수_없다(kakao_ok):
    """
    ⚠️ state 는 한 번 쓰고 버리는 값이 아니라 서명된 토큰이라 만료 전까지
       유효하다. 그래서 화면이 재시도할 때 **같은 code 를 다시 보내면 안 된다** —
       카카오 인가 코드가 1회용이기 때문이다.
       화면은 로그인 주소를 새로 받아 처음부터 진행해야 한다.
       (web/app/auth/kakao/callback/page.tsx 의 retry 참고)

    이 테스트는 그 계약을 문서화한다. state 자체는 재사용 가능하므로
    화면 쪽 재시도 구현이 유일한 방어선이다.
    """
    state = _state()

    first = client.post(
        "/auth/kakao/callback",
        json={"code": "code-1", "state": state, "role": "WORKER"},
    )
    assert first.status_code == 200

    # 백엔드는 state 를 다시 받아도 통과시킨다. 막는 것은 카카오의 code 다.
    second = client.post(
        "/auth/kakao/callback",
        json={"code": "code-2", "state": state, "role": "WORKER"},
    )
    assert second.status_code == 200
