"""계약서 없이 묻는 일반 노동기준 안내.

질문을 검증된 지식 범주로만 라우팅하고 결정론적 문장으로 답한다. 이전 응답의
주제 코드를 함께 받으면 "그럼 6시간은?" 같은 후속 질문도 같은 기준으로 처리한다.
"""

import re

from app.schemas import (
    ChatAction,
    ChatEvidence,
    ChatEvidenceKind,
    GeneralQuestionResponse,
    GeneralQuestionTopic,
)

WEEKLY_HOLIDAY_URL = "https://1350.moel.go.kr/rtmview.do?id=1000059852"
MINIMUM_WAGE_URL = "https://www.minimumwage.go.kr/minWage/policy/decisionMain.do"
LABOR_STANDARDS_ACT_URL = "https://www.law.go.kr/LSW/lsInfoP.do?lsId=001872"
CONTRACT_FORM_URL = (
    "https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230700845"
)
UNDER_FIVE_URL = "https://1350.moel.go.kr/rtmview.do?id=1000000868"
GUIDANCE_URL = "https://1350.moel.go.kr/"

MINIMUM_WAGE_2026 = 10_320

SUGGESTIONS = [
    "1주일에 12시간 일하면 주휴수당을 받나요?",
    "최저임금 기준을 알려주세요.",
    "6시간 일하면 휴게시간은 얼마나 필요한가요?",
    "근로계약서를 꼭 받아야 하나요?",
    "17살인데 밤 10시 이후에 일해도 되나요?",
    "야간근로 수당 기준을 알려주세요.",
]

_HOURS = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*시간")
_MONEY = re.compile(r"([0-9][0-9,]{3,})\s*원")
_AGE = re.compile(r"(?:만\s*)?(\d{1,2})\s*(?:살|세)")

_OUT_OF_SCOPE_WORDS = (
    "해고",
    "신고",
    "고소",
    "소송",
    "처벌",
    "합의금",
    "부당해고",
    "직장 내 괴롭힘",
    "임금체불 신고",
)


def _evidence(label: str, value: str, url: str) -> ChatEvidence:
    return ChatEvidence(
        kind=ChatEvidenceKind.LEGAL_STANDARD,
        label=label,
        value=value,
        url=url,
    )


def _upload_action(label: str = "계약서로 내 조건 확인하기") -> ChatAction:
    return ChatAction(label=label, href="/upload")


def _hours(question: str) -> float | None:
    match = _HOURS.search(question.replace(",", ""))
    return float(match.group(1)) if match else None


def _money(question: str) -> int | None:
    match = _MONEY.search(question)
    return int(match.group(1).replace(",", "")) if match else None


def _age(question: str) -> int | None:
    match = _AGE.search(question)
    return int(match.group(1)) if match else None


def _classify(
    question: str,
    context: GeneralQuestionTopic | None,
) -> GeneralQuestionTopic:
    if any(word in question for word in _OUT_OF_SCOPE_WORDS):
        return GeneralQuestionTopic.OUT_OF_SCOPE
    if any(word in question for word in ("최저임금", "최저 시급", "최저시급")):
        return GeneralQuestionTopic.MINIMUM_WAGE
    if any(word in question for word in ("주휴", "주휴수당", "유급휴일")):
        return GeneralQuestionTopic.WEEKLY_HOLIDAY
    if any(word in question for word in ("휴게", "쉬는 시간", "쉬는시간")):
        return GeneralQuestionTopic.BREAK_TIME
    if any(
        word in question
        for word in ("미성년", "청소년", "17살", "17세", "16살", "16세")
    ):
        return GeneralQuestionTopic.MINOR_WORK
    if any(
        word in question
        for word in ("야간근로", "연장근로", "휴일근로", "가산수당", "밤 10시")
    ):
        return GeneralQuestionTopic.EXTRA_WORK
    if any(
        word in question
        for word in ("근로계약서", "계약서를", "서면 교부", "필수 기재")
    ):
        return GeneralQuestionTopic.WRITTEN_CONTRACT
    if context is not None and context != GeneralQuestionTopic.OUT_OF_SCOPE:
        return context
    return GeneralQuestionTopic.OUT_OF_SCOPE


def _weekly_holiday(question: str) -> GeneralQuestionResponse:
    hours = _hours(question)
    if hours is not None and hours < 15:
        answer = (
            f"입력하신 주 {hours:g}시간이 4주 평균 소정근로시간이라면, "
            "주 15시간 미만이어서 주휴일 적용 대상에서 제외됩니다."
        )
    elif hours is not None:
        answer = (
            f"입력하신 주 {hours:g}시간은 주 15시간 시간 요건은 충족합니다. "
            "다만 약정한 근무일의 개근과 근로관계 유지도 확인해야 합니다."
        )
    else:
        answer = (
            "주휴일은 일반적으로 4주 평균 1주 소정근로시간이 15시간 이상이고, "
            "약정한 근무일을 모두 출근한 경우에 확인합니다."
        )
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.WEEKLY_HOLIDAY,
        answer=answer,
        limitations=(
            "실제 근무시간이 아니라 계약에서 정한 소정근로시간을 기준으로 보며, "
            "개근·근로관계 유지 여부는 이 질문만으로 확인할 수 없습니다."
        ),
        evidence=[
            _evidence(
                "주휴일 기준",
                "근로기준법 제18조·제55조 · 4주 평균 주 15시간 기준",
                WEEKLY_HOLIDAY_URL,
            )
        ],
        action=_upload_action(),
        suggestions=SUGGESTIONS,
    )


def _minimum_wage(question: str) -> GeneralQuestionResponse:
    amount = _money(question)
    if amount is None:
        answer = (
            "2026년 적용 최저임금은 시간급 10,320원입니다. 일급은 8시간 기준 "
            "82,560원, 월 환산액은 주 40시간·월 209시간 기준 2,156,880원입니다."
        )
    elif amount < MINIMUM_WAGE_2026:
        shortfall = MINIMUM_WAGE_2026 - amount
        answer = (
            f"입력하신 {amount:,}원이 시간급이라면 2026년 최저임금 "
            f"10,320원보다 {shortfall:,}원 낮습니다."
        )
    else:
        answer = (
            f"입력하신 {amount:,}원이 시간급이라면 2026년 최저임금 "
            "10,320원보다 낮지는 않습니다."
        )
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.MINIMUM_WAGE,
        answer=answer,
        limitations=(
            "월급·일급 비교는 소정근로시간과 최저임금에 산입되는 임금 항목을 "
            "함께 확인해야 하므로 계약서 없이 단정할 수 없습니다."
        ),
        evidence=[
            _evidence(
                "2026년 최저임금",
                "시간급 10,320원 · 일급 82,560원 · 월 환산액 2,156,880원",
                MINIMUM_WAGE_URL,
            )
        ],
        action=_upload_action("계약서로 내 임금 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _break_time(question: str) -> GeneralQuestionResponse:
    hours = _hours(question)
    if hours is None:
        answer = (
            "현행 기준은 근로시간 4시간에 30분 이상, 8시간에 1시간 이상의 "
            "휴게를 근로시간 도중에 부여하고 자유롭게 이용할 수 있게 하는 것입니다."
        )
    elif hours >= 8:
        answer = f"{hours:g}시간 근로라면 1시간 이상의 휴게가 필요합니다."
    elif hours >= 4:
        answer = f"{hours:g}시간 근로라면 30분 이상의 휴게가 필요합니다."
    else:
        answer = (
            f"{hours:g}시간 근로는 근로기준법 제54조의 4시간 기준에는 "
            "도달하지 않습니다. 다만 계약이나 사업장 규정으로 휴게를 정할 수 있습니다."
        )
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.BREAK_TIME,
        answer=answer,
        limitations=(
            "계약서에 기재가 없다는 사실만으로 실제 휴게 부여 여부나 법 위반을 "
            "확정할 수 없습니다. 실제로 자유롭게 이용한 휴게인지도 확인해야 합니다."
        ),
        evidence=[
            _evidence(
                "휴게시간 기준",
                "근로기준법 제54조 · 4시간에 30분 이상, 8시간에 1시간 이상",
                LABOR_STANDARDS_ACT_URL,
            )
        ],
        action=_upload_action("계약서로 휴게시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _written_contract() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.WRITTEN_CONTRACT,
        answer=(
            "사용자는 임금, 소정근로시간, 휴일, 연차 유급휴가 등 주요 근로조건을 "
            "명시하고 서면으로 근로자에게 교부해야 합니다. 표준근로계약서에서는 "
            "계약기간, 근무장소, 업무 내용, 근로시간, 근무일·휴일, 임금도 확인합니다."
        ),
        limitations=(
            "계약서를 받지 못한 구체적인 경위나 이미 합의한 내용의 효력은 이 "
            "서비스에서 판단하지 않습니다. 1350 또는 전문가에게 확인해 주세요."
        ),
        evidence=[
            _evidence(
                "서면 명시·교부",
                "근로기준법 제17조 · 고용노동부 표준근로계약서",
                CONTRACT_FORM_URL,
            )
        ],
        action=_upload_action("받은 계약서 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _minor_work(question: str) -> GeneralQuestionResponse:
    age = _age(question)
    if age is not None and age >= 18:
        answer = (
            f"만 {age}세라면 근로기준법의 18세 미만자 특별 근로시간 제한은 "
            "적용되지 않습니다. 일반 근로시간 기준은 별도로 확인해야 합니다."
        )
    elif age is not None and 15 <= age < 18:
        answer = (
            f"만 {age}세는 원칙적으로 1일 7시간·1주 35시간을 초과해 일할 수 "
            "없습니다. 합의가 있어도 1일 1시간·1주 5시간 범위의 연장 한도가 있고, "
            "22시부터 06시까지의 야간근로와 휴일근로에는 별도 제한이 있습니다."
        )
    elif age is not None:
        answer = (
            f"만 {age}세의 취업에는 취직인허증 등 추가 요건이 관련될 수 있어 이 "
            "서비스의 검증 범위를 벗어납니다. 고용노동부 1350에 확인해 주세요."
        )
    else:
        answer = (
            "15세 이상 18세 미만 근로자는 원칙적으로 1일 7시간·1주 35시간 "
            "한도가 적용되며, 22시부터 06시까지의 야간근로와 휴일근로에는 별도 "
            "제한이 있습니다."
        )
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.MINOR_WORK,
        answer=answer,
        limitations=(
            "나이, 계약기간, 실제 근무시각과 고용노동부장관 인가 여부 등에 따라 "
            "달라질 수 있으므로 개인별 허용 여부를 단정하지 않습니다."
        ),
        evidence=[
            _evidence(
                "18세 미만 근로시간",
                "근로기준법 제69조·제70조 · 1일 7시간, 1주 35시간",
                LABOR_STANDARDS_ACT_URL,
            )
        ],
        action=_upload_action("계약서 근무시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _extra_work() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.EXTRA_WORK,
        answer=(
            "근로기준법 제56조는 연장·야간·휴일근로의 가산임금을 규정하고, "
            "야간근로는 22시부터 06시까지의 근로를 말합니다."
        ),
        limitations=(
            "상시 근로자 수, 실제 근무시각, 휴일 여부와 합의 내용에 따라 적용이 "
            "달라집니다. 특히 5인 미만 사업장은 적용 규정이 다를 수 있어 계약서와 "
            "사업장 정보를 확인하기 전에는 지급 여부나 금액을 계산하지 않습니다."
        ),
        evidence=[
            _evidence(
                "가산임금 기준",
                "근로기준법 제56조 · 연장·야간·휴일근로",
                LABOR_STANDARDS_ACT_URL,
            ),
            _evidence(
                "사업장 규모",
                "고용노동부 1350 · 5인 미만 사업장 적용 범위 확인 필요",
                UNDER_FIVE_URL,
            ),
        ],
        action=_upload_action("계약서 근무시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _out_of_scope() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.OUT_OF_SCOPE,
        answer=(
            "이 질문은 일반 기준만으로 판단할 수 없습니다. 개별 사실관계에 따라 "
            "답이 달라질 수 있어 고용노동부 고객상담센터 1350 또는 전문가에게 "
            "확인해 주세요."
        ),
        limitations=(
            "해고·신고·분쟁의 결론, 실제 근무기록과 당사자 진술이 필요한 판단은 "
            "지원하지 않습니다."
        ),
        evidence=[
            ChatEvidence(
                kind=ChatEvidenceKind.OFFICIAL_GUIDANCE,
                label="공식 상담 안내",
                value="고용노동부 고객상담센터 1350",
                url=GUIDANCE_URL,
            )
        ],
        action=_upload_action(),
        suggestions=SUGGESTIONS,
    )


_HANDLERS = {
    GeneralQuestionTopic.WEEKLY_HOLIDAY: _weekly_holiday,
    GeneralQuestionTopic.MINIMUM_WAGE: _minimum_wage,
    GeneralQuestionTopic.BREAK_TIME: _break_time,
    GeneralQuestionTopic.WRITTEN_CONTRACT: lambda _: _written_contract(),
    GeneralQuestionTopic.MINOR_WORK: _minor_work,
    GeneralQuestionTopic.EXTRA_WORK: lambda _: _extra_work(),
    GeneralQuestionTopic.OUT_OF_SCOPE: lambda _: _out_of_scope(),
}


def answer_general_question(
    question: str,
    context: GeneralQuestionTopic | None = None,
) -> GeneralQuestionResponse:
    normalized = question.strip().lower()
    topic = _classify(normalized, context)
    return _HANDLERS[topic](normalized)
