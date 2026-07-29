"""
입력값 유효성 + 진행 차단 판정 (프론트·백엔드 공통 기준)

--- 왜 별도 모듈인가 ---

rules.py 는 **법정 기준 판정**을 한다. "시급 9,500원 < 최저임금 10,320원".
그런데 시급이 `0000` 이면 rules.py 는 이것도 "최저임금 미달"이라고 말한다.

**0원은 저임금 계약이 아니라 입력 오류다.** 둘을 같은 칸에 넣으면
  · 사용자는 "사장님이 0원 주기로 했나?" 라고 읽는다
  · 고치는 방법도 다르다 (한쪽은 협의, 한쪽은 오타 수정)
  · 무엇보다 **0원짜리 계약서가 생성될 수 있다**

그래서 이 모듈이 값 자체의 유효성을 먼저 본다.

--- 4단계 ---

  error    반드시 수정. 다음 단계·PDF 생성 차단
  warning  확인 권장. 알고 진행 가능
  info     참고
  valid    정상

⚠️ 프론트엔드에 같은 규칙을 복사하지 말 것.
   /contracts/validation-state 로 받아 쓴다. 두 곳에 두면 반드시 어긋난다.
   (실제로 anchor 좌표를 두 파일에 복사했다가 서명 위치가 어긋난 적이 있다)
"""

import re
from dataclasses import dataclass, field as dataclass_field

from app.schemas import CheckStatus, ContractTerms, ValidationReport, WageType

# ------------------------------------------------------------ 유효 범위
#
# app/ai/extract.py 의 상식 검사와 같은 취지지만 역할이 다르다.
#   extract 쪽 : AI가 읽은 값이 이상하면 신뢰도를 낮춘다 (사용자에게 확인 요청)
#   여기       : 확인까지 마친 값이 여전히 이상하면 진행을 막는다
WAGE_RANGES: dict[str, tuple[int, int]] = {
    WageType.HOURLY.value: (1_000, 200_000),
    WageType.DAILY.value: (10_000, 1_000_000),
    WageType.MONTHLY.value: (100_000, 20_000_000),
}
WAGE_RANGE_DEFAULT = (1_000, 20_000_000)

_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

# 계약서에 없으면 계약 자체가 성립하기 어려운 항목.
# 근로기준법 제17조 필수 기재사항 중 우리가 확인할 수 있는 것들.
REQUIRED_FOR_CONTRACT = (
    "contract_start",
    "wage_type",
    "wage_amount",
    "work_start_time",
    "work_end_time",
    "work_days_per_week",
    "worker_name",
    "employer_name",
)

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


@dataclass
class Issue:
    """
    화면에 그대로 뿌릴 수 있는 형태.

    "확인할 항목 5건" 처럼 개수만 주지 않는다.
    어디를, 왜, 어떻게 고쳐야 하는지까지 담는다.
    """

    field: str
    label: str
    severity: str          # error / warning / info
    value: object          # 문제가 된 현재 값
    reason: str            # 왜 문제인가
    fix: str               # 어떻게 고치나
    blocks: bool           # 진행을 막는가
    step: str = "review"   # 어느 단계에서 고치는가
    source: str = "input"  # input(값 자체) / legal(법정 기준)

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "label": self.label,
            "severity": self.severity,
            "value": self.value,
            "reason": self.reason,
            "fix": self.fix,
            "blocks": self.blocks,
            "step": self.step,
            "source": self.source,
        }


def _digits(value) -> str:
    return re.sub(r"[^\d]", "", str(value or ""))


def check_wage_value(terms: ContractTerms) -> Issue | None:
    """
    임금 금액 자체가 계약 조건으로 성립하는가.

    ⚠️ 최저임금 비교와 다르다. 여기는 "값이 값인가"만 본다.
       0원·음수·문자는 협의 대상이 아니라 입력 오류다.
    """
    raw = terms.wage_amount.value
    label = FIELD_LABELS["wage_amount"]

    if raw is None or str(raw).strip() == "":
        return Issue(
            field="wage_amount", label=label, severity="error", value=raw,
            reason="임금이 비어 있습니다.",
            fix="계약서에 적힌 금액을 입력해 주세요.",
            blocks=True,
        )

    text = str(raw).strip()
    if text.startswith("-"):
        return Issue(
            field="wage_amount", label=label, severity="error", value=raw,
            reason="임금이 음수입니다.",
            fix="0보다 큰 금액을 입력해 주세요.",
            blocks=True,
        )

    digits = _digits(text)
    if not digits:
        return Issue(
            field="wage_amount", label=label, severity="error", value=raw,
            reason="임금에서 숫자를 찾을 수 없습니다.",
            fix="'10000' 처럼 숫자로 입력해 주세요.",
            blocks=True,
        )

    amount = int(digits)
    if amount == 0:
        return Issue(
            field="wage_amount", label=label, severity="error", value=raw,
            reason="임금이 0원입니다. 무상 근로 계약은 성립하지 않습니다.",
            fix="계약서에 적힌 실제 금액을 확인해 입력해 주세요.",
            blocks=True,
        )

    wage_type = str(terms.wage_type.value or "")
    low, high = WAGE_RANGES.get(wage_type, WAGE_RANGE_DEFAULT)

    if amount < low:
        return Issue(
            field="wage_amount", label=label, severity="error", value=raw,
            reason=f"임금이 {amount:,}원으로 지나치게 작습니다. 자릿수를 잘못 읽었을 수 있습니다.",
            fix="계약서 원본과 대조해 다시 입력해 주세요.",
            blocks=True,
        )
    if amount > high:
        return Issue(
            field="wage_amount", label=label, severity="warning", value=raw,
            reason=f"임금이 {amount:,}원으로 일반적인 범위를 벗어납니다.",
            fix="임금 형태(시급·일급·월급)가 맞는지 확인해 주세요.",
            blocks=False,
        )
    return None


def check_time_values(terms: ContractTerms) -> list[Issue]:
    """근무·휴게 시각이 HH:MM 형식인가. 형식이 깨지면 근로시간 계산이 전부 틀어진다."""
    issues: list[Issue] = []
    for name in ("work_start_time", "work_end_time", "break_start_time", "break_end_time"):
        value = getattr(terms, name).value
        if value is None or str(value).strip() == "":
            continue
        if not _TIME.match(str(value).strip()):
            required = name in REQUIRED_FOR_CONTRACT
            issues.append(Issue(
                field=name, label=FIELD_LABELS[name],
                severity="error" if required else "warning",
                value=value,
                reason="시각 형식이 아닙니다.",
                fix="'09:00' 처럼 시:분 형식으로 입력해 주세요.",
                blocks=required,
            ))
    return issues


def check_work_days(terms: ContractTerms) -> Issue | None:
    """주 근무일수가 1~7 범위인가."""
    raw = terms.work_days_per_week.value
    if raw is None or str(raw).strip() == "":
        return None
    digits = _digits(raw)
    if not digits or not (1 <= int(digits) <= 7):
        return Issue(
            field="work_days_per_week", label=FIELD_LABELS["work_days_per_week"],
            severity="error", value=raw,
            reason="주 근무일수는 1일에서 7일 사이여야 합니다.",
            fix="계약서의 '매주 ○일 근무' 를 확인해 주세요.",
            blocks=True,
        )
    return None


def check_required(terms: ContractTerms) -> list[Issue]:
    """계약이 성립하려면 있어야 하는 항목이 비어 있는가."""
    issues: list[Issue] = []
    for name in REQUIRED_FOR_CONTRACT:
        value = getattr(terms, name).value
        if value is None or str(value).strip() == "":
            issues.append(Issue(
                field=name, label=FIELD_LABELS[name],
                severity="error", value=None,
                reason="계약서 작성에 반드시 필요한 항목입니다.",
                fix="계약서를 보고 값을 입력해 주세요.",
                blocks=True,
            ))
    return issues


def legal_issues(report: ValidationReport) -> list[Issue]:
    """
    법정 기준 판정을 같은 형태로 변환한다.

    ⚠️ 법정 기준 위반은 **차단하지 않는다.**
       최저임금 미달은 사실이고, 사용자가 알고도 진행할 수 있어야 한다.
       (사장님과 협의 중이거나, 일단 기록으로 남기려는 경우)
       대신 무엇을 무시하고 진행하는지 명확히 보여준다.
    """
    mapping = {
        CheckStatus.VIOLATION: "warning",
        CheckStatus.MISSING: "warning",
        CheckStatus.UNKNOWN: "info",
    }
    issues: list[Issue] = []
    for check in report.checks:
        severity = mapping.get(check.status)
        if severity is None:
            continue
        issues.append(Issue(
            field=check.code.lower(), label=check.label,
            severity=severity, value=check.calculation,
            reason=check.detail or check.calculation or "확인이 필요합니다.",
            fix="사장님과 조건을 조정하거나, 알고도 진행할 수 있습니다.",
            blocks=False,
            step="result",
            source="legal",
        ))
    return issues


@dataclass
class ValidationState:
    issues: list[Issue] = dataclass_field(default_factory=list)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocks]

    @property
    def can_proceed(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        counts = {"error": 0, "warning": 0, "info": 0}
        for issue in self.issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return {
            "can_proceed": self.can_proceed,
            "blocking_fields": [i.field for i in self.blocking],
            "counts": counts,
            "issues": [i.to_dict() for i in self.issues],
        }


def build_validation_state(
    terms: ContractTerms,
    report: ValidationReport | None = None,
) -> ValidationState:
    """
    입력값 유효성 + 법정 기준을 한 번에 본다.

    프론트엔드는 이 결과만 보고 버튼 활성화를 결정하면 된다.
    같은 규칙을 화면에 복사하지 말 것.
    """
    issues: list[Issue] = []

    wage = check_wage_value(terms)
    if wage:
        issues.append(wage)

    days = check_work_days(terms)
    if days:
        issues.append(days)

    issues += check_time_values(terms)

    # 필수 누락은 위에서 이미 다룬 항목과 겹칠 수 있으므로 중복을 제거한다
    seen = {i.field for i in issues}
    issues += [i for i in check_required(terms) if i.field not in seen]

    if report is not None:
        issues += legal_issues(report)

    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], i.field))
    return ValidationState(issues=issues)
