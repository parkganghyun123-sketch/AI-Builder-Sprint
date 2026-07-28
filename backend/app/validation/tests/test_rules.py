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
    assert "14.9시간 < 15시간" in result.calculation
    assert "충족하지 않습니다" in result.detail


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
