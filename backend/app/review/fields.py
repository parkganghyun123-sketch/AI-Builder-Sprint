"""
확인이 필요한 항목 판별 (C 담당)

AI가 읽은 값을 그대로 판정에 쓰지 않는다. 사용자가 확인·수정한 값으로 판정한다.
이 모듈은 "무엇을 반드시 확인받아야 하는가"를 코드로 정한다.

--- 왜 필요한가 (실측 근거) ---

손글씨 계약서 1장, 3회 반복 (spikes/fixtures/handwritten_01.png):

  wage_amount   '10 000' → '0000'   판정에 쓰이는 값이 틀림. LOW로 표시됨
  wage_type     2/3 회 NOT_FOUND    임금 형태를 못 읽음
  worker_name   '박강현' → '박강헌'   자신 있게(HIGH) 틀림. 계약서에 그대로 찍힘

앞의 둘은 신뢰도로 걸러진다. 세 번째는 걸러지지 않는다 —
값이 상식적이라 코드가 이상하다고 판단할 근거가 없다.

그래서 기준을 셋으로 둔다.
  1. 신뢰도가 낮거나 못 읽은 항목      → 값 자체가 의심스럽다
  2. 판정에 쓰이는 항목                → 틀리면 판정이 틀린다
  3. 계약서에 찍히는 신원 정보          → 틀리면 남의 이름으로 서명한다

⚠️ 손글씨는 source_text 도 AI가 읽은 결과다.
   '박강헌'이 틀렸는데 근거도 '박강헌'으로 나오면 확인이 불가능하다.
   화면에서는 원본 사진을 함께 보여줘야 한다. (D 담당)
"""

from app.schemas import Confidence, ContractTerms

# 판정에 직접 쓰이는 항목. 틀리면 판정 결과가 틀린다.
#
# app/validation/rules.py 의 검사들이 실제로 읽는 필드다.
#   최저임금  ← wage_type, wage_amount
#   주휴      ← 근무 시각, 주 근무일수, 주휴일
#   휴게      ← 근무 시각, 휴게 시각
JUDGMENT_FIELDS = frozenset({
    "wage_type",
    "wage_amount",
    "work_start_time",
    "work_end_time",
    "break_start_time",
    "break_end_time",
    "work_days_per_week",
    "weekly_holiday_day",
})

# 계약서에 그대로 인쇄되어 법적 효력을 갖는 신원 정보.
# 판정에는 안 쓰이지만 틀리면 잘못된 계약서에 서명하게 된다.
IDENTITY_FIELDS = frozenset({
    "worker_name",
    "employer_name",
    "employer_business_name",
})

# 사람이 읽을 항목 이름
FIELD_LABELS: dict[str, str] = {
    "contract_start": "계약 시작일",
    "contract_end": "계약 종료일",
    "workplace": "근무장소",
    "job_description": "업무의 내용",
    "work_start_time": "출근 시각",
    "work_end_time": "퇴근 시각",
    "break_start_time": "휴게 시작",
    "break_end_time": "휴게 종료",
    "work_days_per_week": "주 근무일수",
    "weekly_holiday_day": "주휴일",
    "wage_type": "임금 형태",
    "wage_amount": "임금 금액",
    "has_bonus": "상여금",
    "other_allowance": "기타 수당",
    "payday": "임금 지급일",
    "payment_method": "임금 지급방법",
    "employer_business_name": "사업체명",
    "employer_phone": "사업주 전화",
    "employer_address": "사업체 주소",
    "employer_name": "대표자",
    "worker_address": "근로자 주소",
    "worker_contact": "근로자 연락처",
    "worker_name": "근로자 성명",
}


def review_reasons(name: str, field) -> list[str]:
    """이 항목을 확인받아야 하는 이유. 비어 있으면 확인 불필요."""
    reasons: list[str] = []

    if field.confidence == Confidence.NOT_FOUND:
        reasons.append("계약서에서 값을 찾지 못했습니다")
    elif field.confidence == Confidence.LOW:
        reasons.append("읽은 값이 정확한지 확신할 수 없습니다")

    if name in JUDGMENT_FIELDS:
        reasons.append("법정 기준 판정에 사용되는 항목입니다")
    if name in IDENTITY_FIELDS:
        reasons.append("계약서에 그대로 기재되는 항목입니다")

    # 판정·신원 항목이 아니고 신뢰도도 정상이면 확인 불필요
    if name not in JUDGMENT_FIELDS and name not in IDENTITY_FIELDS:
        return [] if not reasons else reasons

    return reasons


def priority(name: str, field) -> str:
    """
    확인 우선순위.

      high    반드시 확인. 확인 전에는 서명 요청이 막힌다
      medium  보여주되 막지는 않는다
      low     그 외

    --- 기준을 이렇게 잡은 이유 ---

    신원 정보는 신뢰도로 걸러지지 않는다.
      실측에서 '박강현' → '박강헌' 이 confidence HIGH 로 나왔다.
      값이 상식적이라 코드가 이상하다고 판단할 근거가 없다.
      사람이 보는 것 말고는 방법이 없으므로 **항상** high 다.

    값이 있는데 신뢰도가 낮은 판정 항목이 가장 위험하다.
      '0000'(시급) 처럼 틀린 값으로 판정이 돌아가면 결과가 뒤집힌다.

    값을 못 찾은 판정 항목은 high 가 아니다.
      판정이 이미 '누락'으로 잡아 사용자에게 보여준다.
      여기까지 막으면 빈칸 많은 계약서에서 확인 요구가 쏟아져
      사용자가 아무 생각 없이 다 눌러버린다 — 관문이 무력해진다.
    """
    if name in IDENTITY_FIELDS:
        return "high"

    if name in JUDGMENT_FIELDS and field.confidence == Confidence.LOW:
        return "high"

    if name in JUDGMENT_FIELDS or field.confidence in (
        Confidence.LOW,
        Confidence.NOT_FOUND,
    ):
        return "medium"

    return "low"


def build_review_items(terms: ContractTerms) -> list[dict]:
    """
    확인이 필요한 항목 목록. 우선순위 높은 순.

    프론트는 이 목록만 보고 화면을 구성하면 된다.
    confidence 를 직접 해석할 필요가 없다.
    """
    items: list[dict] = []
    dumped = terms.model_dump()

    for name in FIELD_LABELS:
        field = getattr(terms, name, None)
        if field is None:
            continue

        reasons = review_reasons(name, field)
        if not reasons:
            continue

        items.append({
            "field": name,
            "label": FIELD_LABELS[name],
            "value": dumped[name].get("value"),
            "confidence": field.confidence.value,
            "source_text": dumped[name].get("source_text"),
            "priority": priority(name, field),
            "reasons": reasons,
            "affects_judgment": name in JUDGMENT_FIELDS,
            "printed_on_contract": name in IDENTITY_FIELDS,
        })

    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: (order[i["priority"]], i["field"]))
    return items


def unconfirmed_high_priority(
    terms: ContractTerms,
    confirmed: set[str],
) -> list[str]:
    """
    확인받아야 하는데 아직 확인 안 된 항목.

    서명 요청을 막는 기준으로 쓴다. high 만 막는다 —
    medium 까지 막으면 거의 모든 계약이 막혀 기능이 무력해진다.
    """
    return [
        item["label"]
        for item in build_review_items(terms)
        if item["priority"] == "high" and item["field"] not in confirmed
    ]
