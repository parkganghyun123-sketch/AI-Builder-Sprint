from app.schemas import CheckStatus, Confidence
from app.validation import rules
from app.validation.tests.conftest import field


class TestMinimumWage:
    def test_exact_minimum_wage_is_ok(self, terms_factory):
        terms = terms_factory(wage_amount=field("10320"))
        result = rules.check_minimum_wage(terms)
        assert result.status == CheckStatus.OK

    def test_one_won_below_is_violation(self, terms_factory):
        terms = terms_factory(wage_amount=field("10319"))
        result = rules.check_minimum_wage(terms)
        assert result.status == CheckStatus.VIOLATION

    def test_monthly_wage_is_unknown(self, terms_factory):
        terms = terms_factory(
            wage_type=field("MONTHLY"), wage_amount=field("2000000")
        )
        result = rules.check_minimum_wage(terms)
        assert result.status == CheckStatus.UNKNOWN

    def test_missing_wage_amount_is_unknown_not_crash(self, terms_factory):
        terms = terms_factory(
            wage_amount=field(None, confidence=Confidence.NOT_FOUND)
        )
        result = rules.check_minimum_wage(terms)
        assert result.status == CheckStatus.UNKNOWN


class TestWeeklyHoliday:
    def test_exactly_15_hours_meets_requirement(self, terms_factory):
        terms = terms_factory(
            work_start_time=field("00:00"),
            work_end_time=field("15:00"),
            break_start_time=field("00:00"),
            break_end_time=field("00:00"),
            work_days_per_week=field(1),
        )
        result = rules.check_weekly_holiday(terms)
        assert result.status == CheckStatus.OK
        assert "충족" in result.calculation
        assert "미충족" not in result.calculation

    def test_14_9_hours_does_not_meet_requirement(self, terms_factory):
        terms = terms_factory(
            work_start_time=field("00:00"),
            work_end_time=field("14:54"),
            break_start_time=field("00:00"),
            break_end_time=field("00:00"),
            work_days_per_week=field(1),
        )
        result = rules.check_weekly_holiday(terms)
        assert "미충족" in result.calculation

    def test_missing_weekly_holiday_day_is_missing(self, terms_factory):
        terms = terms_factory(
            weekly_holiday_day=field(None, confidence=Confidence.NOT_FOUND)
        )
        result = rules.check_weekly_holiday(terms)
        assert result.status == CheckStatus.MISSING

    def test_never_asserts_entitlement(self, terms_factory):
        terms = terms_factory()
        result = rules.check_weekly_holiday(terms)
        assert "대상입니다" not in (result.detail or "")


class TestBreakTime:
    def test_six_hours_with_30min_break_is_ok(self, terms_factory):
        terms = terms_factory(
            work_start_time=field("09:00"),
            work_end_time=field("15:30"),
            break_start_time=field("12:00"),
            break_end_time=field("12:30"),
        )
        result = rules.check_break_time(terms)
        assert result.status == CheckStatus.OK

    def test_eight_hours_with_30min_break_is_violation(self, terms_factory):
        terms = terms_factory(
            work_start_time=field("09:00"),
            work_end_time=field("17:30"),
            break_start_time=field("12:00"),
            break_end_time=field("12:30"),
        )
        result = rules.check_break_time(terms)
        assert result.status == CheckStatus.VIOLATION

    def test_missing_times_is_unknown_not_crash(self, terms_factory):
        terms = terms_factory(
            work_start_time=field(None, confidence=Confidence.NOT_FOUND)
        )
        result = rules.check_break_time(terms)
        assert result.status == CheckStatus.UNKNOWN


class TestRequiredFields:
    def test_all_present_returns_no_missing(self, terms_factory):
        terms = terms_factory()
        assert rules.check_required_fields(terms) == []

    def test_missing_workplace_is_flagged(self, terms_factory):
        terms = terms_factory(
            workplace=field(None, confidence=Confidence.NOT_FOUND)
        )
        results = rules.check_required_fields(terms)
        codes = [r.code for r in results]
        assert "MISSING_WORKPLACE" in codes
        assert all(r.status == CheckStatus.MISSING for r in results)

    def test_weekly_holiday_day_not_double_counted(self, terms_factory):
        terms = terms_factory(
            weekly_holiday_day=field(None, confidence=Confidence.NOT_FOUND)
        )
        results = rules.check_required_fields(terms)
        codes = [r.code for r in results]
        assert "MISSING_WEEKLY_HOLIDAY_DAY" not in codes


class TestValidate:
    def test_full_report_with_violations(self, terms_factory):
        terms = terms_factory(wage_amount=field("9000"))
        report = rules.validate(terms)
        assert report.has_problem is True
        assert report.wage_shortfall is not None

    def test_full_report_all_ok(self, terms_factory):
        terms = terms_factory()
        report = rules.validate(terms)
        assert isinstance(report.checks, list)
        assert len(report.checks) >= 3
