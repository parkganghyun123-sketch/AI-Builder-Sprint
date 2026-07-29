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


def _validate_with_optional_birth_date(
    terms: ContractTerms,
    worker_birth_date: str | None,
) -> ValidationReport:
    """생년월일 미입력 요청은 기존 한 인자 검증 호출과 호환한다."""

    if worker_birth_date is None:
        return validate(terms)
    return validate(terms, worker_birth_date=worker_birth_date)


# ============================================================
# 1. 검증만
# ============================================================


class ValidateRequest(BaseModel):
    terms: ContractTerms
    worker_birth_date: str | None = None


@router.post("/contracts/validate", response_model=ValidationReport)
async def validate_terms(body: ValidateRequest) -> ValidationReport:
    """
    계약 조건을 법정 기준과 대조한다.

    입력은 사용자가 확인·수정을 마친 조건이어야 한다.
    AI 추출 직후 값을 그대로 넣으면 안 된다.
    """
    return _validate_with_optional_birth_date(
        _minimize_contact_fields(body.terms),
        body.worker_birth_date,
    )


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


# 경로 B(근로자가 조건을 직접 입력)로 만들어진 문서에 붙이는 출처 표시.
#
# 서명할 문서에는 '확인 전 초안' 워터마크를 찍지 않는다(analyze_and_sign 주석 참고).
# 대신 조건의 출처를 문장으로 밝혀, 사업주가 무엇에 서명하는지 알 수 있게 한다.
MANUAL_ENTRY_NOTICE = (
    "※ 본 문서의 근로조건은 근로자가 구두로 안내받은 내용을 직접 입력한 것입니다. "
    "사실과 다른 부분이 있으면 서명 전에 수정을 요청해 주세요."
)


def build_verification_note(
    report: ValidationReport,
    entry_path: EntryPath = EntryPath.PHOTO,
) -> str:
    """
    판정 결과를 계약서 하단에 넣을 한 문단으로 만든다.

    ⚠️ 여기서 새로운 사실이나 숫자를 만들지 않는다.
       CheckResult가 담고 있는 값만 옮긴다.
    """
    prefix = (
        f"{MANUAL_ENTRY_NOTICE}\n\n"
        if entry_path == EntryPath.MANUAL
        else ""
    )
    problems = [
        c
        for c in report.checks
        if c.status in (CheckStatus.VIOLATION, CheckStatus.MISSING)
    ]

    if not problems:
        return prefix + (
            "※ 본 문서는 FairSign에서 지원하는 2026년 법정 기준 항목을 "
            "확인했으며, 확인된 범위에서 기준을 벗어나거나 누락된 항목이 "
            "발견되지 않았습니다. 법률 자문이 아닙니다."
        )

    lines = []
    for check in problems:
        evidence = []
        if check.calculation:
            evidence.append(f"계산: {check.calculation}")
        if check.detail:
            evidence.append(f"안내: {check.detail}")
        lines.append(f"· {check.label}: {' / '.join(evidence) or '확인 필요'}")

    return prefix + (
        "※ FairSign 확인 결과(2026년 기준), 아래 항목은 지원하는 기본 기준을 "
        "벗어났거나 확인된 입력에서 찾지 못했거나 추가 확인이 필요합니다. "
        "이 문서는 해당 결과를 자동으로 수정하지 않습니다.\n"
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
    worker_birth_date: str | None = None
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

    # 3단계 — 확인된 값으로 법정 기준 판정
    terms = _minimize_contact_fields(body.terms)
    report = _validate_with_optional_birth_date(terms, body.worker_birth_date)

    if report.has_problem and not body.proceed_with_violations:
        problem_checks = [
            check
            for check in report.checks
            if check.status in (CheckStatus.VIOLATION, CheckStatus.MISSING)
        ]
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "기본 기준 초과·누락 또는 추가 확인이 필요한 항목이 있습니다."
                ),
                "problems": [check.label for check in problem_checks],
                "problem_details": [
                    {
                        "code": check.code,
                        "label": check.label,
                        "calculation": check.calculation,
                        "detail": check.detail,
                    }
                    for check in problem_checks
                ],
                "hint": "조건을 수정하거나 proceed_with_violations=true 로 다시 요청하세요.",
            },
        )

    pdf = render_contract_pdf(
        terms,
        # 서명할 문서에는 '확인 전 초안' 워터마크를 찍지 않는다.
        #
        # 워터마크의 원래 목적은 경로 B(근로자가 혼자 입력)에서
        # 사장님이 그 문서를 이미 합의된 계약서로 오해하는 것을 막는 것이다.
        # 그건 서명 전 단계(/contracts/preview)의 문제다.
        #
        # 이 문서는 양측이 읽고 서명한다 — 서명이 곧 확인이다.
        # 체결된 문서에 '초안' 표기가 남으면
        #   · 분쟁 시 "초안인 줄 알았다"는 주장의 빌미가 되고
        #   · 근로기준법 제17조 교부 의무를 이행한 증거로도 약해진다
        #
        # 경로 B의 투명성은 워터마크가 아니라 검증 문단의 출처 표시로 확보한다.
        is_draft=False,
        verification_note=build_verification_note(report, body.entry_path),
    )

    try:
        result = await modusign.request_signature(
            pdf_bytes=pdf,
            # 이름을 넣지 않는다. 모두싸인 문서 목록·메일 제목에 노출된다.
            title="근로계약서",
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
