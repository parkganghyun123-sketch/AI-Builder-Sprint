"""
입력값 유효성 · 진행 차단 기준 테스트.

핵심 구분:
  임금 0원  → 값 자체가 성립 안 함 → error, 차단
  최저임금 미달 → 사실이고 협의 대상 → warning, 진행 가능

둘을 같은 칸에 넣으면 0원짜리 계약서가 만들어진다.
"""

import pytest

from app.schemas import Confidence, ContractTerms, ExtractedField, WageType
from app.validation.rules import validate
from app.validation.severity import build_validation_state


def f(value, confidence=Confidence.HIGH) -> ExtractedField:
    return ExtractedField(value=value, confidence=confidence)


def terms(**overrides) -> ContractTerms:
    base = dict(
        contract_start=f("2026년 8월 1일"),
        contract_end=f("2027년 1월 31일"),
        workplace=f("카페 000"),
        job_description=f("음료 제조"),
        work_start_time=f("09:00"),
        work_end_time=f("16:00"),
        break_start_time=f("12:00"),
        break_end_time=f("12:30"),
        work_days_per_week=f("3"),
        weekly_holiday_day=f("일요일"),
        wage_type=f(WageType.HOURLY.value),
        wage_amount=f("10320"),
        has_bonus=f("없음"),
        other_allowance=f("없음"),
        payday=f("매월 10일"),
        payment_method=f("계좌 입금"),
        employer_business_name=f("카페 000"),
        employer_phone=f(None, Confidence.NOT_FOUND),
        employer_address=f(None, Confidence.NOT_FOUND),
        employer_name=f("김사장"),
        worker_address=f(None, Confidence.NOT_FOUND),
        worker_contact=f(None, Confidence.NOT_FOUND),
        worker_name=f("박강현"),
    )
    base.update(overrides)
    return ContractTerms(**base)


def state(t):
    return build_validation_state(t, validate(t))


class TestWageBlocking:
    """임금은 계약의 핵심이다. 값이 성립하지 않으면 문서를 만들지 않는다."""

    @pytest.mark.parametrize(
        "bad", ["0000", "0", "-5000", "abc", "", "   ", "50"]
    )
    def test_invalid_wage_blocks(self, bad):
        s = state(terms(wage_amount=f(bad)))
        assert not s.can_proceed, f"{bad!r} 가 통과됐다"
        assert "wage_amount" in [i.field for i in s.blocking]

    def test_zero_wage_reason_is_not_minimum_wage(self):
        """
        0원을 '최저임금 미달'이라고 말하면 안 된다.
        사용자가 '사장님이 0원 주기로 했나' 로 읽는다.
        """
        s = state(terms(wage_amount=f("0000")))
        issue = next(i for i in s.blocking if i.field == "wage_amount")
        assert "0원" in issue.reason
        assert "최저임금" not in issue.reason

    def test_every_blocking_issue_tells_how_to_fix(self):
        s = state(terms(wage_amount=f("0000")))
        for issue in s.blocking:
            assert issue.fix, f"{issue.field} 에 수정 방법이 없다"
            assert issue.label
            assert issue.severity == "error"


class TestLegalIsWarningNotError:
    """법정 기준 위반은 사실이다. 알고도 진행할 수 있어야 한다."""

    def test_below_minimum_wage_does_not_block(self):
        s = state(terms(wage_amount=f("9500")))
        assert s.can_proceed
        assert s.to_dict()["counts"]["warning"] >= 1

    def test_valid_contract_has_no_issues(self):
        assert state(terms()).can_proceed


class TestOtherFields:
    def test_invalid_time_blocks(self):
        assert not state(terms(work_start_time=f("25:00"))).can_proceed

    def test_valid_time_passes(self):
        assert state(terms(work_start_time=f("09:00"))).can_proceed

    @pytest.mark.parametrize("bad", ["0", "9", "abc"])
    def test_impossible_work_days_block(self, bad):
        assert not state(terms(work_days_per_week=f(bad))).can_proceed

    def test_missing_required_field_blocks(self):
        s = state(terms(worker_name=f(None, Confidence.NOT_FOUND)))
        assert not s.can_proceed
        assert "worker_name" in [i.field for i in s.blocking]

    def test_optional_field_does_not_block(self):
        """주휴일이 비어도 계약서는 만들 수 있다. 판정이 누락으로 잡는다."""
        assert state(terms(weekly_holiday_day=f(None, Confidence.NOT_FOUND))).can_proceed


class TestResponseShape:
    """'확인할 항목 5건' 처럼 개수만 주지 않는다."""

    def test_issue_carries_enough_to_render(self):
        d = state(terms(wage_amount=f("0000"))).to_dict()
        assert set(d) >= {"can_proceed", "blocking_fields", "counts", "issues"}
        for issue in d["issues"]:
            assert set(issue) >= {
                "field", "label", "severity", "value",
                "reason", "fix", "blocks", "step",
            }

    def test_errors_come_first(self):
        d = state(terms(wage_amount=f("0000"))).to_dict()
        order = {"error": 0, "warning": 1, "info": 2}
        levels = [order[i["severity"]] for i in d["issues"]]
        assert levels == sorted(levels)

    def test_blocking_fields_match_issues(self):
        d = state(terms(wage_amount=f("0000"))).to_dict()
        assert d["blocking_fields"] == [
            i["field"] for i in d["issues"] if i["blocks"]
        ]
