"""계약서 없이 묻는 일반 노동기준 안내.

자유 생성 모델은 법률 상담처럼 보이는 답을 만들 수 있으므로, 확인된 공식 기준만
검색한다. 계약 조건·개근·근로관계 유지가 필요한 지점에서는 계약서 확인으로 전환한다.
"""

import re

from app.schemas import (
    ChatAction,
    ChatEvidence,
    ChatEvidenceKind,
    GeneralQuestionResponse,
)

WEEKLY_HOLIDAY_URL = "https://1350.moel.go.kr/rtmview.do?id=1000059852"
WEEKLY_HOLIDAY_SOURCE = (
    "고용노동부 고객상담센터: 4주 평균 1주 소정근로시간 15시간 이상, "
    "1주 소정근로일 개근 등의 조건을 확인"
)
_HOURS = re.compile(r"(?:주|일주일|1주(?:일)?)\s*(?:에|당)?\s*(\d{1,3})\s*시간|(?:(\d{1,3})\s*시간).*?(?:주|일주일)")

SUGGESTIONS = [
    "1주일에 12시간 일하면 주휴수당을 받나요?",
    "최저임금 기준을 알려주세요.",
    "계약서에서 휴게시간이 안 적혀 있어요.",
]


def _weekly_hours(question: str) -> int | None:
    match = _HOURS.search(question.replace(" ", ""))
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    return int(raw) if raw is not None else None


def _weekly_holiday(question: str) -> GeneralQuestionResponse:
    hours = _weekly_hours(question)
    evidence = [
        ChatEvidence(
            kind=ChatEvidenceKind.LEGAL_STANDARD,
            label="주휴일 기준",
            value=WEEKLY_HOLIDAY_SOURCE,
        )
    ]
    if hours is not None and hours < 15:
        answer = (
            f"입력하신 주 {hours}시간이 매주 약정된 소정근로시간이라면, "
            "주 15시간 미만이어서 주휴일 적용 대상에서 제외됩니다."
        )
    elif hours is not None:
        answer = (
            f"입력하신 주 {hours}시간은 주 15시간 시간 요건은 충족합니다. "
            "다만 실제 주휴일 유급 처리 여부는 약정한 근무일을 모두 출근했는지와 "
            "근로관계가 유지되는지 등을 함께 확인해야 합니다."
        )
    else:
        answer = (
            "주휴일은 일반적으로 4주 평균 1주 소정근로시간이 15시간 이상이고, "
            "약정한 근무일을 모두 출근한 경우에 확인합니다."
        )
    return GeneralQuestionResponse(
        answer=answer,
        limitations=(
            "실제 근무시간이 아니라 계약에서 정한 소정근로시간을 기준으로 보며, "
            "개근·근로관계 유지 등 개별 사실은 이 질문만으로 확인할 수 없습니다."
        ),
        evidence=evidence,
        action=ChatAction(label="계약서로 내 조건 확인하기", href="/upload"),
        suggestions=SUGGESTIONS,
    )


def answer_general_question(question: str) -> GeneralQuestionResponse:
    normalized = question.strip().lower()
    if any(word in normalized for word in ("주휴", "주휴수당", "유급휴일")):
        return _weekly_holiday(normalized)

    return GeneralQuestionResponse(
        answer=(
            "계약서 없이 확인할 수 있는 일반 기준은 현재 주휴일 관련 안내를 지원합니다. "
            "급여·휴게시간·계약 조건은 계약서를 올리면 확인된 내용으로 안내할 수 있습니다."
        ),
        limitations="개별 분쟁, 실제 근무기록, 계약서에 없는 사실은 이 서비스에서 판단하지 않습니다.",
        evidence=[],
        action=ChatAction(label="계약서로 내 조건 확인하기", href="/upload"),
        suggestions=SUGGESTIONS,
    )
