"""
HTTP 계층 관문 테스트.

--- 왜 이 파일이 필요한가 ---

기존 테스트 208개는 라우터 함수를 **직접 호출**한다. 그래서 프론트엔드가
실제로 보내는 요청 본문이 백엔드 기대와 맞는지는 아무도 검증하지 않았다.

그 틈으로 실제 결함이 지나갔다.
  프론트엔드가 `confirmed_fields` 를 보내지 않아 /contracts/analyze-sign 이
  **항상 409** 로 막혔는데, 208개 테스트는 전부 통과했다.
  화면에서 서명 발송이 100% 실패하는 동안 CI는 초록색이었다.

그래서 이 파일은 TestClient로 **실제 HTTP 요청**을 보낸다.
Pydantic 검증(422)과 관문 응답(409/413/400)의 형태까지 고정한다.

⚠️ 외부 유료 API는 절대 호출하지 않는다. 모두싸인은 monkeypatch로 대체한다.
⚠️ 가상 인물만 사용한다 (AGENTS.md).
"""

import sys
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

# WeasyPrint 네이티브 의존성 없이도 관문 로직을 검증할 수 있어야 한다.
# 이 파일은 PDF 내용을 보지 않는다.
_pdf_stub = ModuleType("app.pdf.generator")
_pdf_stub.render_contract_pdf = lambda *a, **k: b"%PDF-stub"
_pdf_stub.verify_anchors = lambda pdf: {}
sys.modules.setdefault("app.pdf.generator", _pdf_stub)

from app.auth.deps import require_user  # noqa: E402
from app.main import app  # noqa: E402
from app.review.fields import build_review_items  # noqa: E402
from app.routers import contracts  # noqa: E402
from app.schemas import ContractTerms  # noqa: E402
from app.store import MemoryDocumentStore, set_store  # noqa: E402

client = TestClient(app)

WORKER = "김가상"
EMPLOYER = "홍길동"

TEST_USER = {
    "user_id": "kakao:test-1",
    "provider": "kakao",
    "nickname": "가상 사용자",
    "role": "WORKER",
}


@pytest.fixture(autouse=True)
def logged_in():
    """
    로그인한 상태를 기본으로 둔다.

    이 파일의 테스트는 **관문 로직**을 검증한다. 로그인 자체는
    tests/test_auth.py 가 검증하므로 여기서는 의존성을 대체한다.

    ⚠️ 그렇다고 "로그인 없이도 통과한다"를 놓치면 안 된다.
       아래 test_로그인_없이는_서명을_보낼_수_없다 가 오버라이드를 걷어내고
       확인한다.
    """
    app.dependency_overrides[require_user] = lambda: dict(TEST_USER)
    yield
    app.dependency_overrides.pop(require_user, None)


def _f(value=None, confidence: str | None = None) -> dict:
    """ExtractedField JSON. 값이 없으면 NOT_FOUND."""
    return {
        "value": value,
        "confidence": confidence or ("NOT_FOUND" if value is None else "HIGH"),
        "source_text": None,
    }


def _terms(**overrides) -> dict:
    """
    사용자가 확인·수정을 마친 계약 조건.

    시급 9,500원 — 2026년 최저임금(10,320원) 미달이다.
    위반이 하나 있는 상태를 기본으로 두어야 `proceed_with_violations`
    관문까지 함께 검증할 수 있다.
    """
    terms = {
        "contract_start": _f("2026-08-01"),
        "contract_end": _f("2026-12-31"),
        "workplace": _f("부산 금정구 가상카페"),
        "job_description": _f("음료 제조 및 매장 관리"),
        "work_start_time": _f("09:00"),
        "work_end_time": _f("15:00"),
        "break_start_time": _f("12:00"),
        "break_end_time": _f("12:30"),
        "work_days_per_week": _f(3),
        "weekly_holiday_day": _f("일"),
        "wage_type": _f("HOURLY"),
        "wage_amount": _f(9500),
        "has_bonus": _f("없음"),
        "other_allowance": _f("없음"),
        "payday": _f("매월 10일"),
        "payment_method": _f("근로자 명의 예금통장 입금"),
        "employer_business_name": _f("가상카페"),
        "employer_phone": _f("051-000-0000"),
        "employer_address": _f("부산 금정구"),
        "employer_name": _f(EMPLOYER),
        "worker_address": _f("부산 금정구"),
        "worker_contact": _f("010-0000-0000"),
        "worker_name": _f(WORKER),
    }
    terms.update(overrides)
    return terms


def _must_confirm(terms: dict) -> list[str]:
    """review-items 가 반드시 확인하라고 지정하는 항목 전체."""
    items = build_review_items(ContractTerms(**terms))
    return [i["field"] for i in items if i["priority"] == "high"]


def _body(terms: dict | None = None, **overrides) -> dict:
    terms = terms if terms is not None else _terms()
    body = {
        "terms": terms,
        "worker_birth_date": None,
        "worker_name": WORKER,
        "worker_email": "worker@example.com",
        "employer_name": EMPLOYER,
        "employer_email": "owner@example.com",
        "entry_path": "PHOTO",
        "confirmed_fields": [],
        "proceed_with_violations": False,
    }
    body.update(overrides)
    return body


@pytest.fixture
def no_provider_call(monkeypatch):
    """모두싸인이 호출되면 즉시 실패한다. 관문이 새는지 확인하는 데 쓴다."""

    async def fail(**kwargs):
        raise AssertionError("관문을 통과하기 전에 서명 요청이 발송됐다")

    monkeypatch.setattr(contracts.modusign, "request_signature", fail)


@pytest.fixture
def memory_store():
    """
    항상 빈 메모리 저장소를 심는다.

    ⚠️ DATABASE_URL 이 설정된 환경에서 테스트를 돌려도 실제 DB를
       건드리지 않아야 한다.
    """
    store = MemoryDocumentStore()
    set_store(store)
    return store


@pytest.fixture
def fake_provider(monkeypatch, memory_store):
    """서명 요청을 가짜로 성공시킨다. 호출 인자를 기록한다."""
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return {"id": "TEST-DOC-1", "status": "ON_GOING"}

    monkeypatch.setattr(contracts.modusign, "request_signature", fake)
    monkeypatch.setattr(contracts, "render_contract_pdf", lambda *a, **k: b"%PDF-stub")
    return calls


# ============================================================
# 1. 확인 관문 — 프론트엔드가 confirmed_fields 를 빼먹으면 막힌다
# ============================================================


def test_confirmed_fields_누락은_409_UNCONFIRMED_FIELDS(no_provider_call):
    """
    ⚠️ 이 테스트가 실패하면 화면에서 서명 발송이 안 되고 있는 것이다.

    프론트엔드는 /contracts/review-items 의 must_confirm 을 전부
    confirmed_fields 에 담아 보내야 한다. 빠지면 여기서 막힌다.
    """
    res = client.post("/contracts/analyze-sign", json=_body())

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "UNCONFIRMED_FIELDS"
    # 어떤 항목을 확인해야 하는지 화면에 보여줄 수 있어야 한다.
    assert detail["fields"], "확인할 항목 목록이 비어 있으면 사용자가 고칠 수 없다"
    assert detail["hint"]


def test_위반_강행_플래그로도_확인_관문은_넘지_못한다(no_provider_call):
    """
    proceed_with_violations 는 **법정 기준 위반**을 알고 진행하는 플래그다.
    '사람이 값을 확인했는가'를 건너뛰는 수단이 아니다.
    확인되지 않은 값으로 내린 판정은 그 판정 자체를 믿을 수 없다.
    """
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(proceed_with_violations=True),
    )

    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "UNCONFIRMED_FIELDS"


# ============================================================
# 2. 이름 불일치 관문
# ============================================================


def test_계약서_이름과_입력_이름이_다르면_409_NAME_MISMATCH(no_provider_call):
    """
    ⚠️ 코드는 어느 쪽이 맞는지 모른다. 그래서 고르지 않고 되돌린다.

    실측에서 AI가 '박강현'을 '박강헌'으로 읽었지만, 반대로 사용자가
    입력을 틀렸을 수도, 종이에 정말 다른 이름이 적혀 있었을 수도 있다.
    화면이 두 값을 나란히 보여줄 수 있도록 둘 다 응답에 담아야 한다.
    """
    terms = _terms()
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(
            terms,
            worker_name="김가상아님",
            confirmed_fields=_must_confirm(terms),
        ),
    )

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "NAME_MISMATCH"

    conflict = next(c for c in detail["conflicts"] if c["field"] == "worker_name")
    assert conflict["on_contract"] == WORKER  # 계약서에서 읽은 값
    assert conflict["typed"] == "김가상아님"  # 입력한 값


# ============================================================
# 3. 값 자체가 계약으로 성립하지 않는 경우
# ============================================================


def test_시급_0원은_422로_막고_문서를_만들지_않는다(no_provider_call):
    """
    0원은 저임금 계약이 아니라 입력 오류다.
    최저임금 미달(경고)과 달리 알고도 진행할 수 없다.
    """
    terms = _terms(wage_amount=_f(0, "HIGH"))
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(
            terms,
            confirmed_fields=_must_confirm(terms),
            proceed_with_violations=True,
        ),
    )

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "INVALID_CONTRACT_VALUES"
    assert "wage_amount" in detail["blocking_fields"]


# ============================================================
# 4. 정상 경로 — 관문을 모두 통과하면 발송된다
# ============================================================


def test_확인_완료_후_위반_강행하면_200으로_발송된다(fake_provider):
    terms = _terms()
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(
            terms,
            confirmed_fields=_must_confirm(terms),
            proceed_with_violations=True,
        ),
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["document_id"] == "TEST-DOC-1"
    assert payload["status"] == "ON_GOING"

    # 판정 결과를 함께 돌려줘야 화면이 무엇을 알고 진행했는지 보여줄 수 있다.
    problems = [
        c["code"]
        for c in payload["report"]["checks"]
        if c["status"] in ("VIOLATION", "MISSING")
    ]
    assert "MINIMUM_WAGE" in problems

    assert len(fake_provider) == 1
    # 문서 제목에 이름을 넣지 않는다 — 모두싸인 문서 목록·메일 제목에 노출된다.
    assert WORKER not in fake_provider[0]["title"]


def test_확인_완료_후_위반_미강행이면_409로_안내한다(no_provider_call):
    """최저임금 미달은 사실이다. 막되, 알고 진행할 길을 함께 알려줘야 한다."""
    terms = _terms()
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(terms, confirmed_fields=_must_confirm(terms)),
    )

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "최저임금" in detail["problems"]
    # ⚠️ 문구를 통째로 비교하지 않는다. 지켜야 하는 건 "그대로 진행할 수
    #    있다"는 사실을 알려준다는 것이지 특정 표현이 아니다.
    #    (예전에는 hint 에 API 파라미터명이 적혀 있었다 — 사용자에게는 무의미하다)
    assert "진행" in detail["hint"]
    assert "proceed_with_violations" not in detail["hint"]


def test_발송한_문서는_이력에_남는다(fake_provider, memory_store):
    """
    ⚠️ 이 테스트가 실패하면 웹훅이 조용히 죽는다.

    webhook() 은 이력에 없는 문서를 그냥 무시한다.
    발송 경로가 이력을 남기지 않으면 모두싸인 이벤트가 전부 버려지고,
    상태는 사용자가 화면을 열어 폴링하는 동안에만 갱신된다.

    한동안 /contracts/sign 만 남기고 화면이 쓰는 analyze-sign 은
    남기지 않아 실제로 그런 상태였다.
    """
    terms = _terms()
    client.post(
        "/contracts/analyze-sign",
        json=_body(
            terms,
            confirmed_fields=_must_confirm(terms),
            proceed_with_violations=True,
        ),
    )

    rows = memory_store.snapshot()
    assert "TEST-DOC-1" in rows

    record = rows["TEST-DOC-1"]
    assert record["total"] == 2  # 근로자 + 사업주
    # 계약 조건·이름·이메일은 이력에 남기지 않는다.
    assert "terms" not in record
    assert WORKER not in str(record)


# ============================================================
# 4-2. 사업주 경로 (경로 C)
# ============================================================


def test_사업주가_만든_문서는_사업주가_먼저_서명한다(fake_provider):
    """
    문서를 만든 쪽이 먼저 서명한다.

    사업주가 작성한 계약서는 사업주가 서명해 근로자에게 보낸다.
    근로자가 마지막에 서명해야 조건을 확인한 뒤 결정할 수 있다.

    ⚠️ 순서만 바뀐다. anchor 와 참여자 매핑은 절대 바뀌지 않는다.
       섞이면 서명란이 뒤바뀐 계약서가 나간다.
    """
    terms = _terms()
    res = client.post(
        "/contracts/analyze-sign",
        json=_body(
            terms,
            entry_path="EMPLOYER",
            confirmed_fields=_must_confirm(terms),
            proceed_with_violations=True,
        ),
    )

    assert res.status_code == 200, res.text
    assert fake_provider[0]["employer_first"] is True


def test_근로자가_만든_문서는_근로자가_먼저_서명한다(fake_provider):
    terms = _terms()
    for path in ("PHOTO", "MANUAL"):
        fake_provider.clear()
        res = client.post(
            "/contracts/analyze-sign",
            json=_body(
                terms,
                entry_path=path,
                confirmed_fields=_must_confirm(terms),
                proceed_with_violations=True,
            ),
        )
        assert res.status_code == 200, res.text
        assert fake_provider[0]["employer_first"] is False, path


@pytest.mark.parametrize(
    "entry_path,expected",
    [
        ("EMPLOYER", "사업주가 작성한 것입니다"),
        ("MANUAL", "근로자가 구두로 안내받은 내용을 직접 입력한 것입니다"),
    ],
)
def test_문서에_작성자를_밝힌다(entry_path, expected):
    """
    ⚠️ 상대방이 무엇에 서명하는지 알아야 한다.

    양쪽 모두에 출처를 붙인다. 근로자가 만든 문서에만 출처를 밝히고
    사업주가 만든 문서에는 안 밝히면, 그 자체가 한쪽을 덜 신뢰하는
    설계가 된다.
    """
    from app.schemas import EntryPath, ValidationReport

    note = contracts.build_verification_note(
        ValidationReport(checks=[]), EntryPath(entry_path)
    )
    assert expected in note


def test_계약서_사진_경로는_출처_문구를_붙이지_않는다():
    """출처가 계약서 원본이므로 별도 표시가 필요 없다."""
    from app.schemas import EntryPath, ValidationReport

    note = contracts.build_verification_note(
        ValidationReport(checks=[]), EntryPath.PHOTO
    )
    assert "직접 입력한 것입니다" not in note
    assert "사업주가 작성한 것입니다" not in note


# ============================================================
# 5. 이메일·이름 형식 검증 (Pydantic)
# ============================================================


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_email", "골뱅이없음"),
        ("worker_email", "worker@localhost"),  # 점 없는 도메인
        ("worker_email", "a b@example.com"),  # 공백
        ("employer_email", ""),
        ("worker_name", "   "),  # 공백만
    ],
)
def test_잘못된_이메일과_이름은_발송_전에_422로_막는다(no_provider_call, field, value):
    """
    ⚠️ 화면 검증만으로는 부족하다.

    프론트엔드 검증은 URL 직접 접근·개발자 도구·curl 로 우회된다.
    검증이 없으면 API를 직접 호출해 아무 주소로나 서명 요청을 보낼 수 있다.
    """
    res = client.post("/contracts/analyze-sign", json=_body(**{field: value}))
    assert res.status_code == 422


# ============================================================
# 5-2. 로그인 관문 — 어디서부터 로그인이 필요한가
# ============================================================


def test_로그인_없이는_서명을_보낼_수_없다(no_provider_call):
    """
    ⚠️ 익명 발송을 허용하면 이 서비스가 스팸 도구가 된다.
       아무 이메일이나 넣고 "근로계약서 서명 요청"을 보낼 수 있게 된다.
    """
    app.dependency_overrides.pop(require_user, None)  # 로그인 상태를 걷어낸다

    res = client.post("/contracts/analyze-sign", json=_body())

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "LOGIN_REQUIRED"


def test_로그인_없이는_보관함을_볼_수_없다():
    app.dependency_overrides.pop(require_user, None)
    assert client.get("/contracts").status_code == 401


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/contracts/validate", {"terms": _terms()}),
        ("/contracts/validation-state", {"terms": _terms()}),
        ("/contracts/message", {"terms": _terms()}),
        ("/contracts/review-items", {"terms": _terms()}),
    ],
)
def test_판정과_문구는_로그인_없이_된다(path, payload):
    """
    ⚠️ 이 테스트가 깨지면 제품의 전제가 무너진 것이다.

    열여섯 살이 첫 계약서를 확인하려고 회원가입부터 해야 한다면
    그 벽을 넘지 못한다. 로그인은 "내 문서"를 구분해야 하는
    시점(서명 발송·보관함)에서 처음 필요해진다.
    """
    app.dependency_overrides.pop(require_user, None)

    res = client.post(path, json=payload)

    assert res.status_code == 200, res.text


def test_남의_문서_상태는_볼_수_없다(memory_store):
    """
    ⚠️ 403 이 아니라 404 를 낸다.

    403 은 "그 문서는 존재하지만 네 것이 아니다"를 알려주는 셈이라,
    문서 ID 를 넣어보며 존재 여부를 알아낼 수 있다.
    계약서의 존재 자체가 개인정보다.
    """
    import asyncio

    from app.schemas import DocumentStatus, EntryPath

    asyncio.run(
        memory_store.remember(
            "SOMEONE-ELSE-DOC",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id="kakao:다른사람",
        )
    )

    res = client.get("/contracts/SOMEONE-ELSE-DOC/status")

    assert res.status_code == 404


def test_보관함은_내_문서만_보여준다(memory_store, monkeypatch):
    """
    ⚠️ owner_id 조건이 빠지면 보관함이 전체 사용자의 계약서 목록이 된다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    async def fake_get_document(document_id):
        raise sign_router.modusign.ModusignError("테스트에서는 제공자를 부르지 않는다")

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    async def seed(doc_id: str, owner: str) -> None:
        await memory_store.remember(
            doc_id,
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=owner,
        )

    asyncio.run(seed("MINE", TEST_USER["user_id"]))
    asyncio.run(seed("THEIRS", "kakao:다른사람"))

    ids = [item["document_id"] for item in client.get("/contracts").json()]

    assert ids == ["MINE"]


# ============================================================
# 6. 업로드 제한 — 공개 엔드포인트가 유료 API를 지키는가
# ============================================================


def test_계약서가_아닌_파일_형식은_거부한다():
    """
    ⚠️ 요청 한 번이 Upstage 유료 API를 두 번 호출한다.
       제한이 없으면 데모 당일에 크레딧이 소진될 수 있다.
       CORS는 브라우저만 막는다. curl 은 막지 못한다.
    """
    res = client.post(
        "/contracts/extract",
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )
    assert res.status_code == 400


def test_10MB_초과_업로드는_413으로_거부한다():
    res = client.post(
        "/contracts/extract",
        files={"file": ("huge.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert res.status_code == 413


def test_빈_파일은_400으로_거부한다():
    res = client.post(
        "/contracts/extract",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert res.status_code == 400


# ============================================================
# 7. 보관함 상세 — 누가 누구와 맺었는가
# ============================================================


def test_참여자_정보를_저장하지_않고_제공자에서_읽어온다(memory_store, monkeypatch):
    """
    ⚠️ 보관함에 이름이 없으면 "무슨 계약인지 알 수 없는 목록"이 된다.
       그렇다고 우리 DB에 이름·이메일을 쌓으면 보관 기간과 삭제 책임이 생긴다.

    그래서 저장하지 않고 문서를 열 때마다 모두싸인에서 읽는다.
    다운로드 링크를 저장하지 않는 것과 같은 이유다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    asyncio.run(
        memory_store.remember(
            "DOC-DETAIL",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=TEST_USER["user_id"],
        )
    )

    async def fake_get_document(document_id):
        return {
            "id": document_id,
            "title": "근로계약서",
            "status": "COMPLETED",
            "participants": [
                {"id": "p2", "name": "홍길동", "signingOrder": 2},
                {"id": "p1", "name": "김가상", "signingOrder": 1},
            ],
            "signings": [{"participantId": "p1"}],
            "file": {"downloadUrl": "https://example.com/signed.pdf"},
        }

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    body = client.get("/contracts/DOC-DETAIL/status").json()

    # 서명 순서대로 정렬되고, 서명 여부가 구분된다
    assert [p["name"] for p in body["participants"]] == ["김가상", "홍길동"]
    assert body["participants"][0]["signed"] is True
    assert body["participants"][1]["signed"] is False
    assert body["download_url"] == "https://example.com/signed.pdf"

    # ⚠️ 저장소에는 여전히 이름이 없어야 한다
    record = memory_store.snapshot()["DOC-DETAIL"]
    assert "김가상" not in str(record)
    assert "홍길동" not in str(record)


def test_참여자_이름이_없어도_상태_조회가_깨지지_않는다(memory_store, monkeypatch):
    """
    제공자 응답 구조가 바뀌어도 상태 조회 전체가 죽으면 안 된다.
    이름을 못 읽으면 순서로 대신한다 — 빈 목록보다 낫다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    asyncio.run(
        memory_store.remember(
            "DOC-ODD",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=TEST_USER["user_id"],
        )
    )

    async def fake_get_document(document_id):
        return {"id": document_id, "status": "ON_GOING", "participants": [{}, {}]}

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    body = client.get("/contracts/DOC-ODD/status").json()

    assert [p["name"] for p in body["participants"]] == ["1번 서명자", "2번 서명자"]
    assert body["download_url"] is None


def test_보관함_목록에_상대방과_다운로드_링크가_함께_온다(memory_store, monkeypatch):
    """
    ⚠️ 예전 보관함은 "체결 완료 · 날짜"만 보여줬다. 무슨 계약인지도,
       누구와 맺었는지도 알 수 없었고 문서를 받으려면 두 번 더 눌러야 했다.
       보관함이라면 목록에서 바로 상대방과 문서가 보여야 한다.

    ⚠️ 그래도 저장소에는 이름이 남지 않는다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    asyncio.run(
        memory_store.remember(
            "DOC-LIST",
            status=DocumentStatus.ON_GOING,  # 저장된 값은 아직 진행 중
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=TEST_USER["user_id"],
        )
    )

    async def fake_get_document(document_id):
        return {
            "id": document_id,
            "status": "COMPLETED",  # 제공자 쪽은 이미 체결 완료
            "participants": [
                {"id": "p1", "name": "김가상", "signingOrder": 1},
                {"id": "p2", "name": "홍길동", "signingOrder": 2},
            ],
            "signings": [{"participantId": "p1"}, {"participantId": "p2"}],
            "file": {"downloadUrl": "https://example.com/signed.pdf"},
        }

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    item = client.get("/contracts").json()[0]

    assert [p["name"] for p in item["participants"]] == ["김가상", "홍길동"]
    assert item["download_url"] == "https://example.com/signed.pdf"
    # 저장값(ON_GOING)이 아니라 제공자의 최신 상태를 보여준다
    assert item["status"] == "COMPLETED"
    assert item["stale"] is False

    record = memory_store.snapshot()["DOC-LIST"]
    assert "김가상" not in str(record)
    assert "홍길동" not in str(record)


def test_한_문서의_조회_실패가_보관함_전체를_깨뜨리지_않는다(memory_store, monkeypatch):
    """
    ⚠️ 제공자가 잠깐 죽었다고 "계약서가 사라진" 화면을 보여주면 안 된다.
       실패한 항목은 저장값으로 보여주고 stale 로 알린다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    async def seed(doc_id: str) -> None:
        await memory_store.remember(
            doc_id,
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=TEST_USER["user_id"],
        )

    asyncio.run(seed("DOC-OK"))
    asyncio.run(seed("DOC-BROKEN"))

    async def fake_get_document(document_id):
        if document_id == "DOC-BROKEN":
            raise sign_router.modusign.ModusignError("제공자 응답 없음")
        return {
            "id": document_id,
            "status": "COMPLETED",
            "participants": [{"id": "p1", "name": "김가상", "signingOrder": 1}],
            "signings": [{"participantId": "p1"}],
            "file": {"downloadUrl": "https://example.com/signed.pdf"},
        }

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    res = client.get("/contracts")

    assert res.status_code == 200
    items = {item["document_id"]: item for item in res.json()}
    # 실패한 항목도 목록에서 사라지지 않는다
    assert set(items) == {"DOC-OK", "DOC-BROKEN"}
    assert items["DOC-BROKEN"]["stale"] is True
    assert items["DOC-BROKEN"]["status"] == "ON_GOING"  # 마지막 저장값
    assert items["DOC-BROKEN"]["participants"] == []
    assert items["DOC-BROKEN"]["download_url"] is None
    assert items["DOC-OK"]["stale"] is False


def test_체결되지_않은_문서는_다운로드_링크를_주지_않는다(memory_store, monkeypatch):
    """
    ⚠️ 진행 중인 문서에 다운로드 버튼이 뜨면 "이미 끝났다"고 오해한다.
    """
    import asyncio

    from app.routers import sign as sign_router
    from app.schemas import DocumentStatus, EntryPath

    asyncio.run(
        memory_store.remember(
            "DOC-GOING",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
            owner_id=TEST_USER["user_id"],
        )
    )

    async def fake_get_document(document_id):
        return {
            "id": document_id,
            "status": "ON_GOING",
            "participants": [
                {"id": "p1", "name": "김가상", "signingOrder": 1},
                {"id": "p2", "name": "홍길동", "signingOrder": 2},
            ],
            "signings": [{"participantId": "p1"}],
            # 제공자가 링크를 실어 보내도 미체결이면 노출하지 않는다
            "file": {"downloadUrl": "https://example.com/draft.pdf"},
        }

    monkeypatch.setattr(sign_router.modusign, "get_document", fake_get_document)

    item = client.get("/contracts").json()[0]

    assert item["download_url"] is None
    assert item["signed"] == 1
    assert item["total"] == 2
    assert [p["signed"] for p in item["participants"]] == [True, False]


# ============================================================
# 8. 계약 비서 — 확인된 조건과 검증 결과만 검색하는가
# ============================================================


def test_계약_비서는_법정_기준에_근거를_붙여_답한다():
    res = client.post(
        "/contracts/chat",
        json={"terms": _terms(), "question": "최저임금 기준이 어떻게 되나요?"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "LEGAL_STANDARD"
    assert body["evidence"]
    assert any(item["kind"] == "LEGAL_STANDARD" for item in body["evidence"])


def test_계약_비서는_분쟁_질문을_고정_안내로_돌린다():
    res = client.post(
        "/contracts/chat",
        json={"terms": _terms(), "question": "사장님을 신고할 수 있나요?"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "OUT_OF_SCOPE"
    assert "1350" in body["answer"]


def test_계약서_없는_주휴_질문은_시간_요건과_한계를_함께_안내한다():
    res = client.post(
        "/questions/general",
        json={"question": "1주일에 12시간 일하면 주휴수당을 받나요?"},
    )

    assert res.status_code == 200
    body = res.json()
    assert "15시간 이상" in body["answer"]
    assert "소정근로일 개근" in body["answer"]
    assert "해당 주까지 근로관계 유지" in body["limitations"]
    assert body["evidence"][0]["kind"] == "LEGAL_STANDARD"
    assert body["action"]["href"] == "/upload"


@pytest.mark.parametrize("question", ["소정근로일이 뭐야?", "소정근로일 뜻"])
def test_소정근로일_정의는_범위밖_거절_대신_검증된_근거로_답한다(question):
    res = client.post("/questions/general", json={"question": question})

    assert res.status_code == 200
    body = res.json()
    assert body["topic"] == "WEEKLY_HOLIDAY"
    assert "미리 일하기로 정한 날" in body["answer"]
    assert "추가로 출근한 날과는 구분" in body["answer"]
    assert body["evidence"]
    assert body["retrieved_kb_ids"] == ["KB-GLOSSARY-PRESCRIBED-WORKDAY"]
    assert "SRC-MOEL-WEEKLY-HOLIDAY" in body["retrieved_source_ids"]


@pytest.mark.parametrize(
    "question,expected,source_fragment",
    [
        ("최저임금 기준을 알려주세요.", "10,320원", "minimumwage.go.kr"),
        ("계약서에 휴게시간이 안 적혀 있어요.", "4시간", "law.go.kr"),
    ],
)
def test_추천_질문은_질문별_공식_근거로_답한다(question, expected, source_fragment):
    res = client.post("/questions/general", json={"question": question})

    assert res.status_code == 200
    body = res.json()
    assert expected in body["answer"]
    assert source_fragment in body["evidence"][0]["url"]


@pytest.mark.parametrize(
    "question,topic,expected",
    [
        ("근로계약서를 꼭 받아야 하나요?", "WRITTEN_CONTRACT", "서면"),
        ("17살인데 밤 10시 이후에도 일해도 되나요?", "MINOR_WORK", "35시간"),
        ("야간근로 수당 기준을 알려주세요.", "EXTRA_WORK", "22시"),
        ("해고 신고는 어떻게 하나요?", "OUT_OF_SCOPE", "1350"),
    ],
)
def test_계약서_없는_주요_노동_질문을_주제별로_답한다(question, topic, expected):
    res = client.post("/questions/general", json={"question": question})

    assert res.status_code == 200
    body = res.json()
    assert body["topic"] == topic
    assert expected in body["answer"]
    if topic == "WEEKLY_HOLIDAY":
        assert "소정근로일 개근" in body["answer"]
        assert "해당 주까지 근로관계 유지" in body["limitations"]


@pytest.mark.parametrize(
    "question,context,topic,expected",
    [
        ("그럼 6시간이면?", "BREAK_TIME", "BREAK_TIME", "30분"),
        ("그럼 14시간은?", "WEEKLY_HOLIDAY", "WEEKLY_HOLIDAY", "15시간 이상"),
        ("시급 10,000원은?", "MINIMUM_WAGE", "MINIMUM_WAGE", "320원"),
    ],
)
def test_짧은_후속_질문은_직전_주제_문맥을_이어받는다(
    question, context, topic, expected
):
    res = client.post(
        "/questions/general",
        json={"question": question, "context": context},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["topic"] == topic
    assert expected in body["answer"]


@pytest.mark.parametrize(
    "path,payload,expected_fragment",
    [
        ("/questions/general", {"question": "안녕하세요"}, "근로계약"),
        (
            "/contracts/chat",
            {"question": "감사합니다", "terms": _terms()},
            "다행이에요",
        ),
    ],
)
def test_두_챗봇_경로에서_일상대화에_응답한다(path, payload, expected_fragment):
    res = client.post(path, json=payload)

    assert res.status_code == 200
    body = res.json()
    assert expected_fragment in body["answer"]
    assert body["evidence"] == []
