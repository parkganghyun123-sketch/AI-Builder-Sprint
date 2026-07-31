"""근로계약 조건을 검증하는 결정론적 순수 함수.

이 모듈에서는 LLM, 네트워크, 데이터베이스를 호출하지 않는다.
"""

from collections.abc import Iterable
from datetime import date
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
    DISABLED_ACCOMMODATION_SOURCE_ID,
    DISABLED_EQUAL_TREATMENT_SOURCE_ID,
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
    POSTPARTUM_DAILY_OVERTIME_LIMIT,
    POSTPARTUM_OVERTIME_SOURCE_ID,
    POSTPARTUM_WEEKLY_OVERTIME_LIMIT,
    PREGNANT_NIGHT_END,
    PREGNANT_NIGHT_SOURCE_ID,
    PREGNANT_NIGHT_START,
    PREGNANT_OVERTIME_SOURCE_ID,
    PREGNANT_SHORTENED_DAILY_HOURS,
    PREGNANT_SHORTENED_EARLY_WEEK_MAX,
    PREGNANT_SHORTENED_LATE_WEEK_MIN,
    PREGNANT_SHORTENED_SOURCE_ID,
    PREGNANT_STATUTORY_WEEKLY_HOURS,
    STANDARD_YEAR,
    STATUTORY_DAILY_HOURS,
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
PREGNANT_OVERTIME_BASIS = (
    f"근로기준법 제74조제5항·2026-07-31 확인 ({PREGNANT_OVERTIME_SOURCE_ID})"
)
PREGNANT_SHORTENED_HOURS_BASIS = (
    f"근로기준법 제74조제7항·제8항·2026-07-31 확인 ({PREGNANT_SHORTENED_SOURCE_ID})"
)
PREGNANT_NIGHT_WORK_BASIS = (
    f"근로기준법 제70조제2항·2026-07-31 확인 ({PREGNANT_NIGHT_SOURCE_ID})"
)
POSTPARTUM_OVERTIME_BASIS = (
    f"근로기준법 제71조·2026-07-31 확인 ({POSTPARTUM_OVERTIME_SOURCE_ID})"
)
DISABLED_ACCOMMODATION_BASIS = (
    f"근로기준법 제6조·장애인차별금지법 제11조·2026-07-31 확인 "
    f"({DISABLED_EQUAL_TREATMENT_SOURCE_ID}, {DISABLED_ACCOMMODATION_SOURCE_ID})"
)
REQUIRED_FIELDS_BASIS = (
    "근로기준법 제17조·고용노동부 표준근로계약서 (SRC-LSA-17, SRC-MOEL-CONTRACT-FORMS)"
)


def _is_missing(field: ExtractedField) -> bool:
    """추출 실패, 빈 문자열, 값 없음은 모두 확인 불가로 본다."""

    if field.confidence == Confidence.NOT_FOUND or field.value is None:
        return True
    return isinstance(field.value, str) and not field.value.strip()


def _is_unreliable(field: ExtractedField) -> bool:
    """
    이 값 하나로 '문제 없음'이라고 말해도 되는가?

    ⚠️ 실측에서 드러난 위험:
       계약서의 주휴일 칸이 '주휴일 매주 ( ) 요일' 로 비어 있는데
       모델이 요일을 지어낸 적이 있다. confidence 는 LOW 였지만
       값이 있다는 이유로 검증이 "주휴일 기재됨 = OK" 로 판정해
       실제 위반이 가려졌다.

       같은 사진을 두 번 넣었을 때 한 번은 문제 1건, 한 번은 2건이 나왔다.

    그래서 원칙을 둔다:
       **AI가 자신 없어 하는 값으로는 '문제 없음'이라고 말하지 않는다.**

    누락(MISSING) 판정에는 이 함수를 쓰지 않는다.
    값이 없다고 보수적으로 경고하는 건 안전한 방향이기 때문이다.
    위험한 건 반대 방향 — 불확실한 값으로 안심시키는 것이다.
    """
    return _is_missing(field) or field.confidence == Confidence.LOW


def _hours(value: float) -> str:
    """
    근로시간을 사람이 읽는 형태로 만든다. 5.833333… → '5시간 50분'

    ⚠️ 계산식(``CheckResult.calculation``)은 화면에만 쓰이는 게 아니다.
       app/bridge/templates.py 가 이 문자열에서 숫자를 꺼내
       **사용자가 사장님에게 보낼 문구**를 만든다.

       예전에는 ``f"{hours:g}"`` 를 썼고, 09:00~15:00 에 휴게 10분이면
       "1일 소정근로시간 5.83333시간" 이 그대로 사장님에게 갈 문장에 들어갔다.
       열여섯 살이 보낼 메시지에 부동소수점이 새어 나오면 안 된다.

       분 단위로 끊어 쓰면 계약서 기재 방식(시각)과도 자연스럽게 이어진다.
    """
    total_minutes = round(value * 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        # "0시간 6분" 이 아니라 "6분". 15시간에서 얼마나 모자란지
        # 알려줄 때 한 시간이 안 되는 경우가 자주 나온다.
        return f"{minutes}분"
    if minutes == 0:
        return f"{hours}시간"
    return f"{hours}시간 {minutes}분"


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
            f"1일 {_hours(hours_per_day)} "
            f"{'>' if daily_over else '≤'} 기본 {MINOR_DAILY_HOURS:g}시간"
        ),
    ]
    if weekly_hours is not None:
        calculation_parts.append(
            f"1주 {_hours(weekly_hours)} "
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


def check_pregnant_overtime(
    terms: ContractTerms,
    is_pregnant: bool,
) -> CheckResult | None:
    """임신 중인 근로자의 계약상 소정근로시간이 법정근로시간(주 40시간)을 넘는지 확인한다."""

    if not is_pregnant:
        return None

    weekly_hours = _safe_weekly_hours(terms)
    if weekly_hours is None:
        return CheckResult(
            code="PREGNANT_OVERTIME",
            label="임신중 시간외근로 금지",
            status=CheckStatus.UNKNOWN,
            legal_basis=PREGNANT_OVERTIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="주 소정근로시간 정보 없음",
            detail="근무 시각 또는 주 근무일 수를 확인할 수 없어 비교하지 못했습니다.",
        )

    operator = ">" if weekly_hours > PREGNANT_STATUTORY_WEEKLY_HOURS else "≤"
    calculation = (
        f"주 소정근로시간 {_hours(weekly_hours)} {operator} "
        f"법정근로시간 {PREGNANT_STATUTORY_WEEKLY_HOURS:g}시간"
    )

    if weekly_hours > PREGNANT_STATUTORY_WEEKLY_HOURS:
        return CheckResult(
            code="PREGNANT_OVERTIME",
            label="임신중 시간외근로 금지",
            status=CheckStatus.VIOLATION,
            legal_basis=PREGNANT_OVERTIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=calculation,
            detail=(
                "임신 중인 근로자에게는 법정근로시간(주 40시간)을 초과하는 시간외근로를 "
                "시킬 수 없습니다. 당사자 합의로도 예외가 인정되지 않으며, 근로자가 "
                "요구하면 쉬운 종류의 근로로 전환해야 합니다."
            ),
        )

    return CheckResult(
        code="PREGNANT_OVERTIME",
        label="임신중 시간외근로 금지",
        status=CheckStatus.OK,
        legal_basis=PREGNANT_OVERTIME_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=calculation,
        detail="확인된 계약상 소정근로시간이 법정근로시간 이내입니다.",
    )


def check_postpartum_overtime_limit(
    terms: ContractTerms,
    is_postpartum_within_year: bool,
    is_pregnant: bool,
) -> CheckResult | None:
    """산후 1년 이내 근로자의 시간외근로 상한(1일 2시간·1주 6시간)을 확인한다.

    ⚠️ 임신 중과는 다른 규정이다(constants.py 주석 참고). 임신 중이면 제74조제5항의
    전면 금지가 적용되므로 이 검사 대상이 아니다.

    1년 150시간 상한은 계약기간 전체의 실제 근로를 알아야 판정할 수 있어
    계약 조건만으로는 확인하지 않는다.
    """

    if not is_postpartum_within_year or is_pregnant:
        return None

    hours_per_day = _safe_hours_per_day(terms)
    weekly_hours = _safe_weekly_hours(terms)
    if hours_per_day is None or weekly_hours is None:
        return CheckResult(
            code="POSTPARTUM_OVERTIME",
            label="산후 1년 이내 시간외근로 상한",
            status=CheckStatus.UNKNOWN,
            legal_basis=POSTPARTUM_OVERTIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="근로시간 정보 없음",
            detail="근무 시각 또는 주 근무일 수를 확인할 수 없어 비교하지 못했습니다.",
        )

    daily_overtime = max(hours_per_day - STATUTORY_DAILY_HOURS, 0.0)
    weekly_overtime = max(weekly_hours - PREGNANT_STATUTORY_WEEKLY_HOURS, 0.0)
    daily_over = daily_overtime > POSTPARTUM_DAILY_OVERTIME_LIMIT
    weekly_over = weekly_overtime > POSTPARTUM_WEEKLY_OVERTIME_LIMIT

    calculation = (
        f"1일 시간외근로 추정 {_hours(daily_overtime)} "
        f"{'>' if daily_over else '≤'} 상한 {POSTPARTUM_DAILY_OVERTIME_LIMIT:g}시간 · "
        f"1주 시간외근로 추정 {_hours(weekly_overtime)} "
        f"{'>' if weekly_over else '≤'} 상한 {POSTPARTUM_WEEKLY_OVERTIME_LIMIT:g}시간"
    )

    if daily_over or weekly_over:
        return CheckResult(
            code="POSTPARTUM_OVERTIME",
            label="산후 1년 이내 시간외근로 상한",
            status=CheckStatus.VIOLATION,
            legal_basis=POSTPARTUM_OVERTIME_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=calculation,
            detail=(
                "산후 1년이 지나지 않은 근로자는 단체협약이 있어도 1일 2시간·1주 6시간·"
                "1년 150시간을 초과하는 시간외근로를 시킬 수 없습니다. 1일·1주 상한은 "
                "계약상 소정근로시간이 법정근로시간(1일 8시간·주 40시간)을 얼마나 넘는지로 "
                "추정한 것이며, 실제 추가 근로와 1년 누적 시간은 계약서만으로 확인되지 "
                "않습니다."
            ),
        )

    return CheckResult(
        code="POSTPARTUM_OVERTIME",
        label="산후 1년 이내 시간외근로 상한",
        status=CheckStatus.OK,
        legal_basis=POSTPARTUM_OVERTIME_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=calculation,
        detail=(
            "계약상 소정근로시간을 기준으로 추정한 결과이며, 1년 누적 시간외근로 상한"
            "(150시간)은 계약서만으로 확인되지 않습니다."
        ),
    )


def check_pregnant_shortened_hours(
    is_pregnant: bool,
    pregnancy_week: int | None,
) -> CheckResult | None:
    """임신 12주 이내·32주 이후 근로시간 단축 신청 대상인지 안내한다."""

    if not is_pregnant or pregnancy_week is None:
        return None

    eligible = (
        pregnancy_week <= PREGNANT_SHORTENED_EARLY_WEEK_MAX
        or pregnancy_week >= PREGNANT_SHORTENED_LATE_WEEK_MIN
    )
    detail = (
        (
            f"임신 {PREGNANT_SHORTENED_EARLY_WEEK_MAX}주 이내 또는 "
            f"{PREGNANT_SHORTENED_LATE_WEEK_MIN}주 이후에 해당해 "
            f"1일 {PREGNANT_SHORTENED_DAILY_HOURS}시간 단축근로를 신청할 수 있습니다. "
            "신청해도 임금은 삭감되지 않습니다."
        )
        if eligible
        else "현재 임신 주수는 근로시간 단축 신청 대상 기간이 아닙니다."
    )
    return CheckResult(
        code="PREGNANT_SHORTENED_HOURS",
        label="임신기 근로시간 단축",
        status=CheckStatus.OK,
        legal_basis=PREGNANT_SHORTENED_HOURS_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=f"임신 {pregnancy_week}주차",
        detail=detail,
    )


def check_pregnant_night_work(
    terms: ContractTerms,
    is_pregnant: bool,
    is_postpartum_within_year: bool,
) -> CheckResult | None:
    """임신 중이거나 산후 1년 이내인 근로자의 22:00~06:00 근로 제한을 확인한다.

    ``_minor_work_intervals``·``_overlaps``는 연소자 전용 로직이 아니라 계약상
    근로 구간과 특정 시간대의 겹침만 계산하는 일반 로직이라 그대로 재사용한다.
    """

    if not (is_pregnant or is_postpartum_within_year):
        return None

    work_intervals = _minor_work_intervals(terms)
    if work_intervals is None:
        return CheckResult(
            code="PREGNANT_NIGHT_WORK",
            label="임산부 야간근로",
            status=CheckStatus.UNKNOWN,
            legal_basis=PREGNANT_NIGHT_WORK_BASIS,
            standard_year=STANDARD_YEAR,
            calculation="근무 시각 정보 없음",
            detail=(
                "시업·종업 시각을 해석할 수 없어 22:00~06:00 시간대와의 겹침을 "
                "확인하지 못했습니다."
            ),
        )

    night_start = _safe_time_minutes(PREGNANT_NIGHT_START)
    night_end = _safe_time_minutes(PREGNANT_NIGHT_END)
    assert night_start is not None and night_end is not None
    overlaps_night = any(
        _overlaps(start, end, 0, night_end)
        or _overlaps(start, end, night_start, 24 * 60 + night_end)
        for start, end in work_intervals
    )

    work_range = f"{terms.work_start_time.value}~{terms.work_end_time.value}"
    if overlaps_night:
        return CheckResult(
            code="PREGNANT_NIGHT_WORK",
            label="임산부 야간근로",
            status=CheckStatus.VIOLATION,
            legal_basis=PREGNANT_NIGHT_WORK_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"근무 {work_range}(기재된 휴게시간 제외)와 "
                f"야간 {PREGNANT_NIGHT_START}~{PREGNANT_NIGHT_END} 시간대가 겹침"
            ),
            detail=(
                "임신 중이거나 산후 1년이 지나지 않은 근로자는 22:00~06:00 및 휴일에 "
                "근로시킬 수 없는 것이 원칙입니다. 본인 동의(임신 중인 경우 명시적 청구)와 "
                "고용노동부장관의 인가가 있으면 예외이며, 예외 인정 여부는 입력만으로 "
                "확인되지 않았습니다. 휴일근로 포함 여부는 이 판정에 포함되어 있지 않습니다."
            ),
        )

    return CheckResult(
        code="PREGNANT_NIGHT_WORK",
        label="임산부 야간근로",
        status=CheckStatus.OK,
        legal_basis=PREGNANT_NIGHT_WORK_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=(
            f"근무 {work_range}(기재된 휴게시간 제외)와 "
            f"야간 {PREGNANT_NIGHT_START}~{PREGNANT_NIGHT_END} 시간대가 겹치지 않음"
        ),
        detail=(
            "확인된 계약상 근무 시각만 비교한 결과입니다. "
            "휴일근로 포함 여부는 이 판정에 포함되어 있지 않습니다."
        ),
    )


def check_disabled_accommodation(is_disabled: bool) -> CheckResult | None:
    """장애인 근로자는 시간 상한 대신 균등처우·편의제공 협의를 안내한다."""

    if not is_disabled:
        return None

    return CheckResult(
        code="DISABLED_ACCOMMODATION",
        label="장애인 근로자 편의제공 협의",
        status=CheckStatus.OK,
        legal_basis=DISABLED_ACCOMMODATION_BASIS,
        standard_year=STANDARD_YEAR,
        calculation=None,
        detail=(
            "FairSign은 근로시간 등 계약 조건을 장애를 이유로 자동 조정하지 않습니다. "
            "근무시간·업무·시설 등 필요한 편의가 있다면 사업주와 미리 협의해 두는 것을 "
            "권장합니다. 균등처우(근로기준법 제6조)와 정당한 편의제공(장애인차별금지법 "
            "제11조) 의무가 있습니다."
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
        f"주 소정근로시간 {_hours(weekly_hours)} "
        f"{'≥' if weekly_hours >= WEEKLY_HOLIDAY_MIN_HOURS else '<'} "
        f"{WEEKLY_HOLIDAY_MIN_HOURS:g}시간"
    )

    if weekly_hours < WEEKLY_HOLIDAY_MIN_HOURS:
        # ⚠️ 여기가 "몰라서 못 받는 것"이 가장 크게 생기는 지점이다.
        #
        #    주 15시간 미만이면 주휴수당(제18조제3항)뿐 아니라
        #    연차유급휴가와 퇴직금(퇴직급여법 제4조제1항 단서)까지 제외된다.
        #    세 가지가 한꺼번에 빠지는데, 계약서에는 그런 말이 한 줄도 없다.
        #
        #    예전에는 "충족하지 않습니다" 한 줄로 끝냈다. 그러면 사용자는
        #    무엇을 못 받는지도, 얼마나 모자란지도 모른 채 넘어간다.
        #    30분 모자란 것과 5시간 모자란 것은 대응이 완전히 다르다.
        #
        #    ⚠️ 다만 주 15시간 미만 계약 자체는 **위법이 아니다.**
        #       그래서 status 는 OK 로 둔다. 사장님을 탓하는 문구를 쓰지 않는다.
        #       사실을 알려주고 판단은 사용자가 한다.
        shortfall = WEEKLY_HOLIDAY_MIN_HOURS - weekly_hours
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴 시간 요건",
            status=CheckStatus.OK,
            legal_basis=WEEKLY_HOLIDAY_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=(
                f"{calculation} — {_hours(shortfall)} 모자람"
            ),
            detail=(
                f"계약상 주 소정근로시간이 15시간에서 {_hours(shortfall)} "
                "모자랍니다. 주 15시간 미만이면 주휴수당·연차유급휴가·퇴직금이 "
                "모두 적용되지 않습니다(근로기준법 제18조제3항, "
                "근로자퇴직급여 보장법 제4조제1항). "
                "주 15시간 미만 계약 자체가 위법한 것은 아니며, "
                "근무시간 조정이 가능한지는 사업주와 논의할 사항입니다."
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

    # 값은 있지만 AI가 자신 없어 하는 경우.
    # 빈칸에 요일을 지어낸 사례가 있어 OK로 넘기지 않는다. (_is_unreliable 주석 참고)
    if _is_unreliable(terms.weekly_holiday_day):
        return CheckResult(
            code="WEEKLY_HOLIDAY",
            label="주휴 시간 요건·주휴일",
            status=CheckStatus.UNKNOWN,
            legal_basis=WEEKLY_HOLIDAY_BASIS,
            standard_year=STANDARD_YEAR,
            calculation=calculation,
            detail=(
                f"계약서에서 주휴일을 '{terms.weekly_holiday_day.value}'(으)로 읽었으나 "
                "인식 신뢰도가 낮습니다. 계약서 원본에서 주휴일 요일을 직접 "
                "확인해 주세요. 확인 전에는 기재 여부를 판정하지 않습니다."
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
                f"1일 소정근로시간 {_hours(hours_per_day)} < 4시간 — "
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
                f"1일 소정근로시간 {_hours(hours_per_day)} → "
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
                f"1일 소정근로시간 {_hours(hours_per_day)} → "
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
            f"1일 소정근로시간 {_hours(hours_per_day)}: "
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
    *,
    worker_is_pregnant: bool = False,
    worker_pregnancy_week: int | None = None,
    worker_is_postpartum_within_year: bool = False,
    worker_is_disabled: bool = False,
) -> ValidationReport:
    """모든 지원 규칙을 실행해 하나의 검증 보고서를 반환한다."""

    optional_checks = (
        check_minor_working_hours(terms, worker_birth_date),
        check_minor_night_work(terms, worker_birth_date),
        check_pregnant_overtime(terms, worker_is_pregnant),
        check_postpartum_overtime_limit(
            terms, worker_is_postpartum_within_year, worker_is_pregnant
        ),
        check_pregnant_shortened_hours(worker_is_pregnant, worker_pregnancy_week),
        check_pregnant_night_work(
            terms, worker_is_pregnant, worker_is_postpartum_within_year
        ),
        check_disabled_accommodation(worker_is_disabled),
    )
    checks = [
        check_minimum_wage(terms),
        check_weekly_holiday(terms),
        check_break_time(terms),
        *(check for check in optional_checks if check is not None),
        *check_required_fields(terms),
    ]
    return ValidationReport(
        checks=checks,
        # 월 환산에는 유급주휴 등 추가 사실이 필요하므로 MVP에서 추정하지 않는다.
        estimated_monthly_pay=None,
        wage_shortfall=None,
    )
