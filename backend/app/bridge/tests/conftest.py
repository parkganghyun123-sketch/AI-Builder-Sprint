"""테스트용 가상 계약 조건. 실제 인물이 아니다."""

import pytest

from app.schemas import Confidence, ContractTerms, ExtractedField, WageType


def f(value, conf=Confidence.HIGH) -> ExtractedField:
    return ExtractedField(value=value, confidence=conf)


def make_terms(**overrides) -> ContractTerms:
    """
    기본값은 데모 시나리오와 동일하다.
      시급 10,000원 (2026년 최저임금 10,320원 미달)
      주휴일 미지정
    """
    base = dict(
        contract_start=f("2026년 8월 1일"),
        contract_end=f("2027년 1월 31일"),
        workplace=f("부산광역시 금정구 장전동 카페 000"),
        job_description=f("음료 제조 및 매장 관리"),
        work_start_time=f("09:00"),
        work_end_time=f("16:00"),
        break_start_time=f("12:00"),
        break_end_time=f("12:30"),
        work_days_per_week=f(3),
        weekly_holiday_day=f(None, Confidence.NOT_FOUND),
        wage_type=f(WageType.HOURLY.value),
        wage_amount=f(10000),
        has_bonus=f(False),
        other_allowance=f(None, Confidence.NOT_FOUND),
        payday=f("매월 10일"),
        payment_method=f("근로자 명의 예금통장에 입금"),
        employer_business_name=f("카페 000"),
        employer_phone=f("051-000-0000"),
        employer_address=f("부산광역시 금정구 장전동 00-0"),
        employer_name=f("박정호"),
        worker_address=f("부산광역시 금정구 구서동 00-0"),
        worker_contact=f("010-0000-0000"),
        worker_name=f("김하늘"),
    )
    base.update(overrides)
    return ContractTerms(**base)


@pytest.fixture
def terms() -> ContractTerms:
    return make_terms()


@pytest.fixture
def compliant_terms() -> ContractTerms:
    """위반 없는 계약 — 시급 10,320원, 주휴일 명시."""
    return make_terms(wage_amount=f(10320), weekly_holiday_day=f("일요일"))
