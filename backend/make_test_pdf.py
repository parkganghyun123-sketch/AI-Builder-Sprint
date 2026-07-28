"""
테스트용 계약서 PDF 생성 (Day 1 스파이크)

실행:
    cd backend
    python make_test_pdf.py

결과:
    ../spikes/sample_contract.pdf
    → 이 파일로 modusign_spike.py send 를 돌린다.
"""

import logging
from pathlib import Path

# WeasyPrint가 PDF를 만들 때마다 fontTools가 글리프 목록을 수백 줄 쏟아낸다.
# import 전에 눌러둔다.
for _noisy in ("fontTools", "weasyprint", "PIL"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from app.pdf.generator import render_contract_pdf, verify_anchors  # noqa: E402
from app.schemas import Confidence, ContractTerms, ExtractedField, WageType


def f(value, conf=Confidence.HIGH, source=None) -> ExtractedField:
    return ExtractedField(value=value, confidence=conf, source_text=source)


# 데모 시나리오와 동일한 가상 계약
#   - 시급 10,000원 → 2026년 최저임금 10,320원 미달
#   - 주휴일 미지정 → 누락
#   - 09:00~16:00 중 휴게 30분 → 1일 6.5시간, 주 3일 = 19.5시간 (15시간 이상)
SAMPLE = ContractTerms(
    contract_start=f("2026년 8월 1일"),
    contract_end=f("2027년 1월 31일"),
    workplace=f("부산광역시 금정구 장전동 카페 000"),
    job_description=f("음료 제조 및 매장 관리"),
    work_start_time=f("09:00", source="09시 00분부터"),
    work_end_time=f("16:00", source="16시 00분까지"),
    break_start_time=f("12:00"),
    break_end_time=f("12:30", source="휴게시간 12시~12시30분"),
    work_days_per_week=f(3),
    weekly_holiday_day=f(None, Confidence.NOT_FOUND),  # 주휴일 미지정
    wage_type=f(WageType.HOURLY.value),
    wage_amount=f(10000, source="시간급 금 10,000원"),
    has_bonus=f(False),
    other_allowance=f(None, Confidence.NOT_FOUND),
    payday=f("10"),
    payment_method=f("근로자 명의 예금통장에 입금"),
    employer_business_name=f("카페 000"),
    employer_phone=f("051-000-0000"),
    employer_address=f("부산광역시 금정구 장전동 00-0"),
    employer_name=f("박정호"),
    worker_address=f("부산광역시 금정구 구서동 00-0"),
    worker_contact=f("010-0000-0000"),
    worker_name=f("김하늘"),
)


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "spikes" / "sample_contract.pdf"
    out.parent.mkdir(exist_ok=True)

    pdf = render_contract_pdf(SAMPLE)
    out.write_bytes(pdf)

    print(f"✅ 생성 완료: {out}  ({len(pdf):,} bytes)")

    # 파생값 확인 — 검증 엔진(B)이 이 값을 쓴다
    print("\n계산된 파생값 (코드가 계산, LLM 아님)")
    print(f"  1일 소정근로시간 : {SAMPLE.hours_per_day} 시간")
    print(f"  휴게시간         : {SAMPLE.break_minutes} 분")
    print(f"  주 소정근로시간  : {SAMPLE.weekly_hours} 시간")
    print(f"  시간급           : {SAMPLE.hourly_wage} 원")

    print("\nanchor 텍스트 (참고용 — PDF 압축 때문에 ?여도 실패는 아님)")
    for text, found in verify_anchors(pdf).items():
        print(f"  {'○' if found else '?'} {text}")

    print("\n다음 단계:")
    print("  1. PDF를 열어 한글이 안 깨졌는지, '근로자 서명'/'사업주 서명'이 보이는지 확인")
    print("  2. cd .. && python3 spikes/modusign_spike.py send")
