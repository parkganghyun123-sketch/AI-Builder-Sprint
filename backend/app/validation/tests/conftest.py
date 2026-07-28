"""
검증 엔진 테스트 픽스처. 실제 계약서·실제 인물을 절대 사용하지 않는다.
모든 값은 가상 데이터다.
"""

import pytest

from app.schemas import Confidence, ContractTerms, ExtractedField


def field(value, confidence: Confidence = Confidence.HIGH) -> ExtractedField:
    source_text = "테스트 근거" if value is not None else None
    return ExtractedField(value=value, confidence=confidence, source_text=source_text)


def make_terms(**overrides) -> ContractTerms:
    base = dict(
        contract_start=field("2026-08-01"),
        contract_end=field("2027-07-31"),
        workplace=field("서울시 강남구 가상카페"),
        job_description=field("홀 서빙"),
        work_start_time=field("09:00"),
        work_end_time=field("15:00"),
        break_start_time=field("12:00"),
        break_end_time=field("12:30"),
        work_days_per_week=field(5),
        weekly_holiday_day=field("수요일"),
        wage_type=field("HOURLY"),
        wage_amount=field("10320"),
        has_bonus=field("없음"),
        other_allowance=field("없음"),
        payday=field("매월 10일"),
        payment_method=field("계좌이체"),
        employer_business_name=field("가상카페"),
        employer_phone=field("02-0000-0000"),
        employer_address=field("서울시 강남구"),
        employer_name=field("가상 대표"),
        worker_address=field("서울시 서초구"),
        worker_contact=field("010-0000-0000"),
        worker_name=field("가상 근로자"),
    )
    base.update(overrides)
    return ContractTerms(**base)


@pytest.fixture
def terms_factory():
    return make_terms
