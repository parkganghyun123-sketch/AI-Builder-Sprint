"""
계약 검증·문서 생성 라우터 (C 담당)

  POST /contracts/validate       조건 → 법정 기준 판정
  POST /contracts/message        판정 → 사장님께 보낼 문의 문구
  POST /contracts/preview        조건 → 계약서 PDF 미리보기
  POST /contracts/analyze-sign   확인 → 검증 → PDF → 서명 요청 (세로 흐름)

⚠️ 판정은 app/validation/ 의 순수 함수가 수행한다. LLM 호출 없음.
"""

import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.bridge.numbers import verify
from app.bridge.templates import build_lines, build_message
from app.pdf.generator import render_contract_pdf
from app.review.fields import unconfirmed_high_priority
from app.schemas import (
    CheckStatus,
    ContractTerms,
    DocumentStatus,
    EntryPath,
    ValidationReport,
)
from app.signing import modusign
from app.validation.rules import validate

log = logging.getLogger(__name__)
router = APIRouter()


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
    return validate(body.terms)


# ============================================================
# 1-2. "말 꺼내기" 문구
# ============================================================


class MessageResponse(BaseModel):
    message: str | None = None
    lines: list[str] = []
    numbers_verified: bool = True


@router.post("/contracts/message", response_model=MessageResponse)
async def build_owner_message(body: ValidateRequest) -> MessageResponse:
    """
    판정 결과 → 사장님께 보낼 문의 메시지.

    계약서가 최저임금 미달인 걸 아는 것과, 그걸 사장님에게 말하는 것은
    다른 문제다. 이 엔드포인트는 후자를 돕는다.

    ⚠️ 문구의 숫자는 전부 ValidationReport에서 꺼낸다. LLM을 쓰지 않는다.
       반환 전 app.bridge.numbers 로 한 번 더 대조한다.
       (LLM 버전을 얹더라도 이 검증은 그대로 통과해야 한다)

    문제가 없으면 message는 null이다.
    """
    report = validate(body.terms)
    message = build_message(report)

    if message is None:
        return MessageResponse(message=None, lines=[])

    ok, unverified = verify(message, report, body.terms)
    if not ok:
        # 템플릿은 구조상 여기 올 수 없다. 오면 템플릿이 깨진 것이므로 로그를 남긴다.
        log.error("문구에 근거 없는 숫자: %s", unverified)

    return MessageResponse(
        message=message,
        lines=build_lines(report),
        numbers_verified=ok,
    )


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
            "※ 본 계약서는 FairSign에서 2026년 기준 최저임금·주휴 시간요건·"
            "휴게시간 항목을 확인했으며, 확인된 범위에서 미달·누락 항목이 "
            "발견되지 않았습니다. 법률 자문이 아닙니다."
        )

    lines = [f"· {c.label}: {c.calculation or c.detail or '확인 필요'}" for c in problems]
    return (
        "※ FairSign 확인 결과(2026년 기준), 아래 항목이 법정 기준에 미달하거나 "
        "누락되어 수정 후 작성되었습니다.\n"
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

    경로 B(근로자가 혼자 입력)는 아직 상대방 확인 전이므로
    '확인 전 초안' 워터마크를 찍는다.
    """
    is_draft = body.entry_path == EntryPath.MANUAL

    note = None
    if body.include_verification:
        note = build_verification_note(validate(body.terms))

    pdf = render_contract_pdf(body.terms, is_draft=is_draft, verification_note=note)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="contract_preview.pdf"'},
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
    # 사용자가 화면에서 확인을 마친 항목들.
    #
    # AI가 자신 있게 틀리는 경우가 있어(실측: '박강현' → '박강헌')
    # 신뢰도만으로는 막을 수 없다. 사람이 봤다는 사실을 받아야 한다.
    # /contracts/review-items 의 must_confirm 을 전부 담아 보낼 것.
    confirmed_fields: list[str] = []


class AnalyzeSignResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    report: ValidationReport
    message: str


def _name_conflicts(body: "AnalyzeSignRequest") -> list[dict]:
    """
    계약서에 적힌 이름과 서명 요청에 입력한 이름이 다른 경우를 찾는다.

    ⚠️ 어느 쪽이 맞는지 코드는 모른다. 그래서 고르지 않는다.

    실측에서 AI가 '박강현' 을 '박강헌' 으로 읽었지만, 반대로
    사용자가 입력을 잘못했을 수도 있고, 종이에 정말 다른 이름이
    적혀 있었을 수도 있다(사장님이 잘못 기재한 경우 등).

    계약서는 종이에 무엇이 적혀 있었는지의 기록이다.
    입력값으로 조용히 덮어쓰면 그 사실이 사라진다.
    그래서 덮어쓰지 않고 사용자에게 되돌려 고르게 한다.
    """
    conflicts: list[dict] = []

    pairs = (
        ("worker_name", "근로자 성명", body.worker_name),
        ("employer_name", "대표자", body.employer_name),
    )
    for field_name, label, typed in pairs:
        typed = (typed or "").strip()
        if not typed:
            continue

        on_paper = str(getattr(body.terms, field_name).value or "").strip()
        if not on_paper or on_paper == typed:
            continue

        conflicts.append({
            "field": field_name,
            "label": label,
            "on_contract": on_paper,   # 계약서에서 읽은 값
            "typed": typed,            # 서명 요청에 입력한 값
        })

    return conflicts


@router.post("/contracts/analyze-sign", response_model=AnalyzeSignResponse)
async def analyze_and_sign(body: AnalyzeSignRequest) -> AnalyzeSignResponse:
    """
    조건 확인 → 법정 기준 검증 → 계약서 생성 → 서명 요청.

    위반 항목이 남아 있으면 기본적으로 막는다.
    사용자가 알고도 진행하려면 proceed_with_violations=true 를 보내야 한다.
    """
    # 1단계 — 사람이 확인했는가.
    #
    # 법정 기준 검사보다 먼저 본다. 확인 안 된 값으로 판정해봐야
    # 그 판정 자체를 믿을 수 없기 때문이다.
    unconfirmed = unconfirmed_high_priority(
        body.terms, set(body.confirmed_fields)
    )
    if unconfirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "UNCONFIRMED_FIELDS",
                "message": "확인이 필요한 항목이 남아 있습니다.",
                "fields": unconfirmed,
                "hint": (
                    "AI가 읽은 값이 정확한지 사용자가 확인해야 합니다. "
                    "/contracts/review-items 로 목록을 받아 화면에서 확인한 뒤 "
                    "confirmed_fields 에 담아 다시 요청하세요."
                ),
            },
        )

    # 2단계 — 계약서의 이름과 입력한 이름이 다른가.
    #
    # 어느 쪽이 맞는지 코드는 판단할 수 없으므로 고르지 않고 되돌린다.
    # 사용자가 계약서 값을 고치거나, 입력을 고쳐서 다시 보내야 한다.
    conflicts = _name_conflicts(body)
    if conflicts:
        log.info("이름 불일치: %s", conflicts)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "NAME_MISMATCH",
                "message": "계약서에 적힌 이름과 입력한 이름이 다릅니다.",
                "conflicts": conflicts,
                "hint": (
                    "어느 쪽이 맞는지 확인해 주세요. "
                    "계약서를 잘못 읽었을 수도, 입력이 잘못됐을 수도, "
                    "계약서에 실제로 다른 이름이 적혀 있을 수도 있습니다."
                ),
            },
        )

    terms = body.terms

    # 3단계 — 확인된 값으로 법정 기준 판정
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
        is_draft=False,  # 서명 단계는 양측이 조건을 확인한 것으로 본다
        verification_note=build_verification_note(report),
    )

    try:
        result = await modusign.request_signature(
            pdf_bytes=pdf,
            title=f"근로계약서_{body.worker_name}_{body.employer_name}",
            worker_name=body.worker_name,
            worker_email=body.worker_email,
            employer_name=body.employer_name,
            employer_email=body.employer_email,
        )
    except modusign.ModusignError as e:
        log.error("서명 요청 실패: %s", e)
        raise HTTPException(status_code=502, detail=f"서명 요청 실패: {e}") from e

    return AnalyzeSignResponse(
        document_id=result["id"],
        status=modusign.to_document_status(result["status"]),
        report=report,
        message="검증을 마치고 서명 요청을 보냈습니다. 근로자부터 서명합니다.",
    )
