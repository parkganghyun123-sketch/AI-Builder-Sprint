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

from app.main import app  # noqa: E402
from app.review.fields import build_review_items  # noqa: E402
from app.routers import contracts, sign  # noqa: E402
from app.schemas import ContractTerms  # noqa: E402

client = TestClient(app)

WORKER = "김가상"
EMPLOYER = "홍길동"


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
def fake_provider(monkeypatch):
    """서명 요청을 가짜로 성공시킨다. 호출 인자를 기록한다."""
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return {"id": "TEST-DOC-1", "status": "ON_GOING"}

    monkeypatch.setattr(contracts.modusign, "request_signature", fake)
    monkeypatch.setattr(contracts, "render_contract_pdf", lambda *a, **k: b"%PDF-stub")
    sign._store.clear()
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
    assert "proceed_with_violations" in detail["hint"]


def test_발송한_문서는_이력에_남는다(fake_provider):
    """
    ⚠️ 이 테스트가 실패하면 웹훅이 조용히 죽는다.

    webhook() 은 `if doc_id not in _store: return` 으로 시작한다.
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

    assert "TEST-DOC-1" in sign._store

    record = sign._store["TEST-DOC-1"]
    assert record["total"] == 2  # 근로자 + 사업주
    # 계약 조건·이름·이메일은 이력에 남기지 않는다.
    assert "terms" not in record
    assert WORKER not in str(record)


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
def test_잘못된_이메일과_이름은_발송_전에_422로_막는다(
    no_provider_call, field, value
):
    """
    ⚠️ 화면 검증만으로는 부족하다.

    프론트엔드 검증은 URL 직접 접근·개발자 도구·curl 로 우회된다.
    검증이 없으면 API를 직접 호출해 아무 주소로나 서명 요청을 보낼 수 있다.
    """
    res = client.post("/contracts/analyze-sign", json=_body(**{field: value}))
    assert res.status_code == 422


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
