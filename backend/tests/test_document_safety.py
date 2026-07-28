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


def test_analyze_sign_keeps_request_pdf_draft_and_uses_neutral_title(
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_render(terms, *, is_draft, verification_note=None):
        captured["is_draft"] = is_draft
        captured["terms"] = terms
        return b"%PDF-synthetic"

    async def fake_request_signature(**kwargs):
        captured.update(kwargs)
        return {"id": "synthetic-document-id", "status": "ON_PROCESSING"}

    monkeypatch.setattr(contracts, "render_contract_pdf", fake_render)
    monkeypatch.setattr(contracts, "validate", lambda terms: _empty_report())
    monkeypatch.setattr(contracts.modusign, "request_signature", fake_request_signature)

    response = asyncio.run(
        contracts.analyze_and_sign(
            contracts.AnalyzeSignRequest(
                terms=_terms(),
                worker_name="가상 근로자",
                worker_email="worker@example.com",
                employer_name="가상 사업주",
                employer_email="employer@example.com",
                entry_path="PHOTO",
            )
        )
    )

    assert captured["is_draft"] is True
    assert captured["title"] == "근로조건 확인 요청서"
    assert captured["terms"].worker_contact.value is None
    assert response.status == DocumentStatus.ON_PROCESSING
    assert "체결 완료 여부" in response.message


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
