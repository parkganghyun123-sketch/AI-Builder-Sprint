import asyncio
import json
import logging
import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

# Windows CI에는 WeasyPrint의 GTK 네이티브 라이브러리가 없을 수 있다. 이 파일은
# 라우터가 generator를 안전하게 호출하는지만 검증하므로 import 단계의 구현을 대체한다.
pdf_generator_stub = ModuleType("app.pdf.generator")
pdf_generator_stub.render_contract_pdf = lambda *args, **kwargs: b"%PDF-stub"
sys.modules.setdefault("app.pdf.generator", pdf_generator_stub)

from app.ai.document_parse import DocumentParseError  # noqa: E402
from app.ai.extract import ExtractError  # noqa: E402
from app.review.fields import build_review_items  # noqa: E402
from app.routers import contracts, sign  # noqa: E402
from app.routers import extract as extract_router  # noqa: E402
from app.schemas import (  # noqa: E402
    ContractTerms,
    DocumentStatus,
    ExtractedField,
    ValidationReport,
)


def _field(value=None, source_text: str | None = None) -> ExtractedField:
    return ExtractedField(
        value=value,
        confidence="NOT_FOUND" if value is None else "HIGH",
        source_text=source_text,
    )


def _all_must_confirm(terms) -> list[str]:
    """
    확인 관문(app/review/)을 통과한 상태를 만든다.

    임금·신원 항목은 AI 신뢰도와 무관하게 사용자 확인을 요구한다.
    실측에서 '박강현' → '박강헌' 이 HIGH 로 나와, 신뢰도만으로는
    막을 수 없다는 게 확인됐기 때문이다.
    이 테스트들은 확인을 마친 뒤의 동작을 검증하므로 전부 확인 처리한다.
    """
    return [
        item["field"]
        for item in build_review_items(terms)
        if item["priority"] == "high"
    ]


def _terms() -> ContractTerms:
    return ContractTerms(
        contract_start=_field("2026-08-01"),
        contract_end=_field("2027-01-31"),
        workplace=_field("가상 카페"),
        job_description=_field("음료 제조"),
        work_start_time=_field("09:00"),
        work_end_time=_field("15:00"),
        break_start_time=_field("12:00"),
        break_end_time=_field("12:30"),
        work_days_per_week=_field("3"),
        weekly_holiday_day=_field("일요일"),
        wage_type=_field("HOURLY"),
        wage_amount=_field("12000"),
        has_bonus=_field("없음"),
        other_allowance=_field(None),
        payday=_field("10"),
        payment_method=_field("계좌입금"),
        employer_business_name=_field("가상 사업장"),
        employer_phone=_field("010-1111-2222", "비공개 전화 원문"),
        employer_address=_field("가상 사업장 주소", "비공개 주소 원문"),
        employer_name=_field("가상 사업주"),
        worker_address=_field("가상 근로자 주소", "비공개 근로자 주소 원문"),
        worker_contact=_field("010-3333-4444", "비공개 연락처 원문"),
        worker_name=_field("가상 근로자"),
    )


def _minor_problem_terms() -> ContractTerms:
    return _terms().model_copy(
        update={
            "work_start_time": _field("20:00"),
            "work_end_time": _field("04:00"),
            "break_start_time": _field(None),
            "break_end_time": _field(None),
            "work_days_per_week": _field(4),
        }
    )


def _empty_report() -> ValidationReport:
    return ValidationReport(
        checks=[],
        estimated_monthly_pay=None,
        wage_shortfall=None,
    )


def _request_with_json(payload: dict) -> Request:
    body = json.dumps(payload).encode()
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/webhooks/modusign",
            "raw_path": b"/webhooks/modusign",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        },
        receive,
    )


def test_contact_fields_are_removed_before_validation_or_pdf() -> None:
    minimized = contracts._minimize_contact_fields(_terms())

    for key in (
        "employer_phone",
        "employer_address",
        "worker_address",
        "worker_contact",
    ):
        field = getattr(minimized, key)
        assert field.value is None
        assert field.source_text is None
        assert field.confidence.value == "NOT_FOUND"


def test_preview_is_always_a_watermarked_request_draft(monkeypatch) -> None:
    captured: dict = {}

    def fake_render(terms, *, is_draft, verification_note=None):
        captured["terms"] = terms
        captured["is_draft"] = is_draft
        return b"%PDF-synthetic"

    monkeypatch.setattr(contracts, "render_contract_pdf", fake_render)
    monkeypatch.setattr(contracts, "validate", lambda terms: _empty_report())

    response = asyncio.run(
        contracts.preview_pdf(
            contracts.PreviewRequest(
                terms=_terms(),
                entry_path="PHOTO",
                include_verification=True,
            )
        )
    )

    assert captured["is_draft"] is True
    assert captured["terms"].employer_phone.value is None
    assert response.body == b"%PDF-synthetic"
    assert (
        response.headers["content-disposition"]
        == 'inline; filename="work_conditions_request_draft.pdf"'
    )


def test_validate_request_forwards_worker_birth_date(monkeypatch) -> None:
    captured: dict = {}

    def fake_validate(terms, worker_birth_date=None):
        captured["terms"] = terms
        captured["worker_birth_date"] = worker_birth_date
        return _empty_report()

    monkeypatch.setattr(contracts, "validate", fake_validate)
    response = asyncio.run(
        contracts.validate_terms(
            contracts.ValidateRequest(
                terms=_terms(),
                worker_birth_date="2009-07-31",
            )
        )
    )

    assert response == _empty_report()
    assert captured["worker_birth_date"] == "2009-07-31"
    assert captured["terms"].worker_contact.value is None


def test_analyze_sign_keeps_request_pdf_draft_and_uses_neutral_title(
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_render(terms, *, is_draft, verification_note=None):
        captured["is_draft"] = is_draft
        captured["terms"] = terms
        captured["verification_note"] = verification_note
        return b"%PDF-synthetic"

    def fake_validate(terms, worker_birth_date=None):
        captured["worker_birth_date"] = worker_birth_date
        return _empty_report()

    async def fake_request_signature(**kwargs):
        captured.update(kwargs)
        return {"id": "synthetic-document-id", "status": "ON_PROCESSING"}

    monkeypatch.setattr(contracts, "render_contract_pdf", fake_render)
    monkeypatch.setattr(contracts, "validate", fake_validate)
    monkeypatch.setattr(contracts.modusign, "request_signature", fake_request_signature)

    response = asyncio.run(
        contracts.analyze_and_sign(
            contracts.AnalyzeSignRequest(
                terms=_terms(),
                worker_name="가상 근로자",
                worker_email="worker@example.com",
                employer_name="가상 사업주",
                employer_email="employer@example.com",
                worker_birth_date="2009-07-31",
                entry_path="PHOTO",
                confirmed_fields=_all_must_confirm(_terms()),
            )
        )
    )

    # 서명할 문서에는 '확인 전 초안' 워터마크를 찍지 않는다.
    # 체결된 계약서에 '초안' 표기가 남으면 분쟁 시 빌미가 되고,
    # 근로기준법 제17조 교부 의무를 이행한 증거로도 약해진다.
    # 경로 B의 투명성은 검증 문단의 출처 표시로 확보한다.
    assert captured["is_draft"] is False
    # 제목에 이름을 넣지 않는다 — 모두싸인 문서 목록·메일 제목에 노출된다.
    assert captured["title"] == "근로계약서"
    assert captured["terms"].worker_contact.value is None
    assert captured["worker_birth_date"] == "2009-07-31"
    assert "2009-07-31" not in captured["verification_note"]
    assert response.status == DocumentStatus.ON_PROCESSING
    assert "체결 완료 여부" in response.message


def test_verification_note_preserves_minor_calculation_and_limit_details() -> None:
    birth_date = "2009-07-31"
    report = contracts.validate(
        _minor_problem_terms(),
        worker_birth_date=birth_date,
    )

    note = contracts.build_verification_note(report)

    assert "계산:" in note
    assert "안내:" in note
    assert "1일 8시간 > 기본 7시간" in note
    assert "당사자 합의 여부는 입력에서 확인되지 않았습니다" in note
    assert "야간 22:00~06:00 시간대가 겹침" in note
    assert "고용노동부장관 인가 등 예외 요건" in note
    assert birth_date not in note


def test_analyze_sign_pdf_note_preserves_minor_limits_with_mock_provider(
    monkeypatch,
) -> None:
    birth_date = "2009-07-31"
    captured: dict = {}

    def fake_render(terms, *, is_draft, verification_note=None):
        captured["verification_note"] = verification_note
        return b"%PDF-synthetic"

    async def fake_request_signature(**kwargs):
        return {"id": "synthetic-minor-document", "status": "ON_PROCESSING"}

    monkeypatch.setattr(contracts, "render_contract_pdf", fake_render)
    monkeypatch.setattr(
        contracts.modusign,
        "request_signature",
        fake_request_signature,
    )

    response = asyncio.run(
        contracts.analyze_and_sign(
            contracts.AnalyzeSignRequest(
                terms=_minor_problem_terms(),
                worker_birth_date=birth_date,
                worker_name="가상 근로자",
                worker_email="worker@example.com",
                employer_name="가상 사업주",
                employer_email="employer@example.com",
                entry_path="PHOTO",
                proceed_with_violations=True,
                confirmed_fields=_all_must_confirm(_minor_problem_terms()),
            )
        )
    )

    assert response.status == DocumentStatus.ON_PROCESSING
    assert (
        "당사자 합의 여부는 입력에서 확인되지 않았습니다"
        in captured["verification_note"]
    )
    assert "고용노동부장관 인가 등 예외 요건" in captured["verification_note"]
    assert birth_date not in captured["verification_note"]


def test_analyze_sign_409_preserves_minor_details_without_sending(
    monkeypatch,
    caplog,
) -> None:
    birth_date = "2009-07-31"
    signing_called = False

    async def fail_if_signature_requested(**kwargs):
        nonlocal signing_called
        signing_called = True
        raise AssertionError("409 응답 전에 모두싸인 요청을 보내면 안 됩니다.")

    monkeypatch.setattr(
        contracts.modusign,
        "request_signature",
        fail_if_signature_requested,
    )

    with caplog.at_level(logging.INFO, logger=contracts.__name__):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(
                contracts.analyze_and_sign(
                    contracts.AnalyzeSignRequest(
                        terms=_minor_problem_terms(),
                        worker_birth_date=birth_date,
                        worker_name="가상 근로자",
                        worker_email="worker@example.com",
                        employer_name="가상 사업주",
                        employer_email="employer@example.com",
                        entry_path="PHOTO",
                        confirmed_fields=_all_must_confirm(_minor_problem_terms()),
                    )
                )
            )

    assert caught.value.status_code == 409
    assert caught.value.detail["message"] == (
        "기본 기준 초과·누락 또는 추가 확인이 필요한 항목이 있습니다."
    )
    assert isinstance(caught.value.detail["problems"], list)
    details = {
        detail["code"]: detail for detail in caught.value.detail["problem_details"]
    }
    assert "MINOR_WORKING_HOURS" in details
    assert "MINOR_NIGHT_WORK" in details
    assert "1일 8시간 > 기본 7시간" in details["MINOR_WORKING_HOURS"]["calculation"]
    assert "당사자 합의 여부" in details["MINOR_WORKING_HOURS"]["detail"]
    assert "고용노동부장관 인가" in details["MINOR_NIGHT_WORK"]["detail"]
    assert signing_called is False
    assert birth_date not in str(caught.value.detail)
    assert birth_date not in caplog.text


def test_direct_sign_does_not_store_terms_or_names_in_title(monkeypatch) -> None:
    captured: dict = {}

    def fake_render(terms, *, is_draft, verification_note=None):
        captured["is_draft"] = is_draft
        captured["terms"] = terms
        return b"%PDF-synthetic"

    async def fake_request_signature(**kwargs):
        captured.update(kwargs)
        return {"id": "synthetic-sign-id", "status": "ON_PROCESSING"}

    monkeypatch.setattr(sign, "render_contract_pdf", fake_render)
    monkeypatch.setattr(sign.modusign, "request_signature", fake_request_signature)
    sign._store.clear()

    response = asyncio.run(
        sign.create_and_send(
            sign.SignRequestBody(
                terms=_terms(),
                worker_name="가상 근로자",
                worker_email="worker@example.com",
                employer_name="가상 사업주",
                employer_email="employer@example.com",
                entry_path="MANUAL",
            )
        )
    )

    # /contracts/sign 은 법정 기준 검증도 확인 관문도 거치지 않는 직접 경로다.
    # 무엇에 서명하는지 보증할 수 없으므로 초안 표기를 유지한다.
    # (검증·확인을 마치는 /contracts/analyze-sign 은 워터마크를 찍지 않는다)
    assert captured["is_draft"] is True
    assert captured["title"] == "근로조건 확인 요청서"
    assert "terms" not in sign._store[response.document_id]
    assert sign._store[response.document_id]["title"] == "근로조건 확인 요청서"


def test_webhook_logs_only_event_and_document_identifiers(caplog) -> None:
    private_email = "private-person@example.com"
    private_name = "로그에 남으면 안 되는 이름"
    sign._store.clear()
    request = _request_with_json(
        {
            "event": {"type": "document_started"},
            "document": {
                "id": "synthetic-webhook-document",
                "requester": {"name": private_name, "email": private_email},
            },
        }
    )

    with caplog.at_level(logging.INFO, logger=sign.__name__):
        result = asyncio.run(sign.webhook(request))

    assert result == {"received": True}
    assert "event=document_started" in caplog.text
    assert "document=synthetic-webhook-document" in caplog.text
    assert private_email not in caplog.text
    assert private_name not in caplog.text


def test_draft_template_uses_status_wording_not_legal_effect_conclusion() -> None:
    template_path = (
        Path(__file__).parents[1]
        / "app"
        / "pdf"
        / "templates"
        / "employment_contract.html"
    )
    template = template_path.read_text(encoding="utf-8")

    assert "근로조건 확인 요청서" in template
    assert "체결 완료 상태가 확인되지 않았습니다" in template
    assert "계약 효력이 없습니다" not in template


@pytest.mark.parametrize(
    "error_type",
    [ExtractError, DocumentParseError, httpx.ReadTimeout],
)
def test_extract_router_hides_private_upstream_error_from_response_and_log(
    monkeypatch,
    caplog,
    error_type,
) -> None:
    private_message = "가상 근로자 김하늘 private-person@example.com"

    async def fail_extract(file_bytes: bytes, filename: str):
        raise error_type(private_message)

    monkeypatch.setattr(extract_router, "extract_contract_terms", fail_extract)
    upload = UploadFile(
        filename="synthetic-contract.png",
        file=BytesIO(b"synthetic-private-contract"),
    )

    with caplog.at_level(logging.ERROR, logger=extract_router.__name__):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(extract_router.extract_terms(upload))

    assert caught.value.status_code == 502
    assert caught.value.detail == (
        "계약서 추출 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
    )
    assert caught.value.__suppress_context__ is True
    assert f"error_type={error_type.__name__}" in caplog.text
    assert private_message not in str(caught.value.detail)
    assert private_message not in caplog.text
