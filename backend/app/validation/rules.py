"""근로계약 조건을 검증하는 결정론적 순수 함수.

이 모듈에서는 LLM, 네트워크, 데이터베이스를 호출하지 않는다.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
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
    ANNUAL_LEAVE_SOURCE_IDS,
    BREAK_RULES,
    BREAK_SOURCE_ID,
    DISMISSAL_NOTICE_MIN_MONTHS,
    DISMISSAL_NOTICE_SOURCE_ID,
    MINIMUM_WAGE_2026,
    MINIMUM_WAGE_SOURCE_ID,
    MINOR_AGE_LIMIT,
    MINOR_DAILY_HOURS,
    MINOR_EXT_DAILY_HOURS,
    MINOR_EXT_WEEKLY_HOURS,
    MINOR_NIGHT_END,
    MINOR_NIGHT_SOURCE_ID,
    MINOR_NIGHT_START,
    MINOR_SOURCE_ID,
    MINOR_WEEKLY_HOURS,
    PROBATION_MINIMUM_WAGE_2026,
    PROBATION_SOURCE_IDS,
    SEVERANCE_CONTINUOUS_YEARS,
    SEVERANCE_MIN_WEEKLY_HOURS,
    SEVERANCE_SOURCE_IDS,
    SOCIAL_INSURANCE_SOURCE_IDS,
    SOCIAL_INSURANCE_WEEKLY_HOURS,
    STANDARD_YEAR,
    WEEKLY_HOLIDAY_MIN_HOURS,
    WEEKLY_HOLIDAY_SOURCE_ID,
)

MINIMUM_WAGE_BASIS = (
    f"최저임금법 · 2026년 적용 최저임금 고시 ({MINIMUM_WAGE_SOURCE_ID})"
)
WEEKLY_HOLIDAY_BASIS = f"근로기준법 제18조제3항·제55조 ({WEEKLY_HOLIDAY_SOURCE_ID})"
BREAK_TIME_BASIS = f"근로기준법 제54조 ({BREAK_SOURCE_ID})"
MINOR_WORKING_HOURS_BASIS = f"근로기준법 제69조·2026-07-29 확인 ({MINOR_SOURCE_ID})"
MINOR_NIGHT_WORK_BASIS = f"근로기준법 제70조·2026-07-29 확인 ({MINOR_NIGHT_SOURCE_ID})"
REQUIRED_FIELDS_BASIS = (
    "근로기준법 제17조·고용노동부 표준근로계약서 (SRC-LSA-17, SRC-MOEL-CONTRACT-FORMS)"
)
SEVERANCE_PAY_BASIS = (
    "근로자퇴직급여 보장법 제4조·제8조 및 고용노동부 2025 상담 "
    f"({', '.join(SEVERANCE_SOURCE_IDS)})"
)


@dataclass(frozen=True)
class SeveranceEligibility:
    """계약에서 확인 가능한 퇴직급여 관련 두 조건의 결정론적 결과."""

    planned_one_year: bool | None
    weekly_hours_15: bool | None
    period_calculation: str
    weekly_hours_calculation: str
    legal_basis: str = SEVERANCE_PAY_BASIS


@dataclass(frozen=True)
class DurationIndicator:
    planned_three_months: bool | None
    calculation: str
    legal_basis: str = f"근로기준법 제26조 ({DISMISSAL_NOTICE_SOURCE_ID})"


@dataclass(frozen=True)
class ProbationWageIndicators:
    planned_one_year: bool | None
    hourly_wage: int | None
    meets_regular_minimum: bool | None
    meets_discounted_floor: bool | None
    period_calculation: str
    wage_calculation: str
    legal_basis: str = (
        f"최저임금법 제5조·2026년 최저임금 ({', '.join(PROBATION_SOURCE_IDS)})"
    )


@dataclass(frozen=True)
class SocialInsuranceIndicators:
    weekly_hours_15: bool | None
    weekly_hours_calculation: str
    legal_basis: str = (
        f"4대보험별 적용·제외 기준 ({', '.join(SOCIAL_INSURANCE_SOURCE_IDS)})"
    )


@dataclass(frozen=True)
class AnnualLeaveIndicators:
    planned_one_year: bool | None
    weekly_hours_15: bool | None
    period_calculation: str
    weekly_hours_calculation: str
    legal_basis: str = (
        f"근로기준법 제60조·제11조·제18조 ({', '.join(ANNUAL_LEAVE_SOURCE_IDS)})"
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


def _one_year_anniversary(start: date) -> date:
    """시작일을 포함한 1년 기간 직후 날짜를 반환한다."""

    try:
        return start.replace(year=start.year + SEVERANCE_CONTINUOUS_YEARS)
    except ValueError:
        # 2월 29일부터 시작한 1년 기간은 다음 해 2월 28일까지로 본다.
        return date(start.year + SEVERANCE_CONTINUOUS_YEARS, 3, 1)


def check_severance_pay(terms: ContractTerms) -> SeveranceEligibility:
    """계약상 예정 기간 1년과 주 소정근로시간 15시간 조건만 확인한다.

    실제 입·퇴사일, 계속근로, 기간 중 시간 변경, 실제 퇴직 여부는 계약서로
    확인하지 않으며 퇴직급여 금액도 계산하지 않는다.
    """

    planned_one_year: bool | None = None
    period_calculation = "계약 시작일 또는 종료일 정보 부족 → 예정 기간 비교 불가"
    if not _is_missing(terms.contract_start) and not _is_missing(terms.contract_end):
        try:
            start = date.fromisoformat(str(terms.contract_start.value).strip())
            end = date.fromisoformat(str(terms.contract_end.value).strip())
        except (TypeError, ValueError):
            period_calculation = (
                "계약 시작일 또는 종료일 형식 확인 필요 → 예정 기간 비교 불가"
            )
        else:
            if end >= start:
                # 시작일과 종료일을 모두 포함한 예정 계약기간을 비교한다.
                one_year_end = _one_year_anniversary(start) - timedelta(days=1)
                planned_one_year = end >= one_year_end
                operator = "≥" if planned_one_year else "<"
                period_calculation = (
                    f"계약상 {start.isoformat()}~{end.isoformat()} {operator} "
                    f"1년 예정 기준 종료일 {one_year_end.isoformat()}"
                )
            else:
                period_calculation = (
                    "계약 종료일이 시작일보다 이름 → 예정 기간 비교 불가"
                )

    weekly_hours = _safe_weekly_hours(terms)
    if weekly_hours is None:
        weekly_hours_15 = None
        weekly_hours_calculation = "주 소정근로시간 정보 부족 → 15시간 기준 비교 불가"
    else:
        weekly_hours_15 = weekly_hours >= SEVERANCE_MIN_WEEKLY_HOURS
        operator = "≥" if weekly_hours_15 else "<"
        weekly_hours_calculation = (
            "4주 평균 기준(현재 계약상 주간 일정으로 비교): "
            f"주 소정근로시간 {weekly_hours:g}시간 {operator} "
            f"{SEVERANCE_MIN_WEEKLY_HOURS:g}시간"
        )

    return SeveranceEligibility(
        planned_one_year=planned_one_year,
        weekly_hours_15=weekly_hours_15,
        period_calculation=period_calculation,
        weekly_hours_calculation=weekly_hours_calculation,
    )


def check_annual_leave_indicators(terms: ContractTerms) -> AnnualLeaveIndicators:
    """연차 답변에 쓰는 계약상 예정기간·주 15시간 지표만 반환한다."""

    base = check_severance_pay(terms)
    return AnnualLeaveIndicators(
        planned_one_year=base.planned_one_year,
        weekly_hours_15=base.weekly_hours_15,
        period_calculation=base.period_calculation,
        weekly_hours_calculation=base.weekly_hours_calculation,
    )


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_end = (
        date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        - timedelta(days=1)
    ).day
    return date(year, month, min(value.day, month_end))


def check_dismissal_notice_indicator(terms: ContractTerms) -> DurationIndicator:
    """계약상 예정기간이 3개월 이상인지 여부만 확인한다."""

    if _is_missing(terms.contract_start) or _is_missing(terms.contract_end):
        return DurationIndicator(
            None, "계약 시작일 또는 종료일 정보 부족 → 3개월 비교 불가"
        )
    try:
        start = date.fromisoformat(str(terms.contract_start.value).strip())
        end = date.fromisoformat(str(terms.contract_end.value).strip())
    except (TypeError, ValueError):
        return DurationIndicator(None, "계약 날짜 형식 확인 필요 → 3개월 비교 불가")
    if end < start:
        return DurationIndicator(
            None, "계약 종료일이 시작일보다 이름 → 3개월 비교 불가"
        )
    threshold_end = _add_months(start, DISMISSAL_NOTICE_MIN_MONTHS) - timedelta(days=1)
    result = end >= threshold_end
    operator = "≥" if result else "<"
    return DurationIndicator(
        result,
        f"계약상 {start.isoformat()}~{end.isoformat()} {operator} "
        f"3개월 예정 기준 종료일 {threshold_end.isoformat()}",
    )


def check_probation_minimum_wage(terms: ContractTerms) -> ProbationWageIndicators:
    """수습 감액의 계약기간 지표와 시간급 하한만 비교한다."""

    period = check_severance_pay(terms)
    hourly_wage = None
    if not _is_missing(terms.wage_type) and not _is_missing(terms.wage_amount):
        hourly_wage = terms.hourly_wage
    if hourly_wage is None:
        wage_calculation = "시간급 정보 부족 → 최저임금·수습 감액 하한 비교 불가"
        regular = discounted = None
    else:
        regular = hourly_wage >= MINIMUM_WAGE_2026
        discounted = hourly_wage >= PROBATION_MINIMUM_WAGE_2026
        wage_calculation = (
            f"계약상 시급 {hourly_wage:,}원 / 일반 최저 {MINIMUM_WAGE_2026:,}원 / "
            f"수습 감액 가능 시 최저 {PROBATION_MINIMUM_WAGE_2026:,}원"
        )
    return ProbationWageIndicators(
        planned_one_year=period.planned_one_year,
        hourly_wage=hourly_wage,
        meets_regular_minimum=regular,
        meets_discounted_floor=discounted,
        period_calculation=period.period_calculation,
        wage_calculation=wage_calculation,
    )


def check_social_insurance_indicators(
    terms: ContractTerms,
) -> SocialInsuranceIndicators:
    """보험별 결론이 아닌 계약상 주 15시간 지표만 계산한다."""

    weekly_hours = _safe_weekly_hours(terms)
    if weekly_hours is None:
        return SocialInsuranceIndicators(
            None, "주 소정근로시간 정보 부족 → 시간 지표 비교 불가"
        )
    result = weekly_hours >= SOCIAL_INSURANCE_WEEKLY_HOURS
    operator = "≥" if result else "<"
    return SocialInsuranceIndicators(
        result,
        f"현재 계약상 주 소정근로시간 {weekly_hours:g}시간 {operator} "
        f"{SOCIAL_INSURANCE_WEEKLY_HOURS:g}시간",
    )


def _minor_context(
    terms: ContractTerms,
    birth_date: str | None,
) -> tuple[date, int] | None:
    """계약 시작일 기준 만 나이가 15세 이상 18세 미만이면 기준일과 나이를 반환한다.

    시스템 현재 시각을 사용하지 않는다. 생년월일 또는 계약 시작일이 없거나 유효한
    ISO 날짜가 아니면 정확한 적용 시점을 알 수 없어 검사를 생성하지 않는다.
    """

    if (
        not isinstance(birth_date, str)
        or not birth_date.strip()
        or _is_missing(terms.contract_start)
    ):
        return None

    try:
        born = date.fromisoformat(birth_date.strip())
        contract_start = date.fromisoformat(str(terms.contract_start.value).strip())
    except (TypeError, ValueError):
        return None

    if contract_start.year != STANDARD_YEAR:
        return None

    age = (
        contract_start.year
        - born.year
        - ((contract_start.month, contract_start.day) < (born.month, born.day))
    )
    if not 15 <= age < MINOR_AGE_LIMIT:
        return None
    return contract_start, age


def _safe_time_minutes(value: str | int | None) -> int | None:
    """기존 계약 시각 형식을 범위 검증해 자정부터의 분으로 바꾼다."""

    if value is None:
        return None
    normalized = str(value).replace("시", ":").replace("분", "").replace(" ", "")
    parts = normalized.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError:
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour * 60 + minute


def _overlaps(
    start_a: int,
    end_a: int,
    start_b: int,
    end_b: int,
) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)


def _minor_work_intervals(
    terms: ContractTerms,
) -> list[tuple[int, int]] | None:
    """자정 넘김과 근무 중 휴게를 반영한 계약상 근로 구간을 반환한다.

    휴게 시각이 없거나 해석할 수 없거나 근무 구간 밖이면 근로시간을 과소 계산하지
    않도록 해당 휴게를 빼지 않는다.
    """

    if _is_missing(terms.work_start_time) or _is_missing(terms.work_end_time):
        return None

    shift_start = _safe_time_minutes(terms.work_start_time.value)
    shift_end = _safe_time_minutes(terms.work_end_time.value)
    if shift_start is None or shift_end is None or shift_start == shift_end:
        return None
    if shift_end < shift_start:
        shift_end += 24 * 60

    full_shift = [(shift_start, shift_end)]
    if _is_missing(terms.break_start_time) or _is_missing(terms.break_end_time):
        return full_shift

    break_start = _safe_time_minutes(terms.break_start_time.value)
    break_end = _safe_time_minutes(terms.break_end_time.value)
    if break_start is None or break_end is None or break_start == break_end:
        return full_shift

    while break_start < shift_start:
        break_start += 24 * 60
    while break_end <= break_start:
        break_end += 24 * 60

    if not shift_start <= break_start < break_end <= shift_end:
        return full_shift

    return [
        interval
        for interval in (
            (shift_start, break_start),
            (break_end, shift_end),
        )
        if interval[0] < interval[1]
    ]


def _safe_minor_hours_per_day(terms: ContractTerms) -> float | None:
    intervals = _minor_work_intervals(terms)
    if intervals is None:
        return None
    hours = sum(end - start for start, end in intervals) / 60
    if not isfinite(hours) or hours < 0:
        return None
    return hours


def _safe_minor_weekly_hours(
    terms: ContractTerms,
    hours_per_day: float,
) -> float | None:
    if _is_missing(terms.work_days_per_week):
        return None
    try:
        work_days = float(terms.work_days_per_week.value)
        weekly_hours = work_days * hours_per_day
    except (TypeError, ValueError):
        return None
    if not isfinite(work_days) or work_days <= 0:
        return None
    if not isfinite(weekly_hours) or weekly_hours < 0:
        return None
    return weekly_hours


def _minor_age_limit_note(contract_start: date) -> str:
    return (
        f"만 나이는 계약 시작일 {contract_start.isoformat()} 기준입니다. "
        "계약기간 중 만 18세 도달에 따른 시점별 변화는 반영하지 않았습니다."
    )


def check_minor_working_hours(
    terms: ContractTerms,
    birth_date: str | None,
) -> CheckResult | None:
    """15세 이상 18세 미만자의 계약상 1일·1주 근로시간을 비교한다."""

    context = _minor_context(terms, birth_date)
    if context is None:
        return None
    contract_start, age = context
    context_text = f"계약 시작일 {contract_start.isoformat()} 기준 만 {age}세"

    hours_per_day = _safe_minor_hours_per_day(terms)
    if hours_per_day is None:
        return CheckResult(
            code="MINOR_WORKING_HOURS",
            label="18세 미만 근로시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=MINOR_WORKING_HOURS_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=f"{context_text} · 1일 소정근로시간 정보 없음",
            detail=(
                "시업·종업 시각을 확인할 수 없어 근로시간 기준과 비교하지 못했습니다. "
                f"{_minor_age_limit_note(contract_start)}"
            ),
        )

    weekly_hours = _safe_minor_weekly_hours(terms, hours_per_day)
    daily_over = hours_per_day > MINOR_DAILY_HOURS
    weekly_over = weekly_hours is not None and weekly_hours > MINOR_WEEKLY_HOURS
    daily_extended_limit = MINOR_DAILY_HOURS + MINOR_EXT_DAILY_HOURS
    weekly_extended_limit = MINOR_WEEKLY_HOURS + MINOR_EXT_WEEKLY_HOURS

    calculation_parts = [
        context_text,
        (
            f"1일 {hours_per_day:g}시간 "
            f"{'>' if daily_over else '≤'} 기본 {MINOR_DAILY_HOURS:g}시간"
        ),
    ]
    if weekly_hours is not None:
        calculation_parts.append(
            f"1주 {weekly_hours:g}시간 "
            f"{'>' if weekly_over else '≤'} 기본 {MINOR_WEEKLY_HOURS:g}시간"
        )

    if daily_over or weekly_over:
        exceeds_extended_limit = hours_per_day > daily_extended_limit or (
            weekly_hours is not None and weekly_hours > weekly_extended_limit
        )
        if exceeds_extended_limit:
            detail = (
                "확인된 근로시간이 기본 기준과 당사자 합의가 있을 때의 연장 한도"
                f"(1일 총 {daily_extended_limit:g}시간, "
                f"1주 총 {weekly_extended_limit:g}시간)도 초과합니다. "
                "확인된 계약상 시간만 비교한 결과이며, "
                f"{_minor_age_limit_note(contract_start)}"
            )
        else:
            detail = (
                "확인된 근로시간이 1일 7시간 또는 1주 35시간의 기본 기준을 "
                "초과합니다. 당사자 합의 여부는 입력에서 확인되지 않았습니다. "
                "합의가 있는 경우에도 1일 1시간, 1주 5시간 범위에서만 "
                "연장할 수 있어 별도 확인이 필요합니다. "
                f"{_minor_age_limit_note(contract_start)}"
            )
        return CheckResult(
            code="MINOR_WORKING_HOURS",
            label="18세 미만 근로시간",
            status=CheckStatus.VIOLATION,
            legal_basis=MINOR_WORKING_HOURS_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=" · ".join(calculation_parts),
            detail=detail,
        )

    if weekly_hours is None:
        return CheckResult(
            code="MINOR_WORKING_HOURS",
            label="18세 미만 근로시간",
            status=CheckStatus.UNKNOWN,
            legal_basis=MINOR_WORKING_HOURS_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=" · ".join([*calculation_parts, "주 근무일 수 정보 없음"]),
            detail=(
                "1일 기준은 초과하지 않지만 주 근무일 수를 확인할 수 없어 "
                "1주 기준은 비교하지 못했습니다. "
                f"{_minor_age_limit_note(contract_start)}"
            ),
        )

    return CheckResult(
        code="MINOR_WORKING_HOURS",
        label="18세 미만 근로시간",
        status=CheckStatus.OK,
        legal_basis=MINOR_WORKING_HOURS_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=" · ".join(calculation_parts),
        detail=(
            "확인된 계약상 근로시간이 1일 7시간과 1주 35시간의 기본 기준을 "
            f"초과하지 않습니다. {_minor_age_limit_note(contract_start)}"
        ),
    )


def check_minor_night_work(
    terms: ContractTerms,
    birth_date: str | None,
) -> CheckResult | None:
    """15세 이상 18세 미만자의 계약 시각과 22:00~06:00 겹침을 확인한다."""

    context = _minor_context(terms, birth_date)
    if context is None:
        return None
    contract_start, age = context
    context_text = f"계약 시작일 {contract_start.isoformat()} 기준 만 {age}세"

    work_intervals = _minor_work_intervals(terms)
    if work_intervals is None:
        return CheckResult(
            code="MINOR_NIGHT_WORK",
            label="18세 미만 야간근로",
            status=CheckStatus.UNKNOWN,
            legal_basis=MINOR_NIGHT_WORK_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=f"{context_text} · 근무 시각 정보 없음",
            detail=(
                "시업·종업 시각을 해석할 수 없어 22:00~06:00 시간대와의 "
                f"겹침을 확인하지 못했습니다. {_minor_age_limit_note(contract_start)}"
            ),
        )

    night_start = _safe_time_minutes(MINOR_NIGHT_START)
    night_end = _safe_time_minutes(MINOR_NIGHT_END)
    assert night_start is not None and night_end is not None
    overlaps_night = any(
        _overlaps(start, end, 0, night_end)
        or _overlaps(start, end, night_start, 24 * 60 + night_end)
        for start, end in work_intervals
    )

    work_range = f"{terms.work_start_time.value}~{terms.work_end_time.value}"
    if overlaps_night:
        return CheckResult(
            code="MINOR_NIGHT_WORK",
            label="18세 미만 야간근로",
            status=CheckStatus.VIOLATION,
            legal_basis=MINOR_NIGHT_WORK_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"{context_text} · 근무 {work_range}(기재된 휴게시간 제외)와 "
                f"야간 {MINOR_NIGHT_START}~{MINOR_NIGHT_END} 시간대가 겹침"
            ),
            detail=(
                "확인된 계약상 근무 시각이 18세 미만자의 야간근로 제한 "
                "시간대와 겹칩니다. 18세 미만자 본인의 동의와 "
                "고용노동부장관 인가 등 예외 요건은 입력만으로 확인되지 "
                f"않았습니다. {_minor_age_limit_note(contract_start)}"
            ),
        )

    return CheckResult(
        code="MINOR_NIGHT_WORK",
        label="18세 미만 야간근로",
        status=CheckStatus.OK,
        legal_basis=MINOR_NIGHT_WORK_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=(
            f"{context_text} · 근무 {work_range}(기재된 휴게시간 제외)와 "
            f"야간 {MINOR_NIGHT_START}~{MINOR_NIGHT_END} 시간대가 겹치지 않음"
        ),
        detail=(
            "확인된 계약상 근무 시각만 비교한 결과입니다. "
            f"{_minor_age_limit_note(contract_start)}"
        ),
    )


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
                f"시급 {hourly_wage:,}원 < 2026년 최저임금 {MINIMUM_WAGE_2026:,}원"
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
            f"시급 {hourly_wage:,}원 ≥ 2026년 최저임금 {MINIMUM_WAGE_2026:,}원"
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
        CheckStatus.OK if break_minutes >= required_minutes else CheckStatus.VIOLATION
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
            f"{label}: 확인된 입력에서 찾지 못함" if missing else f"{label}: 확인됨"
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


def validate(
    terms: ContractTerms,
    worker_birth_date: str | None = None,
) -> ValidationReport:
    """모든 지원 규칙을 실행해 하나의 검증 보고서를 반환한다."""

    minor_checks = (
        check_minor_working_hours(terms, worker_birth_date),
        check_minor_night_work(terms, worker_birth_date),
    )
    checks = [
        check_minimum_wage(terms),
        check_weekly_holiday(terms),
        check_break_time(terms),
        *(check for check in minor_checks if check is not None),
        *check_required_fields(terms),
    ]
    return ValidationReport(
        checks=checks,
        # 월 환산에는 유급주휴 등 추가 사실이 필요하므로 MVP에서 추정하지 않는다.
        estimated_monthly_pay=None,
        wage_shortfall=None,
    )
