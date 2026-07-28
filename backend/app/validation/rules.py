"""
검증 엔진 — 우리 서비스의 심장.

⚠️ 절대 규칙: 이 파일에서 LLM을 호출하지 않는다. 판정은 100% 결정론적 코드로 한다.
모든 순수 함수는 ContractTerms만 입력으로 받고, 외부 호출·전역 상태를 갖지 않는다.
"""

from app.schemas import (
    CheckResult,
    CheckStatus,
    Confidence,
    ContractTerms,
    ExtractedField,
    ValidationReport,
    WageType,
)
from app.validation.constants import (
    AVG_WEEKS_PER_MONTH,
    BREAK_RULES,
    MINIMUM_WAGE_2026,
    MINIMUM_WAGE_YEAR,
    WEEKLY_HOLIDAY_MIN_HOURS,
)

# weekly_holiday_day는 check_weekly_holiday에서 별도로 판정하므로 여기서는 제외한다.
_REQUIRED_FIELD_LABELS: dict[str, str] = {
    "contract_start": "근로계약기간(시작일)",
    "contract_end": "근로계약기간(종료일)",
    "workplace": "근무장소",
    "job_description": "업무의 내용",
    "work_start_time": "시업 시각",
    "work_end_time": "종업 시각",
    "break_start_time": "휴게 시작 시각",
    "break_end_time": "휴게 종료 시각",
    "work_days_per_week": "근무일수",
    "wage_type": "임금 형태",
    "wage_amount": "임금액",
    "has_bonus": "상여금 여부",
    "other_allowance": "기타급여",
    "payday": "임금지급일",
    "payment_method": "지급방법",
    "employer_business_name": "사업체명",
    "employer_address": "사업체 주소",
    "employer_name": "대표자명",
    "worker_address": "근로자 주소",
    "worker_contact": "근로자 연락처",
    "worker_name": "근로자 성명",
}


def _is_missing(field: ExtractedField) -> bool:
    return field.confidence == Confidence.NOT_FOUND or field.value in (None, "")


def _required_break_minutes(hours: float) -> int:
    """근로시간(시간)에 따른 법정 최소 휴게시간(분). 해당 없으면 0."""
    required = 0
    for threshold_hours, min_break in BREAK_RULES:
        if hours >= threshold_hours:
            required = max(required, min_break)
    return required


def check_minimum_wage(terms: ContractTerms) -> CheckResult:
    if terms.wage_type.value != WageType.HOURLY.value:
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.UNKNOWN,
            legal_basis="최저임금법",
            standard_year=MINIMUM_WAGE_YEAR,
            detail="시간급으로 기재된 계약만 판정합니다.",
        )

    wage = terms.hourly_wage
    if wage is None:
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.UNKNOWN,
            legal_basis="최저임금법",
            standard_year=MINIMUM_WAGE_YEAR,
            detail="시급 정보가 없어 판정할 수 없습니다.",
        )

    legal_basis = f"최저임금법 · {MINIMUM_WAGE_YEAR}년 최저임금 고시"
    if wage < MINIMUM_WAGE_2026:
        diff = MINIMUM_WAGE_2026 - wage
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.VIOLATION,
            legal_basis=legal_basis,
            standard_year=MINIMUM_WAGE_YEAR,
            calculation=(
                f"시급 {wage:,}원 < 최저임금 {MINIMUM_WAGE_2026:,}원 "
                f"(시간당 {diff:,}원 차이)"
            ),
        )

    return CheckResult(
        code="MINIMUM_WAGE",
        label="최저임금",
        status=CheckStatus.OK,
        legal_basis=legal_basis,
        standard_year=MINIMUM_WAGE_YEAR,
        calculation=f"시급 {wage:,}원 ≥ 최저임금 {MINIMUM_WAGE_2026:,}원",
    )


def check_weekly_holiday(terms: ContractTerms) -> CheckResult:
    legal_basis = "근로기준법 제18조제3항 · 제55조"

    if _is_missing(terms.weekly_holiday_day):
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴일",
            status=CheckStatus.MISSING,
            legal_basis="근로기준법 제17조 · 표준근로계약서 5번 항목",
            standard_year=2026,
            detail="주휴일(매주 ○요일)이 계약서에 명시되지 않았습니다.",
        )

    weekly_hours = terms.weekly_hours
    if weekly_hours is None:
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴일",
            status=CheckStatus.UNKNOWN,
            legal_basis=legal_basis,
            standard_year=2026,
            detail="주 소정근로시간을 계산할 정보가 부족해 시간 요건을 판정할 수 없습니다.",
        )

    meets_hours = weekly_hours >= WEEKLY_HOLIDAY_MIN_HOURS
    result_word = "충족" if meets_hours else "미충족"
    detail = (
        "계약상 주 소정근로시간이 시간 요건을 충족합니다. 실제 주휴수당 지급은 "
        "소정근로일 개근 여부 등 계약서만으로 확인되지 않는 사실관계에 따라 "
        "달라질 수 있습니다."
        if meets_hours
        else "주 소정근로시간이 15시간 미만이면 근로기준법 제55조(주휴일)가 "
        "적용되지 않습니다."
    )
    return CheckResult(
        code="WEEKLY_HOLIDAY",
        label="주휴일",
        status=CheckStatus.OK,
        legal_basis=legal_basis,
        standard_year=2026,
        calculation=(
            f"주 소정근로시간 {weekly_hours:g}시간 → 시간 요건 {result_word} "
            f"(기준 {WEEKLY_HOLIDAY_MIN_HOURS}시간)"
        ),
        detail=detail,
    )


def check_break_time(terms: ContractTerms) -> CheckResult:
    hours = terms.hours_per_day
    break_minutes = terms.break_minutes
    legal_basis = "근로기준법 제54조"

    if hours is None or break_minutes is None:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=legal_basis,
            standard_year=2026,
            detail="시업·종업·휴게 시각 중 일부가 없어 판정할 수 없습니다.",
        )

    required = _required_break_minutes(hours)
    if required == 0:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.OK,
            legal_basis=legal_basis,
            standard_year=2026,
            calculation=(
                f"근로시간 {hours:g}시간 → 법정 의무 휴게시간 없음 "
                f"(실제 {break_minutes}분)"
            ),
        )

    if break_minutes < required:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.VIOLATION,
            legal_basis=legal_basis,
            standard_year=2026,
            calculation=(
                f"근로시간 {hours:g}시간 → 최소 휴게 {required}분 필요, "
                f"실제 {break_minutes}분"
            ),
        )

    return CheckResult(
        code="BREAK_TIME",
        label="휴게시간",
        status=CheckStatus.OK,
        legal_basis=legal_basis,
        standard_year=2026,
        calculation=(
            f"근로시간 {hours:g}시간, 휴게 {break_minutes}분 ≥ 최소 {required}분"
        ),
    )


def check_required_fields(terms: ContractTerms) -> list[CheckResult]:
    """weekly_holiday_day를 제외한 필수 기재사항 누락 여부."""
    results = []
    for field_name, label in _REQUIRED_FIELD_LABELS.items():
        field: ExtractedField = getattr(terms, field_name)
        if _is_missing(field):
            results.append(
                CheckResult(
                    code=f"MISSING_{field_name.upper()}",
                    label=f"{label} 누락",
                    status=CheckStatus.MISSING,
                    legal_basis="근로기준법 제17조 · 근로계약 체결 시 서면 명시 의무",
                    standard_year=2026,
                    detail=f"{label} 항목이 계약서에서 확인되지 않았습니다.",
                )
            )
    return results


def validate(terms: ContractTerms) -> ValidationReport:
    checks = [
        check_minimum_wage(terms),
        check_weekly_holiday(terms),
        check_break_time(terms),
        *check_required_fields(terms),
    ]

    estimated_monthly_pay = None
    wage_shortfall = None
    wage = terms.hourly_wage
    weekly_hours = terms.weekly_hours
    if wage is not None and weekly_hours is not None:
        monthly_hours = weekly_hours * AVG_WEEKS_PER_MONTH
        estimated_monthly_pay = round(wage * monthly_hours)
        if wage < MINIMUM_WAGE_2026:
            wage_shortfall = round((MINIMUM_WAGE_2026 - wage) * monthly_hours)

    return ValidationReport(
        checks=checks,
        estimated_monthly_pay=estimated_monthly_pay,
        wage_shortfall=wage_shortfall,
    )
