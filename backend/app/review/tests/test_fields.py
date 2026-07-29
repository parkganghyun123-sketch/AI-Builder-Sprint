"""
확인 관문 테스트.

기준 자체가 실측에서 나왔으므로, 그 실측 상황을 그대로 재현해
"막아야 할 것을 막는가"를 확인한다.

실측: spikes/fixtures/handwritten_01.png, 3회 반복
  wage_amount   '10 000' → '0000'  (LOW로 강등됨)
  worker_name   '박강현'  → '박강헌'  (HIGH — 신뢰도로 못 걸러짐)
"""

import pytest

from app.review.fields import (
    IDENTITY_FIELDS,
    JUDGMENT_FIELDS,
    build_review_items,
    priority,
    unconfirmed_high_priority,
)
from app.schemas import Confidence, ContractTerms, ExtractedField


def f(value, confidence=Confidence.HIGH) -> ExtractedField:
    return ExtractedField(value=value, confidence=confidence)


def make_terms(**overrides) -> ContractTerms:
    """손글씨 실측 결과를 그대로 재현한 조건."""
    base = dict(
        contract_start=f("2026년 11월 1일"),
        contract_end=f("2027년 10월 5일"),
        workplace=f(None, Confidence.NOT_FOUND),
        job_description=f(None, Confidence.NOT_FOUND),
        work_start_time=f("12:00"),
        work_end_time=f("15:00"),
        break_start_time=f(None, Confidence.NOT_FOUND),
        break_end_time=f(None, Confidence.NOT_FOUND),
        work_days_per_week=f("3"),
        weekly_holiday_day=f(None, Confidence.NOT_FOUND),
        wage_type=f(None, Confidence.NOT_FOUND),
        wage_amount=f("0000", Confidence.LOW),
        has_bonus=f("없음"),
        other_allowance=f("없음"),
        payday=f(None, Confidence.NOT_FOUND),
        payment_method=f("근로자 명의 계좌에 입금"),
        employer_business_name=f(None, Confidence.NOT_FOUND),
        employer_phone=f(None, Confidence.NOT_FOUND),
        employer_address=f(None, Confidence.NOT_FOUND),
        employer_name=f(None, Confidence.NOT_FOUND),
        worker_address=f(None, Confidence.NOT_FOUND),
        worker_contact=f(None, Confidence.NOT_FOUND),
        worker_name=f("박강헌"),
    )
    base.update(overrides)
    return ContractTerms(**base)


class TestIdentityAlwaysConfirmed:
    """
    신원 정보는 신뢰도로 걸러지지 않는다.
    '박강현' → '박강헌' 이 HIGH 로 나왔고, 값이 상식적이라
    코드가 이상하다고 판단할 근거가 없었다. 사람이 보는 수밖에 없다.
    """

    @pytest.mark.parametrize("name", sorted(IDENTITY_FIELDS))
    def test_high_confidence_identity_still_needs_confirmation(self, name):
        assert priority(name, f("아무값", Confidence.HIGH)) == "high"

    def test_confidently_wrong_name_is_blocked(self):
        """실측 그대로: 박강헌(HIGH)이 서명을 막아야 한다."""
        blocked = unconfirmed_high_priority(make_terms(), set())
        assert "근로자 성명" in blocked


class TestJudgmentFields:
    def test_low_confidence_judgment_field_is_high(self):
        """'0000'(시급) 처럼 틀린 값으로 판정이 돌면 결과가 뒤집힌다."""
        assert priority("wage_amount", f("0000", Confidence.LOW)) == "high"

    def test_not_found_judgment_field_is_not_high(self):
        """
        값이 없으면 판정이 이미 '누락'으로 잡는다.
        여기까지 막으면 확인 요구가 쏟아져 사용자가 다 눌러버린다.
        """
        assert priority("weekly_holiday_day", f(None, Confidence.NOT_FOUND)) != "high"

    def test_reliable_judgment_field_is_medium(self):
        assert priority("work_start_time", f("12:00", Confidence.HIGH)) == "medium"

    @pytest.mark.parametrize("name", sorted(JUDGMENT_FIELDS))
    def test_judgment_fields_always_appear_in_review(self, name):
        fields = {i["field"] for i in build_review_items(make_terms())}
        assert name in fields


class TestBlocking:
    def test_measured_problem_fields_are_exactly_the_blockers(self):
        """실측에서 문제였던 4개가 서명 차단 대상이어야 한다."""
        items = build_review_items(make_terms())
        high = {i["field"] for i in items if i["priority"] == "high"}
        assert high == {
            "wage_amount",              # 0000 (LOW)
            "worker_name",              # 박강헌 (HIGH지만 신원)
            "employer_business_name",   # 신원
            "employer_name",            # 신원
        }

    def test_confirming_removes_from_blockers(self):
        terms = make_terms()
        all_high = [
            i["field"] for i in build_review_items(terms) if i["priority"] == "high"
        ]
        assert unconfirmed_high_priority(terms, set(all_high)) == []

    def test_partial_confirmation_still_blocks(self):
        terms = make_terms()
        remaining = unconfirmed_high_priority(terms, {"wage_amount"})
        assert remaining
        assert "임금 금액" not in remaining


class TestReviewItemShape:
    def test_every_item_has_reason(self):
        for item in build_review_items(make_terms()):
            assert item["reasons"], f"{item['field']} 에 이유가 없다"

    def test_sorted_by_priority(self):
        order = {"high": 0, "medium": 1, "low": 2}
        items = build_review_items(make_terms())
        levels = [order[i["priority"]] for i in items]
        assert levels == sorted(levels)

    def test_flags_are_consistent_with_sets(self):
        for item in build_review_items(make_terms()):
            assert item["affects_judgment"] == (item["field"] in JUDGMENT_FIELDS)
            assert item["printed_on_contract"] == (item["field"] in IDENTITY_FIELDS)
