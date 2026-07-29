"""
"말 꺼내기" 문구 확인 (킥 ①)

프론트 없이 터미널에서 문구를 확인한다.
A가 LLM 버전을 얹을 때 여기서 먼저 돌려보고 화면에 붙일 것.

실행:
    cd ~/AI-Builder-Sprint/backend
    python ../spikes/bridge_spike.py              # 기본 시나리오
    python ../spikes/bridge_spike.py --attack     # 환각 차단 확인

--- LLM 버전을 만들 때 ---

    from app.bridge.numbers import verify
    from app.bridge.templates import build_message

    template = build_message(report)          # 항상 안전한 기준선
    llm_text = call_solar(prompt, report)     # A가 구현

    ok, bad = verify(llm_text, report, terms)
    message = llm_text if ok else template    # 실패하면 되돌아간다

⚠️ 검증 실패 시 LLM을 다시 부르지 않는다. 템플릿으로 즉시 대체한다.
   재시도하면 지연이 쌓이고, 어차피 같은 환각이 반복될 수 있다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.bridge.numbers import allowed_numbers, verify  # noqa: E402
from app.bridge.templates import build_message  # noqa: E402
from app.schemas import (  # noqa: E402
    Confidence,
    ContractTerms,
    ExtractedField,
    WageType,
)
from app.validation.rules import validate  # noqa: E402


def f(value, conf=Confidence.HIGH) -> ExtractedField:
    return ExtractedField(value=value, confidence=conf)


def make_terms(**overrides) -> ContractTerms:
    """가상 계약. 시급 10,000원(최저임금 미달) + 주휴일 미지정."""
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


SCENARIOS = {
    "최저임금 미달 + 주휴일 미지정": make_terms(),
    "최저임금 미달만": make_terms(weekly_holiday_day=f("일요일")),
    "위반 없음": make_terms(wage_amount=f(10320), weekly_holiday_day=f("일요일")),
}

# LLM이 낼 법한 환각. 실제로 차단되는지 확인한다.
ATTACKS = [
    "시급이 최저임금 12,500원이랑 차이가 있어서요",
    "월급이 3,200,000원으로 계산되던데요",
    "이건 근로기준법 제999조 위반입니다",
    "차액이 월 250,000원 정도 됩니다",
    "시급이 최저임금 10,320원이랑 차이가 있어서요",
    "확인 한 번 부탁드려요",
]


def show_scenarios() -> None:
    for title, terms in SCENARIOS.items():
        report = validate(terms)
        message = build_message(report)

        print("=" * 64)
        print(f"  {title}")
        print("=" * 64)

        if message is None:
            print("\n  문제 없음 — 말 꺼낼 일이 없다. (message: null)\n")
            continue

        print()
        for line in message.splitlines():
            print(f"  {line}" if line else "")

        ok, bad = verify(message, report, terms)
        print(f"\n  숫자 검증: {'통과' if ok else f'실패 {bad}'}\n")


def show_attacks() -> None:
    terms = make_terms()
    report = validate(terms)

    print("=" * 64)
    print("  환각 차단 확인")
    print("=" * 64)
    print(f"\n  근거 있는 숫자: {sorted(allowed_numbers(report, terms))[:12]} ...\n")

    for text in ATTACKS:
        ok, bad = verify(text, report, terms)
        mark = "통과" if ok else "차단"
        print(f"  [{mark}] {text}")
        if bad:
            print(f"         └ 근거 없는 숫자: {bad}")
    print()


if __name__ == "__main__":
    if "--attack" in sys.argv:
        show_attacks()
    else:
        show_scenarios()
