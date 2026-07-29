"""
"말 꺼내기" 문구 생성 — 템플릿 버전 (킥 ①)

계약서가 최저임금 미달인 걸 *아는 것*과, 열여섯 살이 사장님에게
"이거 최저임금 안 맞는데요"라고 *말하는 것*은 전혀 다른 문제다.
진짜 벽은 탐지가 아니라 대면의 두려움이고, 이 모듈은 그 벽을 낮춘다.

⚠️ 여기서는 LLM을 쓰지 않는다.
   숫자는 전부 ValidationReport에서 그대로 꺼내 쓰므로 환각이 불가능하다.
   LLM 버전(app/bridge/llm.py)은 이 템플릿을 대체하는 게 아니라
   위에 얹는 것이고, 숫자 검증에 실패하면 여기로 되돌아온다.

문구 원칙:
  - 고발이 아니라 문의. 관계를 지키면서 확인을 요청한다.
  - 단정하지 않는다. "틀렸다"가 아니라 "달라서요, 확인 부탁드려요".
  - 사장님도 몰랐을 수 있다는 여지를 남긴다. (킥 ②와 같은 태도)
"""

from app.schemas import CheckResult, CheckStatus, ValidationReport

# 인사와 맺음말. 본문 사이에 끼워 하나의 메시지로 만든다.
OPENING = "사장님, 안녕하세요. 계약서 다시 보다가 몇 가지 여쭤보고 싶은 게 있어서요."
OPENING_SINGLE = "사장님, 안녕하세요. 계약서 다시 보다가 여쭤보고 싶은 게 있어서요."
CLOSING = "제가 잘못 본 것일 수도 있어서 확인 한 번 부탁드려요. 감사합니다."


def _amount(text: str | None, keyword: str) -> str | None:
    """계산식에서 특정 키워드 뒤 금액을 꺼낸다. 못 찾으면 None."""
    if not text or keyword not in text:
        return None
    tail = text.split(keyword, 1)[1]
    digits = ""
    for ch in tail:
        if ch.isdigit() or ch == ",":
            digits += ch
        elif digits:
            break
    return digits or None


def _minimum_wage_line(check: CheckResult) -> str:
    """
    최저임금 미달.
    계산식이 '시급 9,500원 < 2026년 최저임금 10,320원' 형태다.
    """
    mine = _amount(check.calculation, "시급")
    legal = _amount(check.calculation, "최저임금")

    if mine and legal:
        return (
            f"계약서에 적힌 시급이 {mine}원인데, "
            f"올해 최저임금이 {legal}원이라고 해서요. "
            "혹시 제가 잘못 본 걸까요?"
        )
    return "계약서에 적힌 시급이 올해 최저임금과 차이가 있는 것 같아서요."


def _weekly_holiday_line(check: CheckResult) -> str:
    """주휴일 미기재 또는 주휴 시간 요건."""
    if check.status == CheckStatus.MISSING:
        return (
            "계약서에 주휴일이 어느 요일인지 안 적혀 있더라고요. "
            "혹시 정해진 요일이 있으면 알려주실 수 있을까요?"
        )
    return "주휴일 관련해서 계약서 내용을 한 번 더 확인해주실 수 있을까요?"


def _break_time_line(check: CheckResult) -> str:
    """휴게시간 부족 또는 미기재."""
    if check.status == CheckStatus.MISSING:
        return (
            "계약서에 휴게시간이 안 적혀 있는 것 같아서요. "
            "쉬는 시간은 어떻게 되는지 여쭤봐도 될까요?"
        )
    if check.calculation:
        return (
            f"휴게시간이 근무시간에 비해 조금 짧은 것 같아서요 ({check.calculation}). "
            "확인 부탁드려도 될까요?"
        )
    return "휴게시간 부분을 한 번 확인해주실 수 있을까요?"


def _minor_hours_line(check: CheckResult) -> str:
    """만 18세 미만 근로시간 초과. (B가 규칙 추가 후 연결)"""
    return (
        "제가 만 18세 미만이라 근로시간에 별도 기준이 있다고 하더라고요. "
        f"{check.calculation or '계약서 근무시간'} 부분을 "
        "한 번 확인해주실 수 있을까요?"
    )


def _minor_night_line(check: CheckResult) -> str:
    """만 18세 미만 야간근로."""
    return (
        "제가 만 18세 미만이라 밤 10시 이후 근무는 따로 절차가 필요하다고 해서요. "
        "근무 시간대를 한 번 여쭤봐도 될까요?"
    )


def _missing_field_line(check: CheckResult) -> str:
    """필수 기재사항 누락."""
    return (
        f"계약서에 {check.label} 부분이 비어 있는 것 같아서요. "
        "채워주실 수 있을까요?"
    )


# 판정 코드 → 문구 생성기
_LINE_BUILDERS = {
    "MINIMUM_WAGE": _minimum_wage_line,
    "WEEKLY_HOLIDAY": _weekly_holiday_line,
    "BREAK_TIME": _break_time_line,
    "MINOR_WORKING_HOURS": _minor_hours_line,
    "MINOR_NIGHT_WORK": _minor_night_line,
}


def build_lines(report: ValidationReport) -> list[str]:
    """문제 항목별 문장. 판정 결과에서만 값을 꺼낸다."""
    lines: list[str] = []
    for check in report.checks:
        if check.status not in (CheckStatus.VIOLATION, CheckStatus.MISSING):
            continue
        builder = _LINE_BUILDERS.get(check.code, _missing_field_line)
        lines.append(builder(check))
    return lines


def build_message(report: ValidationReport) -> str | None:
    """
    사장님께 보낼 메시지 전문. 문제가 없으면 None.

    ⚠️ 숫자는 전부 report에서 꺼내므로 app.bridge.numbers.verify 를
       항상 통과한다. LLM 버전이 검증에 실패했을 때의 대체 문구이기도 하다.
    """
    lines = build_lines(report)
    if not lines:
        return None

    opening = OPENING if len(lines) > 1 else OPENING_SINGLE
    body = "\n\n".join(f"- {line}" for line in lines) if len(lines) > 1 else lines[0]

    return f"{opening}\n\n{body}\n\n{CLOSING}"
