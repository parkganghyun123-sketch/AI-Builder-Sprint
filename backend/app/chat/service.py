"""계약 비서 챗봇의 안전한 근거 검색과 답변 조립.

벡터 유사도나 자유 생성 대신, 사용자가 확인한 ContractTerms와 결정론적
ValidationReport만 검색한다. 따라서 답변의 사실·숫자·법정 기준은 항상
이미 검증된 값으로 역추적할 수 있다.
"""

from app.chat.small_talk import (
    SMALL_TALK_SUGGESTIONS,
    classify_small_talk,
    small_talk_answer,
)
from app.schemas import (
    ChatAction,
    ChatEvidence,
    ChatEvidenceKind,
    ChatIntent,
    CheckResult,
    CheckStatus,
    ContractChatResponse,
    ContractTerms,
    ValidationReport,
)

OUT_OF_SCOPE_MESSAGE = (
    "이 질문은 계약서만으로 판단할 수 없습니다. 개별 상황에 따라 답이 달라질 수 있어 "
    "고용노동부 고객상담센터 1350 또는 전문가에게 확인해 주세요."
)
OUT_OF_SCOPE_LIMITATION = "실제 근무기록, 사업장 적용 조건, 당사자 간의 사실관계는 이 서비스에서 확인할 수 없습니다."

SUGGESTIONS = [
    "계약서에 적힌 급여·근무시간은 어떻게 되나요?",
    "예상 월급 계산 결과를 알려주세요.",
    "계약서에서 빠진 항목이 있나요?",
    "최저임금 기준을 알려주세요.",
]

FIELD_QUERIES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("시급", "급여", "임금"), "wage_amount", "임금"),
    (("근무시간", "출근", "퇴근"), "work_start_time", "소정근로시간 시작"),
    (("휴게", "쉬는 시간"), "break_start_time", "휴게시간 시작"),
    (("근무일", "며칠", "주당"), "work_days_per_week", "주당 근무일수"),
    (("주휴일", "휴일"), "weekly_holiday_day", "주휴일"),
    (("지급일", "월급날"), "payday", "임금 지급일"),
    (("지급방법", "통장"), "payment_method", "임금 지급 방법"),
    (("근무 장소", "근무장소", "어디서"), "workplace", "근무 장소"),
    (("업무", "일 내용"), "job_description", "업무 내용"),
)

OUT_OF_SCOPE_WORDS = (
    "신고",
    "고소",
    "소송",
    "처벌",
    "불법",
    "위법",
    "대타",
    "실제 근무",
    "개근",
    "퇴사",
    "해고",
    "사장님이",
)


def _text(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contract_evidence(label: str, value: str, source_text: str | None) -> ChatEvidence:
    suffix = f" (계약서 근거: {source_text})" if source_text else " (사용자 확인 값)"
    return ChatEvidence(
        kind=ChatEvidenceKind.CONTRACT,
        label=label,
        value=f"{value}{suffix}",
    )


def _check_evidence(check: CheckResult) -> list[ChatEvidence]:
    evidence = [
        ChatEvidence(
            kind=ChatEvidenceKind.LEGAL_STANDARD,
            label="법정 기준",
            value=f"{check.legal_basis} · {check.standard_year}년 기준",
        )
    ]
    if check.calculation:
        evidence.append(
            ChatEvidence(
                kind=ChatEvidenceKind.VALIDATION,
                label="검증 계산",
                value=check.calculation,
            )
        )
    if check.detail:
        evidence.append(
            ChatEvidence(
                kind=ChatEvidenceKind.VALIDATION,
                label="판정 범위",
                value=check.detail,
            )
        )
    return evidence


def _find_check(report: ValidationReport, question: str) -> CheckResult | None:
    groups = (
        (("최저", "시급", "임금"), "MINIMUM_WAGE"),
        (("주휴", "주휴일"), "WEEKLY_HOLIDAY"),
        (("휴게", "쉬는 시간"), "BREAK_TIME"),
        (("미성년", "청소년", "야간"), "MINOR"),
    )
    for words, code in groups:
        if any(word in question for word in words):
            for check in report.checks:
                if check.code == code or check.code.startswith(code):
                    return check
    return None


def classify(question: str) -> ChatIntent:
    """지원 목록을 보수적으로 분류한다. 애매하면 답을 만들지 않는다."""
    normalized = question.strip().lower()
    if any(word in normalized for word in OUT_OF_SCOPE_WORDS):
        return ChatIntent.OUT_OF_SCOPE
    if classify_small_talk(normalized) is not None:
        return ChatIntent.SMALL_TALK
    if any(word in normalized for word in ("빠진", "누락", "안 적", "미기재", "빈칸")):
        return ChatIntent.MISSING_CLAUSE
    if any(word in normalized for word in ("얼마", "계산", "예상 월급", "월급")):
        return ChatIntent.CALCULATION
    if any(word in normalized for word in ("기준", "법정", "최저임금", "법률", "법")):
        return ChatIntent.LEGAL_STANDARD
    if any(word in normalized for words, _, _ in FIELD_QUERIES for word in words):
        return ChatIntent.FIELD_LOOKUP
    return ChatIntent.NEEDS_CLARIFICATION


def _field_lookup(question: str, terms: ContractTerms) -> ContractChatResponse:
    for words, field_name, label in FIELD_QUERIES:
        if not any(word in question for word in words):
            continue
        field = getattr(terms, field_name)
        value = _text(field.value)
        if value is None:
            return ContractChatResponse(
                intent=ChatIntent.FIELD_LOOKUP,
                answer=f"계약서에서 {label}을(를) 확인하지 못했습니다.",
                limitations="계약서에 없는 내용을 추정하거나 보완할 수 없습니다.",
                evidence=[],
                action=ChatAction(label="계약 조건 입력·수정", href="/review"),
            )
        return ContractChatResponse(
            intent=ChatIntent.FIELD_LOOKUP,
            answer=f"확인된 {label}은(는) {value}입니다.",
            limitations="계약서에서 추출되었거나 사용자가 확인한 값만 안내합니다.",
            evidence=[_contract_evidence(label, value, field.source_text)],
        )
    return _clarification()


def _calculation(
    question: str, terms: ContractTerms, report: ValidationReport
) -> ContractChatResponse:
    if report.estimated_monthly_pay is not None:
        amount = f"{report.estimated_monthly_pay:,}원"
        return ContractChatResponse(
            intent=ChatIntent.CALCULATION,
            answer=f"검증 엔진이 계산한 예상 월급은 {amount}입니다.",
            limitations="예상 금액은 확인된 계약 조건을 바탕으로 한 계산값이며, 실제 근무기록이나 추가 수당은 반영하지 않습니다.",
            evidence=[
                ChatEvidence(
                    kind=ChatEvidenceKind.VALIDATION,
                    label="예상 월급 계산",
                    value=amount,
                )
            ],
        )

    check = _find_check(report, question)
    if check:
        return ContractChatResponse(
            intent=ChatIntent.CALCULATION,
            answer=(
                check.detail
                or "확인된 계약 조건으로는 추가 계산 결과를 만들 수 없습니다."
            ),
            limitations="계산은 검증 엔진 결과만 사용하며, 실제 근무기록은 반영하지 않습니다.",
            evidence=_check_evidence(check),
        )

    return ContractChatResponse(
        intent=ChatIntent.CALCULATION,
        answer="확인된 계약 조건만으로는 예상 금액을 계산할 수 없습니다.",
        limitations="누락된 계약 조건을 추정하지 않습니다.",
        evidence=[],
        action=ChatAction(label="계약 조건 입력·수정", href="/review"),
    )


def _missing_clause(report: ValidationReport) -> ContractChatResponse:
    missing = [check for check in report.checks if check.status == CheckStatus.MISSING]
    if not missing:
        return ContractChatResponse(
            intent=ChatIntent.MISSING_CLAUSE,
            answer="현재 검증에서는 계약서에서 찾지 못한 필수 항목이 없습니다.",
            limitations="이 결과는 서비스가 지원하는 표준 계약 항목 범위에 한정됩니다.",
            evidence=[],
        )
    labels = ", ".join(check.label for check in missing)
    evidence: list[ChatEvidence] = []
    for check in missing:
        evidence.extend(_check_evidence(check))
    return ContractChatResponse(
        intent=ChatIntent.MISSING_CLAUSE,
        answer=f"계약서에서 확인하지 못한 항목은 {labels}입니다.",
        limitations="누락은 계약서에서 값을 찾지 못했다는 뜻이며, 개별 상황의 법적 결론은 아닙니다.",
        evidence=evidence,
        action=ChatAction(label="빠진 항목 확인·수정", href="/review"),
    )


def _legal_standard(question: str, report: ValidationReport) -> ContractChatResponse:
    check = _find_check(report, question)
    if check is None:
        return ContractChatResponse(
            intent=ChatIntent.LEGAL_STANDARD,
            answer="이 서비스에서 확인된 법정 기준은 최저임금, 주휴일, 휴게시간입니다.",
            limitations="지원하지 않는 법정 기준이나 개별 분쟁 판단은 안내하지 않습니다.",
            evidence=[],
            suggestions=[
                "최저임금 기준을 알려주세요.",
                "주휴일 기준을 알려주세요.",
                "휴게시간 기준을 알려주세요.",
            ],
        )
    return ContractChatResponse(
        intent=ChatIntent.LEGAL_STANDARD,
        answer=(check.detail or f"{check.label} 기준을 현재 계약 조건과 비교했습니다."),
        limitations="법정 기준은 응답에 표시된 적용 연도와 계약서에서 확인한 조건 범위에서만 안내합니다.",
        evidence=_check_evidence(check),
    )


def _out_of_scope() -> ContractChatResponse:
    return ContractChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        answer=OUT_OF_SCOPE_MESSAGE,
        limitations=OUT_OF_SCOPE_LIMITATION,
        evidence=[
            ChatEvidence(
                kind=ChatEvidenceKind.OFFICIAL_GUIDANCE,
                label="공식 상담 안내",
                value="고용노동부 고객상담센터 1350",
            )
        ],
        suggestions=SUGGESTIONS,
    )


def _small_talk(question: str) -> ContractChatResponse:
    kind = classify_small_talk(question)
    if kind is None:
        return _clarification()
    return ContractChatResponse(
        intent=ChatIntent.SMALL_TALK,
        answer=small_talk_answer(kind),
        limitations="근로계약과 노동 기준 안내를 중심으로 도와드려요.",
        evidence=[],
        suggestions=SMALL_TALK_SUGGESTIONS,
    )


def _clarification() -> ContractChatResponse:
    return ContractChatResponse(
        intent=ChatIntent.NEEDS_CLARIFICATION,
        answer="질문이 계약서의 어떤 항목에 관한 것인지 확인하지 못했습니다. 아래 범주 중 하나로 질문해 주세요.",
        limitations="지원 범주 밖의 질문에는 답을 추정하지 않습니다.",
        evidence=[],
        suggestions=SUGGESTIONS,
    )


def answer(
    question: str, terms: ContractTerms, report: ValidationReport
) -> ContractChatResponse:
    """질문을 분류하고, 허용된 출처에서만 근거 카드를 조립한다."""
    intent = classify(question)
    if intent == ChatIntent.OUT_OF_SCOPE:
        return _out_of_scope()
    if intent == ChatIntent.SMALL_TALK:
        return _small_talk(question)
    if intent == ChatIntent.MISSING_CLAUSE:
        return _missing_clause(report)
    if intent == ChatIntent.CALCULATION:
        return _calculation(question, terms, report)
    if intent == ChatIntent.LEGAL_STANDARD:
        return _legal_standard(question, report)
    if intent == ChatIntent.FIELD_LOOKUP:
        return _field_lookup(question, terms)
    return _clarification()
