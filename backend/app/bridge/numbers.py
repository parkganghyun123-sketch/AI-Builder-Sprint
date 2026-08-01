"""
문장 숫자 검증 (킥 ① 안전장치)

"말 꺼내기" 문구에는 판정 수치가 들어간다.

    "시급이 최저임금(10,320원)이랑 조금 차이가 있어서요"

이 숫자를 LLM이 지어내면 이 프로젝트의 핵심 주장
("판정은 코드가 한다")이 그 자리에서 무너진다.
심사에서 가장 먼저 찔릴 지점이기도 하다.

그래서 생성된 문장의 모든 숫자가 ValidationReport에서 나온 값인지
코드로 대조하고, 아니면 문장을 버린다.

⚠️ 이 모듈은 LLM을 호출하지 않는다. 순수 함수만 둔다.
"""

import re

from app.schemas import ContractTerms, ValidationReport

# 문장에서 숫자를 뽑는다. '10,320' 처럼 쉼표가 섞인 것도 한 덩어리로.
_NUMBER = re.compile(r"\d[\d,]*")

# 검증에서 제외할 숫자.
#
# 한국어 문장에는 판정과 무관한 작은 수가 자연스럽게 섞인다.
#   "한 번 부탁드려도" → 숫자 아님(한글)이라 애초에 안 걸리지만
#   "1~2일" "2주" 같은 표현은 걸린다.
# 0~10은 근거 없이도 통과시킨다. 이 범위로 임금·시간을 위조할 수는 없다.
_TRIVIAL_MAX = 10


def _norm(raw: str) -> str:
    """'10,320' → '10320'. 앞자리 0은 유지한다('09:00'의 09)."""
    return raw.replace(",", "")


def allowed_numbers(
    report: ValidationReport,
    terms: ContractTerms | None = None,
) -> set[str]:
    """
    문장에 등장해도 되는 숫자 집합.

    판정 결과(계산식·조문·연도·금액)와 계약 조건 값에서만 모은다.
    여기 없는 숫자는 어디서도 온 적 없는 숫자다.
    """
    pool: list[str] = []

    for check in report.checks:
        # 계산식·조문·안내문에 들어있는 숫자
        #   '시급 9,500원 < 2026년 최저임금 10,320원'
        #   '근로기준법 제55조'  → 조문 번호도 정당한 숫자다
        for text in (check.calculation, check.legal_basis, check.detail, check.label):
            if text:
                pool += _NUMBER.findall(text)
        pool.append(str(check.standard_year))

    if report.estimated_monthly_pay is not None:
        pool.append(str(report.estimated_monthly_pay))
    if report.wage_shortfall is not None:
        pool.append(str(report.wage_shortfall))

    if terms is not None:
        for field in terms.model_dump().values():
            value = field.get("value") if isinstance(field, dict) else None
            if value is not None:
                pool += _NUMBER.findall(str(value))

    return {_norm(n) for n in pool}


def find_unverified(text: str, allowed: set[str]) -> list[str]:
    """
    문장에서 근거 없는 숫자를 찾는다. 비어 있으면 통과.

    0~10은 통과시킨다(_TRIVIAL_MAX 주석 참고).
    """
    bad: list[str] = []
    for raw in _NUMBER.findall(text):
        value = _norm(raw)
        if value in allowed:
            continue
        try:
            if int(value) <= _TRIVIAL_MAX:
                continue
        except ValueError:
            pass
        bad.append(raw)
    return bad


def verify(
    text: str,
    report: ValidationReport,
    terms: ContractTerms | None = None,
) -> tuple[bool, list[str]]:
    """
    (통과 여부, 근거 없는 숫자 목록)

    사용법 — LLM 문장은 통과했을 때만 쓴다:

        ok, bad = verify(llm_text, report, terms)
        message = llm_text if ok else template_text
    """
    unverified = find_unverified(text, allowed_numbers(report, terms))
    return not unverified, unverified
