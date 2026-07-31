import json

import pytest

from app.schemas import (
    CheckStatus,
    Confidence,
    ContractTerms,
    ExtractedField,
    ValidationReport,
    WageType,
)
from app.validation.cli import main as cli_main
from app.validation.rules import (
    check_break_time,
    check_minimum_wage,
    check_minor_night_work,
    check_minor_working_hours,
    check_required_fields,
    check_weekly_holiday,
    validate,
)


def field(
    value: str | int | None,
    *,
    confidence: Confidence | None = None,
) -> ExtractedField:
    if confidence is None:
        confidence = Confidence.NOT_FOUND if value is None else Confidence.HIGH
    return ExtractedField(
        value=value,
        confidence=confidence,
        source_text=None if value is None else str(value),
    )


def terms(**overrides: ExtractedField) -> ContractTerms:
    values: dict[str, ExtractedField] = {
        "contract_start": field("2026-08-01"),
        "contract_end": field("2026-12-31"),
        "workplace": field("부산시 가상매장"),
        "job_description": field("매장 보조"),
        "work_start_time": field("09:00"),
        "work_end_time": field("15:30"),
        "break_start_time": field("12:00"),
        "break_end_time": field("12:30"),
        "work_days_per_week": field(3),
        "weekly_holiday_day": field("일요일"),
        "wage_type": field(WageType.HOURLY.value),
        "wage_amount": field(10_320),
        "has_bonus": field("없음"),
        "other_allowance": field("없음"),
        "payday": field("매월 10일"),
        "payment_method": field("계좌이체"),
        "employer_business_name": field("가상상점"),
        "employer_phone": field("010-0000-0000"),
        "employer_address": field("부산시 가상구"),
        "employer_name": field("가상사업주"),
        "worker_address": field("부산시 가상동"),
        "worker_contact": field("010-1111-1111"),
        "worker_name": field("가상근로자"),
    }
    values.update(overrides)
    return ContractTerms(**values)


def test_minimum_wage_exact_boundary_is_ok() -> None:
    result = check_minimum_wage(terms(wage_amount=field(10_320)))

    assert result.status == CheckStatus.OK
    assert "10,320원 ≥" in result.calculation


def test_minimum_wage_one_won_below_is_violation() -> None:
    result = check_minimum_wage(terms(wage_amount=field(10_319)))

    assert result.status == CheckStatus.VIOLATION
    assert "10,319원 <" in result.calculation


@pytest.mark.parametrize("wage_type", [WageType.DAILY, WageType.MONTHLY])
def test_non_hourly_wage_is_unknown(wage_type: WageType) -> None:
    result = check_minimum_wage(
        terms(wage_type=field(wage_type.value), wage_amount=field(2_000_000))
    )

    assert result.status == CheckStatus.UNKNOWN
    assert "시간급으로 기재된 계약만 판정" in result.detail


def test_missing_wage_is_unknown() -> None:
    result = check_minimum_wage(terms(wage_amount=field(None)))

    assert result.status == CheckStatus.UNKNOWN
    assert result.calculation is not None


def test_not_found_wage_confidence_is_unknown_even_if_value_exists() -> None:
    result = check_minimum_wage(
        terms(
            wage_amount=field(
                10_320,
                confidence=Confidence.NOT_FOUND,
            )
        )
    )

    assert result.status == CheckStatus.UNKNOWN


def test_weekly_hours_exactly_fifteen_meets_time_threshold() -> None:
    result = check_weekly_holiday(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("14:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(3),
        )
    )

    assert result.status == CheckStatus.OK
    assert "15시간 ≥ 15시간" in result.calculation
    assert "개근" in result.detail


def test_weekly_hours_14_point_9_does_not_meet_time_threshold() -> None:
    result = check_weekly_holiday(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("13:58"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(3),
        )
    )

    assert result.status == CheckStatus.OK
    # 시간은 분 단위로 끊어 표시한다. 이 문자열이 사용자가 사장님에게 보낼
    # 문구에 그대로 들어가므로 부동소수점(14.9000000000001)이 새면 안 된다.
    # 근거: app/validation/rules.py _hours()
    assert "14시간 54분 < 15시간" in result.calculation

    # ⚠️ "충족하지 않습니다" 로 끝내지 않는다.
    #    주 15시간 미만이면 주휴수당뿐 아니라 연차·퇴직금까지 함께 빠진다.
    #    무엇을 못 받는지, 얼마나 모자란지를 알려줘야 사용자가 대응할 수 있다.
    #    (30분 모자란 것과 5시간 모자란 것은 대응이 완전히 다르다)
    assert "6분 모자람" in result.calculation
    assert "연차유급휴가" in result.detail
    assert "퇴직금" in result.detail
    # 주 15시간 미만 계약 자체는 위법이 아니다. 사업주를 탓하지 않는다.
    assert "위법한 것은 아니며" in result.detail


def test_weekly_hours_missing_is_unknown() -> None:
    result = check_weekly_holiday(terms(work_days_per_week=field(None)))

    assert result.status == CheckStatus.UNKNOWN


def test_invalid_weekly_days_is_unknown_instead_of_raising() -> None:
    result = check_weekly_holiday(terms(work_days_per_week=field("주 3일")))

    assert result.status == CheckStatus.UNKNOWN


def test_not_found_work_time_confidence_is_unknown() -> None:
    result = check_weekly_holiday(
        terms(
            work_start_time=field(
                "09:00",
                confidence=Confidence.NOT_FOUND,
            )
        )
    )

    assert result.status == CheckStatus.UNKNOWN


def test_weekly_holiday_day_missing_is_missing_when_time_threshold_met() -> None:
    result = check_weekly_holiday(terms(weekly_holiday_day=field(None)))

    assert result.status == CheckStatus.MISSING
    assert "주휴일 요일" in result.detail
    assert "개근" in result.detail


def test_six_work_hours_with_thirty_minute_break_is_ok() -> None:
    result = check_break_time(terms())

    assert result.status == CheckStatus.OK
    assert "휴게 30분 ≥ 최소 30분" in result.calculation


def test_eight_work_hours_with_thirty_minute_break_is_violation() -> None:
    result = check_break_time(
        terms(
            work_end_time=field("17:30"),
            break_start_time=field("12:00"),
            break_end_time=field("12:30"),
        )
    )

    assert result.status == CheckStatus.VIOLATION
    assert "휴게 30분 < 최소 60분" in result.calculation


def test_eight_work_hours_with_sixty_minute_break_is_ok() -> None:
    result = check_break_time(
        terms(
            work_end_time=field("18:00"),
            break_start_time=field("12:00"),
            break_end_time=field("13:00"),
        )
    )

    assert result.status == CheckStatus.OK
    assert "휴게 60분 ≥ 최소 60분" in result.calculation


def test_less_than_four_hours_does_not_require_break_comparison() -> None:
    result = check_break_time(
        terms(
            work_end_time=field("12:00"),
            break_start_time=field(None),
            break_end_time=field(None),
        )
    )

    assert result.status == CheckStatus.OK
    assert "비교 대상 아님" in result.calculation


def test_missing_break_time_is_unknown_when_break_is_required() -> None:
    result = check_break_time(
        terms(
            work_end_time=field("15:00"),
            break_start_time=field(None),
            break_end_time=field(None),
        )
    )

    assert result.status == CheckStatus.UNKNOWN
    assert "확인할 수 없습니다" in result.detail


def test_missing_work_time_is_unknown() -> None:
    result = check_break_time(terms(work_start_time=field(None)))

    assert result.status == CheckStatus.UNKNOWN


def test_break_longer_than_shift_is_unknown() -> None:
    result = check_break_time(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("10:00"),
            break_start_time=field("09:00"),
            break_end_time=field("11:00"),
        )
    )

    assert result.status == CheckStatus.UNKNOWN


def test_required_fields_report_missing_group() -> None:
    results = check_required_fields(terms(job_description=field(None)))
    by_code = {result.code: result for result in results}

    assert by_code["REQUIRED_JOB"].status == CheckStatus.MISSING
    assert by_code["REQUIRED_WAGE"].status == CheckStatus.OK


def test_not_found_confidence_is_missing_even_if_value_exists() -> None:
    results = check_required_fields(
        terms(
            workplace=field(
                "추정 장소",
                confidence=Confidence.NOT_FOUND,
            )
        )
    )
    by_code = {result.code: result for result in results}

    assert by_code["REQUIRED_WORKPLACE"].status == CheckStatus.MISSING


def test_seventeen_year_old_working_eight_hours_exceeds_basic_limit() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("17:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(4),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION
    assert result.standard_year == 2026
    assert "1일 8시간 > 기본 7시간" in result.calculation
    assert "당사자 합의 여부" in result.detail


def test_seventeen_year_old_working_seven_hours_meets_basic_limit() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("16:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(5),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.OK
    assert "1일 7시간 ≤ 기본 7시간" in result.calculation
    assert "1주 35시간 ≤ 기본 35시간" in result.calculation


def test_seventeen_year_old_over_thirty_five_weekly_hours_is_violation() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("15:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(6),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION
    assert "1주 36시간 > 기본 35시간" in result.calculation
    assert "별도 확인" in result.detail


def test_minor_hours_beyond_agreed_extension_limit_is_distinguished() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("09:00"),
            work_end_time=field("18:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(4),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION
    assert "연장 한도" in result.detail
    assert "1일 총 8시간" in result.detail


def test_seventeen_year_old_overnight_shift_overlaps_night_hours() -> None:
    result = check_minor_night_work(
        terms(
            work_start_time=field("22:00"),
            work_end_time=field("02:00"),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION
    assert "22:00~02:00" in result.calculation
    assert "고용노동부장관 인가" in result.detail


def test_minor_working_hours_calculate_overnight_shift() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("22:00"),
            work_end_time=field("02:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(5),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.OK
    assert "1일 4시간 ≤ 기본 7시간" in result.calculation
    assert "1주 20시간 ≤ 기본 35시간" in result.calculation


def test_minor_overnight_eight_hours_without_break_exceeds_basic_limit() -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("22:00"),
            work_end_time=field("06:00"),
            break_start_time=field(None),
            break_end_time=field(None),
            work_days_per_week=field(4),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION
    assert "1일 8시간 > 기본 7시간" in result.calculation


@pytest.mark.parametrize(
    ("break_start", "break_end"),
    [
        ("23:30", "00:30"),
        ("00:30", "01:30"),
    ],
)
def test_minor_overnight_hours_subtract_cross_midnight_or_next_day_break(
    break_start: str,
    break_end: str,
) -> None:
    result = check_minor_working_hours(
        terms(
            work_start_time=field("22:00"),
            work_end_time=field("06:00"),
            break_start_time=field(break_start),
            break_end_time=field(break_end),
            work_days_per_week=field(5),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.OK
    assert "1일 7시간 ≤ 기본 7시간" in result.calculation
    assert "1주 35시간 ≤ 기본 35시간" in result.calculation


def test_minor_night_work_excludes_break_covering_entire_night_window() -> None:
    result = check_minor_night_work(
        terms(
            work_start_time=field("21:00"),
            work_end_time=field("07:00"),
            break_start_time=field("22:00"),
            break_end_time=field("06:00"),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.OK
    assert "기재된 휴게시간 제외" in result.calculation
    assert "겹치지 않음" in result.calculation


def test_exact_daytime_boundary_does_not_overlap_minor_night_hours() -> None:
    result = check_minor_night_work(
        terms(
            work_start_time=field("06:00"),
            work_end_time=field("22:00"),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.OK
    assert "겹치지 않음" in result.calculation


@pytest.mark.parametrize(
    ("work_start", "work_end"),
    [
        ("22:00", "23:00"),
        ("05:00", "06:00"),
    ],
)
def test_minor_night_boundaries_inside_restricted_window_are_violation(
    work_start: str,
    work_end: str,
) -> None:
    result = check_minor_night_work(
        terms(
            work_start_time=field(work_start),
            work_end_time=field(work_end),
        ),
        "2009-07-31",
    )

    assert result is not None
    assert result.status == CheckStatus.VIOLATION


def test_nineteen_year_old_does_not_get_minor_checks() -> None:
    contract = terms(
        work_start_time=field("09:00"),
        work_end_time=field("17:00"),
        break_start_time=field(None),
        break_end_time=field(None),
    )

    assert check_minor_working_hours(contract, "2007-08-01") is None
    assert check_minor_night_work(contract, "2007-08-01") is None
    report = validate(contract, worker_birth_date="2007-08-01")
    assert not any(check.code.startswith("MINOR_") for check in report.checks)


def test_missing_birth_date_does_not_get_minor_checks() -> None:
    contract = terms()

    assert check_minor_working_hours(contract, None) is None
    assert check_minor_night_work(contract, None) is None
    report = validate(contract)
    assert not any(check.code.startswith("MINOR_") for check in report.checks)


@pytest.mark.parametrize("birth_date", ["", "2009/07/31", "not-a-date"])
def test_invalid_birth_date_does_not_get_minor_checks(birth_date: str) -> None:
    contract = terms()

    assert check_minor_working_hours(contract, birth_date) is None
    assert check_minor_night_work(contract, birth_date) is None


def test_under_fifteen_does_not_get_minor_checks() -> None:
    contract = terms()

    assert check_minor_working_hours(contract, "2011-08-02") is None
    assert check_minor_night_work(contract, "2011-08-02") is None


@pytest.mark.parametrize("contract_start", [None, "2026/08/01", "not-a-date"])
def test_missing_or_invalid_contract_start_skips_minor_checks(
    contract_start: str | None,
) -> None:
    contract = terms(contract_start=field(contract_start))

    assert check_minor_working_hours(contract, "2009-07-31") is None
    assert check_minor_night_work(contract, "2009-07-31") is None


def test_contract_start_outside_supported_year_skips_minor_checks() -> None:
    contract = terms(contract_start=field("2030-08-01"))

    assert check_minor_working_hours(contract, "2013-07-31") is None
    assert check_minor_night_work(contract, "2013-07-31") is None
    report = validate(contract, worker_birth_date="2013-07-31")
    assert not any(check.code.startswith("MINOR_") for check in report.checks)


def test_age_is_calculated_at_fixed_contract_start_birthday_boundary() -> None:
    day_before_eighteenth_birthday = terms(contract_start=field("2026-08-01"))
    on_eighteenth_birthday = terms(contract_start=field("2026-08-02"))

    assert (
        check_minor_working_hours(
            day_before_eighteenth_birthday,
            "2008-08-02",
        )
        is not None
    )
    assert (
        check_minor_working_hours(
            on_eighteenth_birthday,
            "2008-08-02",
        )
        is None
    )


def test_validate_conditionally_includes_minor_checks() -> None:
    report = validate(terms(), worker_birth_date="2009-07-31")
    minor_codes = {
        check.code for check in report.checks if check.code.startswith("MINOR_")
    }

    assert minor_codes == {"MINOR_WORKING_HOURS", "MINOR_NIGHT_WORK"}


def test_validate_returns_report_with_evidence_for_every_check() -> None:
    report = validate(terms())

    assert isinstance(report, ValidationReport)
    assert len(report.checks) >= 10
    assert all(check.legal_basis for check in report.checks)
    assert all(check.calculation for check in report.checks)
    assert report.estimated_monthly_pay is None
    assert report.wage_shortfall is None


def test_validate_does_not_mutate_contract_terms() -> None:
    contract = terms()
    before = contract.model_dump()

    validate(contract)

    assert contract.model_dump() == before


def test_validation_report_marks_violation_as_problem() -> None:
    report = validate(terms(wage_amount=field(10_319)))

    assert report.has_problem is True


def test_cli_reads_contract_json_and_prints_report(
    tmp_path,
    capsys,
) -> None:
    input_path = tmp_path / "contract.json"
    input_path.write_text(terms().model_dump_json(), encoding="utf-8")

    exit_code = cli_main([str(input_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["checks"][0]["code"] == "MINIMUM_WAGE"
    assert output["checks"][0]["status"] == CheckStatus.OK.value


# ============================================================
# 낮은 신뢰도 값으로 '문제 없음'이라고 말하지 않기
#
# 실측에서 나온 위험이다. 계약서의 주휴일 칸이 비어 있는데
# ('주휴일 매주 ( ) 요일') 모델이 요일을 지어냈고, confidence 는
# LOW 였지만 값이 있다는 이유로 "주휴일 기재됨 = OK" 로 판정되어
# 실제 위반이 가려졌다.
#
# 같은 사진 두 번 실행에서 문제 1건 / 2건으로 결과가 갈렸다.
# ============================================================


def _weekly_holiday_check(**overrides):
    report = validate(terms(**overrides))
    return next(c for c in report.checks if c.code == "WEEKLY_HOLIDAY")


def test_low_confidence_weekly_holiday_is_not_ok() -> None:
    """지어냈을 수 있는 값으로 안심시키지 않는다."""
    check = _weekly_holiday_check(
        weekly_holiday_day=field("일요일", confidence=Confidence.LOW)
    )
    assert check.status == CheckStatus.UNKNOWN


def test_high_confidence_weekly_holiday_is_ok() -> None:
    """확실한 값이면 정상 판정한다."""
    check = _weekly_holiday_check(
        weekly_holiday_day=field("일요일", confidence=Confidence.HIGH)
    )
    assert check.status == CheckStatus.OK


def test_absent_weekly_holiday_is_still_missing() -> None:
    """
    값이 없으면 여전히 MISSING 이다.
    보수적으로 경고하는 방향은 그대로 둔다 — 위험한 건 반대 방향이다.
    """
    check = _weekly_holiday_check(weekly_holiday_day=field(None))
    assert check.status == CheckStatus.MISSING


def test_low_confidence_detail_tells_user_to_verify() -> None:
    """사용자가 원본을 확인하도록 안내해야 한다."""
    check = _weekly_holiday_check(
        weekly_holiday_day=field("일요일", confidence=Confidence.LOW)
    )
    assert "확인" in (check.detail or "")
