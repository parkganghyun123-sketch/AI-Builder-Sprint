"""검증된 계약 데이터와 결정론적 판정만으로 챗봇 답변을 조립한다."""

from collections.abc import Callable

from app.chat.models import (
    ChatEvidence,
    ChatIntent,
    ChatResponse,
    ChatTopic,
    Classification,
    ConditionGroups,
    EvidenceKind,
)
from app.schemas import (
    CheckResult,
    CheckStatus,
    Confidence,
    ContractTerms,
    ExtractedField,
)
from app.validation.constants import (
    MINIMUM_WAGE_2026,
    PROBATION_MINIMUM_WAGE_2026,
    STANDARD_YEAR,
    WEEKLY_HOLIDAY_MIN_HOURS,
)
from app.validation.rules import (
    check_annual_leave_indicators,
    check_dismissal_notice_indicator,
    check_probation_minimum_wage,
    check_severance_pay,
    check_social_insurance_indicators,
    validate,
)

OUT_OF_SCOPE_ANSWER = (
    "이 질문은 계약서만으로 판단할 수 없습니다. 개별 상황에 따라 답이 달라질 수 있어, "
    "고용노동부 고객상담센터(☎1350)에서 확인하시는 것을 권합니다."
)
COMMON_SUGGESTIONS = [
    "나 지금 주휴수당 시간 요건을 충족하나요?",
    "계약서에 빠진 내용이 있나요?",
    "2026년 최저임금은 얼마인가요?",
]


def is_fail_closed_question(question: str) -> bool:
    normalized = "".join(question.lower().split())
    blocked = (
        "신고",
        "고소",
        "소송",
        "부당해고",
        "해고당",
        "노동청",
        "진정",
        "체불",
        "임금미지급",
        "급여안주",
        "돈안주",
        "월급못받",
        "못받음",
        "못받았",
        "친구가대신",
        "친구대신",
        "동료가대신",
        "동료대신",
        "대신일",
        "대신근무",
        "교대",
        "근무일교환",
        "근무일을교환",
        "근무일바꿨",
        "실제근무",
        "실제로일",
        "출근",
        "지난주",
        "이번주",
        "대타",
        "개근했",
        "개근",
        "결근",
        "추가근무",
        "연장근무",
        "야근",
        "퇴사",
        "그만두",
        "이길수",
    )
    if any(keyword in normalized for keyword in blocked):
        return True

    # 계약서의 소정근로시간만으로 답할 수 없는 실제 출결·교대 사실을 닫힌
    # 문맥+행동 조합으로 탐지한다. 단순히 "빠진 조항"이라고 물은 경우는
    # 출결 문맥이 없으므로 차단하지 않는다.
    fact_dependent_patterns = (
        (
            ("하루", "근무일", "출근일"),
            ("빠졌", "빠진날", "안나갔", "못나갔", "쉬었", "불참"),
        ),
        (
            ("스케줄", "근무일", "근무시간"),
            ("바꿔", "바꿈", "교환", "서로변경"),
        ),
        (
            ("다른사람", "친구", "동료", "대신할사람"),
            ("해줬", "일해줬", "근무해줬", "대신", "맡겼"),
        ),
    )
    return any(
        any(context in normalized for context in contexts)
        and any(action in normalized for action in actions)
        for contexts, actions in fact_dependent_patterns
    )


def out_of_scope_response() -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        topic=ChatTopic.UNSUPPORTED,
        answer=OUT_OF_SCOPE_ANSWER,
        evidence=[],
        limitation="FairSign은 계약서 내용과 지원하는 법정 기준만 설명하며 법률 자문을 제공하지 않습니다.",
        suggested_questions=COMMON_SUGGESTIONS,
    )


def _known(field: ExtractedField) -> bool:
    return (
        field.confidence != Confidence.NOT_FOUND
        and field.value is not None
        and (not isinstance(field.value, str) or bool(field.value.strip()))
    )


def _contract_evidence(title: str, detail: str) -> ChatEvidence:
    return ChatEvidence(kind=EvidenceKind.CONTRACT, title=title, detail=detail)


def _check_evidence(check: CheckResult) -> list[ChatEvidence]:
    evidence = [
        ChatEvidence(
            kind=EvidenceKind.LEGAL,
            title=f"법정 기준 ({check.standard_year}년 기준)",
            detail=check.legal_basis,
        )
    ]
    if check.calculation:
        evidence.append(
            ChatEvidence(
                kind=EvidenceKind.CALCULATION,
                title="계약 조건 계산",
                detail=check.calculation,
            )
        )
    return evidence


def _weekly_holiday(terms: ContractTerms, birth_date: str | None) -> ChatResponse:
    check = next(
        item
        for item in validate(terms, worker_birth_date=birth_date).checks
        if item.code == "WEEKLY_HOLIDAY"
    )
    contract_detail = "근무시간 또는 주 근무일수가 계약서에서 확인되지 않습니다."
    if terms.hours_per_day is not None and _known(terms.work_days_per_week):
        contract_detail = (
            f"1일 소정근로시간 {terms.hours_per_day:g}시간, "
            f"주 {terms.work_days_per_week.value}일"
        )

    met: list[str] = []
    unmet: list[str] = []
    needs_check = [
        "소정근로일 개근 여부",
        "계약과 실제 근무 내용의 일치 여부",
        "실제 주휴수당 지급 내역",
    ]
    if check.status == CheckStatus.UNKNOWN:
        answer = "계약서 정보가 부족해 주휴수당의 주 15시간 요건을 계산할 수 없습니다."
        needs_check.insert(0, "계약서의 근무시간과 주 근무일 수")
    elif (
        terms.weekly_hours is not None
        and terms.weekly_hours >= WEEKLY_HOLIDAY_MIN_HOURS
    ):
        answer = (
            "계약상 주 소정근로시간을 기준으로 보면 주휴수당 지급 조건 중 "
            "시간 요건을 충족합니다."
        )
        met.append(f"계약상 주 소정근로시간 {terms.weekly_hours:g}시간은 15시간 이상")
    else:
        answer = (
            "계약상 주 소정근로시간을 기준으로 보면 주휴수당 지급 조건 중 "
            "시간 요건을 충족하지 않습니다."
        )
        if terms.weekly_hours is not None:
            unmet.append(
                f"계약상 주 소정근로시간 {terms.weekly_hours:g}시간은 15시간 미만"
            )

    return ChatResponse(
        intent=ChatIntent.CALCULATION,
        topic=ChatTopic.WEEKLY_HOLIDAY,
        answer=answer,
        evidence=[
            _contract_evidence("계약서의 소정근로시간", contract_detail),
            *_check_evidence(check),
        ],
        limitation=None,
        condition_groups=ConditionGroups(
            met=met,
            unmet=unmet,
            needs_check=needs_check,
        ),
        suggested_questions=["주휴일은 계약서에 적혀 있나요?", *COMMON_SUGGESTIONS[1:]],
    )


def _severance_pay(terms: ContractTerms) -> ChatResponse:
    result = check_severance_pay(terms)
    met: list[str] = []
    unmet: list[str] = []
    needs_check = [
        "실제 입사일·퇴사일과 계속근로 여부",
        "계속근로기간 중 주 소정근로시간 변경 여부",
        "실제 퇴직 여부",
    ]

    if result.planned_one_year is True:
        met.append("계약상 예정 근로기간이 1년 이상")
    elif result.planned_one_year is False:
        unmet.append("계약상 예정 근로기간이 1년 미만")
    else:
        needs_check.insert(0, "계약 시작일·종료일과 계약상 예정 근로기간")

    if result.weekly_hours_15 is True:
        met.append(
            "4주 평균 기준(현재 계약상 주간 일정으로 비교): "
            "주 소정근로시간이 15시간 이상"
        )
    elif result.weekly_hours_15 is False:
        unmet.append(
            "4주 평균 기준(현재 계약상 주간 일정으로 비교): "
            "주 소정근로시간이 15시간 미만"
        )
    else:
        needs_check.insert(0, "계약상 주 소정근로시간")

    if unmet:
        answer = "계약 조건상 퇴직급여 관련 기준 중 충족하지 않는 항목이 있습니다."
    elif result.planned_one_year is None or result.weekly_hours_15 is None:
        answer = "계약서 정보가 부족해 퇴직급여 관련 두 기준을 모두 확인할 수 없습니다."
    else:
        answer = "계약 조건상 퇴직급여 관련 두 기준을 충족합니다."

    return ChatResponse(
        intent=ChatIntent.CALCULATION,
        topic=ChatTopic.SEVERANCE_PAY,
        answer=answer,
        evidence=[
            _contract_evidence("계약상 예정 근로기간", result.period_calculation),
            ChatEvidence(
                kind=EvidenceKind.LEGAL,
                title=f"퇴직급여 관련 기준 ({STANDARD_YEAR}년 확인)",
                detail=result.legal_basis,
            ),
            ChatEvidence(
                kind=EvidenceKind.CALCULATION,
                title="계약상 예정 기간·현재 주간 일정 비교",
                detail=(
                    f"{result.period_calculation} / {result.weekly_hours_calculation}"
                ),
            ),
        ],
        limitation=None,
        condition_groups=ConditionGroups(
            met=met,
            unmet=unmet,
            needs_check=needs_check,
        ),
        suggested_questions=[
            "계약기간이 어떻게 되나요?",
            "계약상 주 근로시간은 몇 시간인가요?",
            *COMMON_SUGGESTIONS[:2],
        ],
    )


def _policy_response(
    *,
    topic: ChatTopic,
    answer: str,
    basis: str,
    calculation: str,
    met: list[str],
    unmet: list[str],
    needs_check: list[str],
) -> ChatResponse:
    return ChatResponse(
        intent=ChatIntent.CALCULATION,
        topic=topic,
        answer=answer,
        evidence=[
            ChatEvidence(
                kind=EvidenceKind.LEGAL,
                title=f"지원 기준 ({STANDARD_YEAR}년 확인)",
                detail=basis,
            ),
            ChatEvidence(
                kind=EvidenceKind.CALCULATION,
                title="현재 계약 조건 지표",
                detail=calculation,
            ),
        ],
        limitation=None,
        condition_groups=ConditionGroups(
            met=met,
            unmet=unmet,
            needs_check=needs_check,
        ),
        suggested_questions=COMMON_SUGGESTIONS,
    )


def _annual_leave(terms: ContractTerms) -> ChatResponse:
    result = check_annual_leave_indicators(terms)
    met: list[str] = []
    unmet: list[str] = []
    needs = [
        "상시 5명 이상 사업장인지",
        "실제 계속근로기간",
        "1년간 출근율 80% 또는 1개월 개근 여부",
        "이미 사용한 연차와 휴가 내역",
    ]
    if result.planned_one_year is True:
        met.append("계약상 예정기간이 1년 이상")
    elif result.planned_one_year is False:
        unmet.append("계약상 예정기간이 1년 미만")
    else:
        needs.insert(0, "계약 시작일·종료일")
    if result.weekly_hours_15 is True:
        met.append(
            "현재 계약상 주간 일정으로 비교한 4주 평균 주 소정근로시간 지표가 15시간 이상"
        )
    elif result.weekly_hours_15 is False:
        unmet.append(
            "현재 계약상 주간 일정으로 비교한 4주 평균 주 소정근로시간 지표가 15시간 미만"
        )
    else:
        needs.insert(0, "현재 계약상 주 소정근로시간")
    return _policy_response(
        topic=ChatTopic.ANNUAL_LEAVE,
        answer="계약에서 확인 가능한 연차 관련 기간·시간 지표를 정리했습니다.",
        basis=result.legal_basis,
        calculation=f"{result.period_calculation} / {result.weekly_hours_calculation}",
        met=met,
        unmet=unmet,
        needs_check=needs,
    )


def _dismissal_notice(terms: ContractTerms) -> ChatResponse:
    result = check_dismissal_notice_indicator(terms)
    met: list[str] = []
    unmet: list[str] = []
    needs = [
        "실제 해고인지 계약기간 만료인지",
        "해고 시점의 실제 계속근로기간",
        "30일 전 예고 여부",
        "30일분 통상임금 산정에 필요한 임금자료",
        "법정 예외사유 해당 여부",
    ]
    if result.planned_three_months is True:
        met.append("현재 계약의 예정기간이 3개월 이상")
    elif result.planned_three_months is False:
        unmet.append("현재 계약의 예정기간이 3개월 미만")
    else:
        needs.insert(0, "계약 시작일·종료일")
    return _policy_response(
        topic=ChatTopic.DISMISSAL_NOTICE,
        answer="계약상 예정기간 지표만 확인했으며 해고예고수당 여부는 확정할 수 없습니다.",
        basis=result.legal_basis,
        calculation=result.calculation,
        met=met,
        unmet=unmet,
        needs_check=needs,
    )


def _probation_minimum_wage(terms: ContractTerms) -> ChatResponse:
    result = check_probation_minimum_wage(terms)
    met: list[str] = []
    unmet: list[str] = []
    needs = [
        "수습 약정 존재 여부",
        "수습 시작일부터 3개월 이내인지",
        "단순노무 직종 해당 여부",
        "최저임금 산입 임금 범위",
    ]
    if result.planned_one_year is True:
        met.append("계약상 예정기간이 1년 이상")
    elif result.planned_one_year is False:
        unmet.append("계약상 예정기간이 1년 미만")
    else:
        needs.insert(0, "계약 시작일·종료일")
    if result.meets_regular_minimum is True:
        met.append(f"계약상 시급이 일반 최저임금 {MINIMUM_WAGE_2026:,}원 이상")
    elif result.meets_discounted_floor is True:
        met.append(
            f"계약상 시급이 최대 10% 감액 하한 {PROBATION_MINIMUM_WAGE_2026:,}원 이상"
        )
        needs.insert(0, "수습 감액의 모든 법정 전제 충족 여부")
    elif result.meets_discounted_floor is False:
        unmet.append(
            f"계약상 시급이 최대 10% 감액 하한 {PROBATION_MINIMUM_WAGE_2026:,}원 미만"
        )
    else:
        needs.insert(0, "계약상 시간급")
    return _policy_response(
        topic=ChatTopic.PROBATION_MINIMUM_WAGE,
        answer="계약기간과 시급을 수습 최저임금 관련 기준과 비교했습니다.",
        basis=result.legal_basis,
        calculation=f"{result.period_calculation} / {result.wage_calculation}",
        met=met,
        unmet=unmet,
        needs_check=needs,
    )


def _social_insurance(terms: ContractTerms) -> ChatResponse:
    result = check_social_insurance_indicators(terms)
    met: list[str] = []
    unmet: list[str] = []
    needs = [
        "산재보험: 근로자성·적용 업종과 예외",
        "고용보험: 월 60시간, 3개월 이상 계속근로 또는 일용근로 예외",
        "건강보험: 월 소정근로시간 60시간 기준",
        "국민연금: 나이·실제 소득·월 근로일수와 시간 예외",
    ]
    if result.weekly_hours_15 is True:
        met.append("현재 계약상 주 소정근로시간이 15시간 이상")
    elif result.weekly_hours_15 is False:
        needs.insert(
            0,
            "현재 계약상 주 15시간 미만 — 국민연금·건강보험·고용보험의 "
            "월시간·기간·소득 예외 확인 필요",
        )
    else:
        needs.insert(0, "현재 계약상 주 소정근로시간")
    return _policy_response(
        topic=ChatTopic.SOCIAL_INSURANCE,
        answer="4대보험 가입 여부를 하나로 단정하지 않고 보험별 확인사항을 정리했습니다.",
        basis=result.legal_basis,
        calculation=result.weekly_hours_calculation,
        met=met,
        unmet=unmet,
        needs_check=needs,
    )


def _validation_check(
    terms: ContractTerms,
    birth_date: str | None,
    *,
    code: str,
    topic: ChatTopic,
) -> ChatResponse:
    check = next(
        item
        for item in validate(terms, worker_birth_date=birth_date).checks
        if item.code == code
    )
    status_text = {
        CheckStatus.OK: "확인된 계약 조건은 지원하는 기준을 충족합니다.",
        CheckStatus.VIOLATION: "확인된 계약 조건이 지원하는 기준에 미달합니다.",
        CheckStatus.MISSING: "계약서에서 필요한 항목을 확인하지 못했습니다.",
        CheckStatus.UNKNOWN: "계약서 정보가 부족해 비교할 수 없습니다.",
    }[check.status]
    return ChatResponse(
        intent=ChatIntent.CALCULATION,
        topic=topic,
        answer=status_text,
        evidence=_check_evidence(check),
        limitation=check.detail,
        suggested_questions=COMMON_SUGGESTIONS,
    )


def _field_lookup(terms: ContractTerms, topic: ChatTopic) -> ChatResponse:
    field_map: dict[ChatTopic, tuple[str, ExtractedField, Callable[[object], str]]] = {
        ChatTopic.PAYDAY: ("임금 지급일", terms.payday, str),
        ChatTopic.WORKPLACE: ("근무 장소", terms.workplace, str),
        ChatTopic.JOB: ("업무 내용", terms.job_description, str),
        ChatTopic.WAGE: (
            "계약 임금",
            terms.wage_amount,
            lambda value: f"{int(value):,}원",
        ),
    }
    if topic == ChatTopic.CONTRACT_PERIOD:
        start = (
            str(terms.contract_start.value) if _known(terms.contract_start) else None
        )
        end = str(terms.contract_end.value) if _known(terms.contract_end) else None
        if start and end:
            detail = f"{start}부터 {end}까지"
        elif start:
            detail = f"시작일 {start}, 종료일은 확인되지 않음"
        else:
            detail = "계약기간이 확인되지 않음"
        return ChatResponse(
            intent=ChatIntent.FIELD_LOOKUP,
            topic=topic,
            answer=f"계약서의 근로계약기간은 {detail}입니다.",
            evidence=[_contract_evidence("근로계약기간", detail)],
            limitation=None if start else "계약서에서 시작일을 확인하지 못했습니다.",
            suggested_questions=COMMON_SUGGESTIONS,
        )

    entry = field_map.get(topic)
    if entry is None:
        return out_of_scope_response()
    title, field, formatter = entry
    if not _known(field):
        return ChatResponse(
            intent=ChatIntent.FIELD_LOOKUP,
            topic=topic,
            answer=f"계약서에서 {title}을 확인하지 못했습니다.",
            evidence=[_contract_evidence(title, "기재 내용 확인 불가")],
            limitation="없는 값을 추정하지 않았습니다.",
            suggested_questions=COMMON_SUGGESTIONS,
        )
    try:
        value = formatter(field.value)
    except (TypeError, ValueError):
        value = str(field.value)
    return ChatResponse(
        intent=ChatIntent.FIELD_LOOKUP,
        topic=topic,
        answer=f"계약서에 적힌 {title}은 {value}입니다.",
        evidence=[_contract_evidence(title, value)],
        limitation=None,
        suggested_questions=COMMON_SUGGESTIONS,
    )


def _missing_clauses(terms: ContractTerms, birth_date: str | None) -> ChatResponse:
    missing = [
        check
        for check in validate(terms, worker_birth_date=birth_date).checks
        if check.status == CheckStatus.MISSING
    ]
    if not missing:
        return ChatResponse(
            intent=ChatIntent.MISSING_CLAUSE,
            topic=ChatTopic.MISSING_CLAUSES,
            answer="지원하는 필수 항목 범위에서는 계약서에서 누락된 항목을 찾지 못했습니다.",
            evidence=[
                ChatEvidence(
                    kind=EvidenceKind.LEGAL,
                    title=f"필수 기재사항 ({STANDARD_YEAR}년 기준)",
                    detail="근로기준법 제17조·고용노동부 표준근로계약서",
                )
            ],
            limitation="FairSign이 현재 지원하는 필수 항목만 확인한 결과입니다.",
            suggested_questions=COMMON_SUGGESTIONS,
        )
    labels = ", ".join(check.label for check in missing)
    return ChatResponse(
        intent=ChatIntent.MISSING_CLAUSE,
        topic=ChatTopic.MISSING_CLAUSES,
        answer=f"확인된 계약서에서 다음 항목을 찾지 못했습니다: {labels}.",
        evidence=[
            ChatEvidence(
                kind=EvidenceKind.CONTRACT,
                title="확인되지 않은 항목",
                detail=labels,
            ),
            ChatEvidence(
                kind=EvidenceKind.LEGAL,
                title=f"필수 기재사항 ({STANDARD_YEAR}년 기준)",
                detail="근로기준법 제17조·고용노동부 표준근로계약서",
            ),
        ],
        limitation="문서에 실제로 없거나 추출 과정에서 확인하지 못한 항목일 수 있습니다.",
        suggested_questions=COMMON_SUGGESTIONS,
    )


def _legal_standard(topic: ChatTopic) -> ChatResponse:
    standards = {
        ChatTopic.MINIMUM_WAGE: (
            f"{STANDARD_YEAR}년 적용 최저임금은 시간급 {MINIMUM_WAGE_2026:,}원입니다.",
            "최저임금위원회 2026년 적용 최저임금 (SRC-MINWAGE-2026)",
        ),
        ChatTopic.WEEKLY_HOLIDAY: (
            f"주휴수당 관련 시간 기준은 4주 평균 1주 소정근로시간 {WEEKLY_HOLIDAY_MIN_HOURS:g}시간 이상입니다.",
            "근로기준법 제18조제3항·제55조 (SRC-LSA-18)",
        ),
        ChatTopic.BREAK_TIME: (
            "근로시간이 4시간이면 30분 이상, 8시간이면 1시간 이상의 휴게시간 기준을 확인합니다.",
            "근로기준법 제54조 (SRC-LSA-54-CURRENT)",
        ),
    }
    standard = standards.get(topic)
    if standard is None:
        return out_of_scope_response()
    answer, basis = standard
    return ChatResponse(
        intent=ChatIntent.LEGAL_STANDARD,
        topic=topic,
        answer=answer,
        evidence=[
            ChatEvidence(
                kind=EvidenceKind.LEGAL,
                title=f"법정 기준 ({STANDARD_YEAR}년 기준)",
                detail=basis,
            )
        ],
        limitation="일반 기준 안내이며 개별 상황에 대한 법률 판단이 아닙니다.",
        suggested_questions=COMMON_SUGGESTIONS,
    )


def build_response(
    classification: Classification,
    terms: ContractTerms,
    worker_birth_date: str | None,
) -> ChatResponse:
    if classification.intent == ChatIntent.OUT_OF_SCOPE:
        return out_of_scope_response()
    if classification.intent == ChatIntent.FIELD_LOOKUP:
        return _field_lookup(terms, classification.topic)
    if classification.intent == ChatIntent.MISSING_CLAUSE:
        return _missing_clauses(terms, worker_birth_date)
    if classification.intent == ChatIntent.LEGAL_STANDARD:
        return _legal_standard(classification.topic)
    if classification.intent == ChatIntent.CALCULATION:
        if classification.topic == ChatTopic.WEEKLY_HOLIDAY:
            return _weekly_holiday(terms, worker_birth_date)
        if classification.topic == ChatTopic.SEVERANCE_PAY:
            return _severance_pay(terms)
        if classification.topic == ChatTopic.SOCIAL_INSURANCE:
            return _social_insurance(terms)
        if classification.topic == ChatTopic.ANNUAL_LEAVE:
            return _annual_leave(terms)
        if classification.topic == ChatTopic.DISMISSAL_NOTICE:
            return _dismissal_notice(terms)
        if classification.topic == ChatTopic.PROBATION_MINIMUM_WAGE:
            return _probation_minimum_wage(terms)
        if classification.topic == ChatTopic.MINIMUM_WAGE:
            return _validation_check(
                terms,
                worker_birth_date,
                code="MINIMUM_WAGE",
                topic=classification.topic,
            )
        if classification.topic == ChatTopic.BREAK_TIME:
            return _validation_check(
                terms,
                worker_birth_date,
                code="BREAK_TIME",
                topic=classification.topic,
            )
    return out_of_scope_response()
