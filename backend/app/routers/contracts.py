"""
계약 검증·문서 생성 라우터 (C 담당)

  POST /contracts/validate       조건 → 법정 기준 판정
  POST /contracts/preview        조건 → 계약서 PDF 미리보기
  POST /contracts/analyze-sign   조건 → 검증 → PDF → 서명 요청 (세로 흐름)

⚠️ 판정은 app/validation/ 의 순수 함수가 수행한다. LLM 호출 없음.
"""

import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.pdf.generator import render_contract_pdf
from app.schemas import (
    CheckStatus,
    ContractTerms,
    DocumentStatus,
    EntryPath,
    ExtractedField,
    ValidationReport,
)
from app.signing import modusign
from app.validation.rules import validate

log = logging.getLogger(__name__)
router = APIRouter()


def _minimize_contact_fields(terms: ContractTerms) -> ContractTerms:
    """검증·초안 생성에 불필요한 전화·주소·연락처는 즉시 비운다."""
    return terms.model_copy(
        update={
            "employer_phone": ExtractedField(),
            "employer_address": ExtractedField(),
            "worker_address": ExtractedField(),
            "worker_contact": ExtractedField(),
        }
    )


# ============================================================
# 1. 검증만
# ============================================================


class ValidateRequest(BaseModel):
    terms: ContractTerms


@router.post("/contracts/validate", response_model=ValidationReport)
async def validate_terms(body: ValidateRequest) -> ValidationReport:
    """
    계약 조건을 법정 기준과 대조한다.

    입력은 사용자가 확인·수정을 마친 조건이어야 한다.
    AI 추출 직후 값을 그대로 넣으면 안 된다.
    """
    return validate(_minimize_contact_fields(body.terms))


# ============================================================
# 2. 검증 결과를 계약서에 남기기
# ============================================================


def build_verification_note(report: ValidationReport) -> str:
    """
    판정 결과를 계약서 하단에 넣을 한 문단으로 만든다.

    ⚠️ 여기서 새로운 사실이나 숫자를 만들지 않는다.
       CheckResult가 담고 있는 값만 옮긴다.
    """
    problems = [
        c
        for c in report.checks
        if c.status in (CheckStatus.VIOLATION, CheckStatus.MISSING)
    ]

    if not problems:
        return (
            "※ 본 요청서는 FairSign에서 2026년 기준 최저임금·주휴 시간요건·"
            "휴게시간 항목을 확인했으며, 확인된 범위에서 미달·누락 항목이 "
            "발견되지 않았습니다. 법률 자문이 아닙니다."
        )

    lines = [
        f"· {c.label}: {c.calculation or c.detail or '확인 필요'}" for c in problems
    ]
    return (
        "※ FairSign 확인 결과(2026년 기준), 아래 항목은 지원하는 기준보다 낮거나 "
        "확인된 입력에서 찾지 못했습니다. 이 요청서는 해당 결과를 자동으로 "
        "수정하지 않습니다.\n"
        + "\n".join(lines)
        + "\n법정 기준 자동 계산 결과이며 법률 자문이 아닙니다."
    )


# ============================================================
# 3. PDF 미리보기
# ============================================================


class PreviewRequest(BaseModel):
    terms: ContractTerms
    entry_path: EntryPath = EntryPath.PHOTO
    include_verification: bool = True


@router.post("/contracts/preview")
async def preview_pdf(body: PreviewRequest) -> Response:
    """
    계약서 PDF를 만들어 바로 반환한다. 서명 요청은 보내지 않는다.

    입력 경로와 무관하게 미리보기는 아직 상대방 확인·체결 완료 전이므로
    '확인 전 초안' 워터마크가 있는 근로조건 확인 요청서로 만든다.
    """
    terms = _minimize_contact_fields(body.terms)

    note = None
    if body.include_verification:
        note = build_verification_note(validate(terms))

    pdf = render_contract_pdf(terms, is_draft=True, verification_note=note)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="work_conditions_request_draft.pdf"'
        },
    )


# ============================================================
# 4. 세로 흐름 — 검증 → PDF → 서명 요청
# ============================================================


class AnalyzeSignRequest(BaseModel):
    terms: ContractTerms
    worker_name: str
    worker_email: str
    employer_name: str
    employer_email: str
    entry_path: EntryPath = EntryPath.PHOTO
    # 위반 항목이 남아 있어도 그대로 진행할지. 기본은 차단.
    proceed_with_violations: bool = False


class AnalyzeSignResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    report: ValidationReport
    message: str


@router.post("/contracts/analyze-sign", response_model=AnalyzeSignResponse)
async def analyze_and_sign(body: AnalyzeSignRequest) -> AnalyzeSignResponse:
    """
    조건 확인 → 법정 기준 검증 → 계약서 생성 → 서명 요청.

    위반 항목이 남아 있으면 기본적으로 막는다.
    사용자가 알고도 진행하려면 proceed_with_violations=true 를 보내야 한다.
    """
    terms = _minimize_contact_fields(body.terms)
    report = validate(terms)

    if report.has_problem and not body.proceed_with_violations:
        problems = [
            c.label
            for c in report.checks
            if c.status in (CheckStatus.VIOLATION, CheckStatus.MISSING)
        ]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "법정 기준에 미달하거나 누락된 항목이 있습니다.",
                "problems": problems,
                "hint": "조건을 수정하거나 proceed_with_violations=true 로 다시 요청하세요.",
            },
        )

    pdf = render_contract_pdf(
        terms,
        # 폼 제출이나 발송만으로 양쪽이 조건을 확인했다고 보지 않는다.
        is_draft=True,
        verification_note=build_verification_note(report),
    )

    try:
        result = await modusign.request_signature(
            pdf_bytes=pdf,
            title="근로조건 확인 요청서",
            worker_name=body.worker_name,
            worker_email=body.worker_email,
            employer_name=body.employer_name,
            employer_email=body.employer_email,
        )
    except modusign.ModusignError as e:
        log.error("서명 요청 실패: error_type=%s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail="서명 요청 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from e

    return AnalyzeSignResponse(
        document_id=result["id"],
        status=modusign.to_document_status(result["status"]),
        report=report,
        message=(
            "확인 전 초안 요청서를 서명 절차에 보냈습니다. "
            "체결 완료 여부는 제공자 상태를 다시 확인한 뒤 표시합니다."
        ),
    )
