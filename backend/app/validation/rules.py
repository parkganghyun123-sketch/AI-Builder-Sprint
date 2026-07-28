"""근로계약 조건을 검증하는 결정론적 순수 함수.

이 모듈에서는 LLM, 네트워크, 데이터베이스를 호출하지 않는다.
"""

from collections.abc import Iterable
from math import isfinite

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
    BREAK_RULES,
    BREAK_SOURCE_ID,
    MINIMUM_WAGE_2026,
    MINIMUM_WAGE_SOURCE_ID,
    STANDARD_YEAR,
    WEEKLY_HOLIDAY_MIN_HOURS,
    WEEKLY_HOLIDAY_SOURCE_ID,
)

MINIMUM_WAGE_BASIS = (
    f"최저임금법 · 2026년 적용 최저임금 고시 ({MINIMUM_WAGE_SOURCE_ID})"
)
WEEKLY_HOLIDAY_BASIS = (
    f"근로기준법 제18조제3항·제55조 ({WEEKLY_HOLIDAY_SOURCE_ID})"
)
BREAK_TIME_BASIS = f"근로기준법 제54조 ({BREAK_SOURCE_ID})"
REQUIRED_FIELDS_BASIS = (
    "근로기준법 제17조·고용노동부 표준근로계약서 "
    "(SRC-LSA-17, SRC-MOEL-CONTRACT-FORMS)"
)


def _is_missing(field: ExtractedField) -> bool:
    """추출 실패, 빈 문자열, 값 없음은 모두 확인 불가로 본다."""

    if field.confidence == Confidence.NOT_FOUND or field.value is None:
        return True
    return isinstance(field.value, str) and not field.value.strip()


def _minimum_break_minutes(hours_per_day: float) -> int:
    for minimum_hours, minimum_minutes in BREAK_RULES:
        if hours_per_day >= minimum_hours:
            return minimum_minutes
    return 0


def _safe_hours_per_day(terms: ContractTerms) -> float | None:
    if _is_missing(terms.work_start_time) or _is_missing(terms.work_end_time):
        return None
    hours = terms.hours_per_day
    if hours is None or not isfinite(hours) or hours <= 0:
        return None
    return hours


def _safe_weekly_hours(terms: ContractTerms) -> float | None:
    if _is_missing(terms.work_days_per_week):
        return None
    hours_per_day = _safe_hours_per_day(terms)
    if hours_per_day is None:
        return None
    try:
        weekly_hours = float(terms.work_days_per_week.value) * hours_per_day
    except (TypeError, ValueError):
        return None
    if not isfinite(weekly_hours) or weekly_hours <= 0:
        return None
    return weekly_hours


def check_minimum_wage(terms: ContractTerms) -> CheckResult:
    """시간급으로 확인된 계약만 2026년 최저임금과 비교한다."""

    if _is_missing(terms.wage_type) or _is_missing(terms.wage_amount):
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.UNKNOWN,
            legal_basis=MINIMUM_WAGE_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="시간급 정보 없음 — 최저임금 비교 불가",
            detail="시간급 또는 임금 금액을 확인할 수 없습니다.",
        )

    hourly_wage = terms.hourly_wage
    if hourly_wage is None:
        wage_type = terms.wage_type.value
        if wage_type in (WageType.DAILY.value, WageType.MONTHLY.value):
            reason = "월급·일급 계약은 MVP에서 시간급으로 환산하지 않습니다."
        else:
            reason = "시간급 또는 임금 금액을 확인할 수 없습니다."
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.UNKNOWN,
            legal_basis=MINIMUM_WAGE_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="시간급 정보 없음 — 최저임금 비교 불가",
            detail=f"시간급으로 기재된 계약만 판정합니다. {reason}",
        )

    if hourly_wage < MINIMUM_WAGE_2026:
        return CheckResult(
            code="MINIMUM_WAGE",
            label="최저임금",
            status=CheckStatus.VIOLATION,
            legal_basis=MINIMUM_WAGE_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"시급 {hourly_wage:,}원 < "
                f"2026년 최저임금 {MINIMUM_WAGE_2026:,}원"
            ),
            detail=(
                "확인된 시간급이 2026년 적용 최저임금보다 낮습니다. "
                "이 결과는 확인된 계약서 기재값을 기준으로 한 비교입니다."
            ),
        )

    return CheckResult(
        code="MINIMUM_WAGE",
        label="최저임금",
        status=CheckStatus.OK,
        legal_basis=MINIMUM_WAGE_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=(
            f"시급 {hourly_wage:,}원 ≥ "
            f"2026년 최저임금 {MINIMUM_WAGE_2026:,}원"
        ),
        detail="확인된 시간급이 2026년 적용 최저임금 이상입니다.",
    )


def check_weekly_holiday(terms: ContractTerms) -> CheckResult:
    """주휴 관련 시간 요건과 계약서의 주휴일 지정 여부만 확인한다."""

    weekly_hours = _safe_weekly_hours(terms)
    if weekly_hours is None:
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴 시간 요건",
            status=CheckStatus.UNKNOWN,
            legal_basis=WEEKLY_HOLIDAY_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="주 소정근로시간 정보 없음 — 시간 요건 비교 불가",
            detail=(
                "근무 시각 또는 주 근무일 수를 확인할 수 없습니다. "
                "주휴수당 지급 여부를 판정한 결과가 아닙니다."
            ),
        )

    calculation = (
        f"주 소정근로시간 {weekly_hours:g}시간 "
        f"{'≥' if weekly_hours >= WEEKLY_HOLIDAY_MIN_HOURS else '<'} "
        f"{WEEKLY_HOLIDAY_MIN_HOURS:g}시간"
    )

    if weekly_hours < WEEKLY_HOLIDAY_MIN_HOURS:
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴 시간 요건",
            status=CheckStatus.OK,
            legal_basis=WEEKLY_HOLIDAY_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=calculation,
            detail=(
                "계약상 4주 평균 주 소정근로시간이 15시간 미만으로, "
                "주휴 관련 시간 요건을 충족하지 않습니다."
            ),
        )

    if _is_missing(terms.weekly_holiday_day):
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴 시간 요건·주휴일",
            status=CheckStatus.MISSING,
            legal_basis=WEEKLY_HOLIDAY_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=calculation,
            detail=(
                "주휴 관련 시간 요건은 충족하지만 계약서에서 주휴일 요일을 "
                "확인하지 못했습니다. 실제 지급은 소정근로일 개근 등 "
                "계약서만으로 확인되지 않는 사실관계에 따라 달라질 수 있습니다."
            ),
        )

    return CheckResult(
        code="WEEKLY_HOLIDAY",
        label="주휴 시간 요건·주휴일",
        status=CheckStatus.OK,
        legal_basis=WEEKLY_HOLIDAY_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=calculation,
        detail=(
            f"계약서에 주휴일이 {terms.weekly_holiday_day.value}(으)로 기재되어 있고, "
            "주휴 관련 시간 요건을 충족합니다. 실제 지급은 소정근로일 개근 등 "
            "계약서만으로 확인되지 않는 사실관계에 따라 달라질 수 있습니다."
        ),
    )


def check_break_time(terms: ContractTerms) -> CheckResult:
    """확인된 1일 소정근로시간에 필요한 최소 휴게시간을 비교한다."""

    hours_per_day = _safe_hours_per_day(terms)
    if hours_per_day is None:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=BREAK_TIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="1일 소정근로시간 정보 없음 — 휴게시간 비교 불가",
            detail="시업·종업 시각을 확인할 수 없습니다.",
        )

    required_minutes = _minimum_break_minutes(hours_per_day)
    if required_minutes == 0:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.OK,
            legal_basis=BREAK_TIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"1일 소정근로시간 {hours_per_day:g}시간 < 4시간 — "
                "법정 최소 휴게시간 비교 대상 아님"
            ),
            detail="계약서에 기재된 시각을 기준으로 계산했습니다.",
        )

    if _is_missing(terms.break_start_time) or _is_missing(terms.break_end_time):
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=BREAK_TIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"1일 소정근로시간 {hours_per_day:g}시간 → "
                f"최소 휴게 {required_minutes}분 필요"
            ),
            detail="휴게 시작 또는 종료 시각을 확인할 수 없습니다.",
        )

    break_minutes = terms.break_minutes
    if break_minutes is None:
        return CheckResult(
            code="BREAK_TIME",
            label="휴게시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=BREAK_TIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"1일 소정근로시간 {hours_per_day:g}시간 → "
                f"최소 휴게 {required_minutes}분 필요"
            ),
            detail="휴게 시각 형식을 해석할 수 없습니다.",
        )

    operator = "≥" if break_minutes >= required_minutes else "<"
    status = (
        CheckStatus.OK
        if break_minutes >= required_minutes
        else CheckStatus.VIOLATION
    )
    return CheckResult(
        code="BREAK_TIME",
        label="휴게시간",
        status=status,
        legal_basis=BREAK_TIME_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=(
            f"1일 소정근로시간 {hours_per_day:g}시간: "
            f"휴게 {break_minutes}분 {operator} 최소 {required_minutes}분"
        ),
        detail=(
            "계약서에 기재된 휴게시간이 법정 최소 기준 이상입니다."
            if status == CheckStatus.OK
            else "계약서에 기재된 휴게시간이 법정 최소 기준보다 짧습니다."
        ),
    )


def _required_group_result(
    *,
    code: str,
    label: str,
    fields: Iterable[ExtractedField],
) -> CheckResult:
    missing = any(_is_missing(field) for field in fields)
    return CheckResult(
        code=code,
        label=label,
        status=CheckStatus.MISSING if missing else CheckStatus.OK,
        legal_basis=REQUIRED_FIELDS_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=(
            f"{label}: 확인된 입력에서 찾지 못함"
            if missing
            else f"{label}: 확인됨"
        ),
        detail=(
            "확인된 입력에서 해당 항목을 찾지 못했습니다. "
            "원본 계약서와 표준근로계약서를 함께 확인해 주세요."
            if missing
            else "확인된 계약 내용에 해당 항목이 있습니다."
        ),
    )


def check_required_fields(terms: ContractTerms) -> list[CheckResult]:
    """현재 스키마로 안전하게 확인할 수 있는 주요 기재항목을 점검한다.

    주휴일은 시간 요건과 함께 ``check_weekly_holiday``에서, 휴게시간은
    ``check_break_time``에서 점검해 중복 결과를 만들지 않는다.
    """

    groups = (
        ("REQUIRED_CONTRACT_START", "근로계약 시작일", (terms.contract_start,)),
        ("REQUIRED_WORKPLACE", "근무장소", (terms.workplace,)),
        ("REQUIRED_JOB", "업무의 내용", (terms.job_description,)),
        (
            "REQUIRED_WORKING_HOURS",
            "소정근로시간",
            (terms.work_start_time, terms.work_end_time),
        ),
        (
            "REQUIRED_WORK_DAYS",
            "주 근무일 수",
            (terms.work_days_per_week,),
        ),
        (
            "REQUIRED_WAGE",
            "임금",
            (terms.wage_type, terms.wage_amount),
        ),
        ("REQUIRED_PAYDAY", "임금지급일", (terms.payday,)),
        (
            "REQUIRED_PAYMENT_METHOD",
            "임금지급방법",
            (terms.payment_method,),
        ),
        (
            "REQUIRED_PARTIES",
            "계약 당사자",
            (
                terms.employer_business_name,
                terms.employer_name,
                terms.worker_name,
            ),
        ),
    )
    return [
        _required_group_result(code=code, label=label, fields=fields)
        for code, label, fields in groups
    ]


def validate(terms: ContractTerms) -> ValidationReport:
    """모든 지원 규칙을 실행해 하나의 검증 보고서를 반환한다."""

    checks = [
        check_minimum_wage(terms),
        check_weekly_holiday(terms),
        check_break_time(terms),
        *check_required_fields(terms),
    ]
    return ValidationReport(
        checks=checks,
        # 월 환산에는 유급주휴 등 추가 사실이 필요하므로 MVP에서 추정하지 않는다.
        estimated_monthly_pay=None,
        wage_shortfall=None,
    )
