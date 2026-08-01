"""질문 원문에서 외부 전송이 안전한 폐쇄형 특징만 추출한다."""

from enum import Enum

from pydantic import BaseModel

from app.chat.models import ChatTopic, Classification


class QuerySignal(str, Enum):
    AMOUNT = "AMOUNT"
    DATE = "DATE"
    REQUIREMENT = "REQUIREMENT"
    ELIGIBILITY = "ELIGIBILITY"
    MISSING = "MISSING"


class SafeQuestionFeatures(BaseModel):
    """이 모델의 enum 값만 제공자에 전송할 수 있다."""

    topics: list[ChatTopic]
    signals: list[QuerySignal]


_TOPIC_KEYWORDS: tuple[tuple[ChatTopic, tuple[str, ...]], ...] = (
    (ChatTopic.WEEKLY_HOLIDAY, ("주휴",)),
    (ChatTopic.SEVERANCE_PAY, ("퇴직금", "퇴직급여")),
    (ChatTopic.SOCIAL_INSURANCE, ("4대보험", "사대보험", "사회보험")),
    (ChatTopic.ANNUAL_LEAVE, ("연차", "연차휴가")),
    (ChatTopic.DISMISSAL_NOTICE, ("해고예고수당", "해고예고")),
    (ChatTopic.PROBATION_MINIMUM_WAGE, ("수습최저임금", "수습시급", "수습기간시급")),
    (ChatTopic.MINIMUM_WAGE, ("최저임금", "최저시급")),
    (ChatTopic.BREAK_TIME, ("휴게", "쉬는시간")),
    (ChatTopic.PAYDAY, ("급여일", "월급날", "임금지급일")),
    (ChatTopic.CONTRACT_PERIOD, ("계약기간", "근로계약기간")),
    (ChatTopic.WORKPLACE, ("근무장소", "일하는곳", "근무지")),
    (ChatTopic.JOB, ("업무내용", "무슨일", "담당업무")),
    (ChatTopic.MISSING_CLAUSES, ("빠진", "누락", "조항")),
    (ChatTopic.WORKING_HOURS, ("근로시간", "근무시간")),
    (ChatTopic.WAGE, ("시급", "임금", "급여", "월급")),
)

_SIGNAL_KEYWORDS: tuple[tuple[QuerySignal, tuple[str, ...]], ...] = (
    (QuerySignal.AMOUNT, ("얼마", "금액")),
    (QuerySignal.DATE, ("언제", "날짜")),
    (QuerySignal.REQUIREMENT, ("요건", "기준")),
    (QuerySignal.ELIGIBILITY, ("받을수", "해당", "충족", "적나요", "맞나요")),
    (QuerySignal.MISSING, ("빠진", "누락", "조항")),
)


def extract_safe_features(question: str) -> SafeQuestionFeatures | None:
    """이름·연락처·자유 문장은 버리고 닫힌 enum 특징만 반환한다."""

    normalized = "".join(question.lower().split())
    topics = [
        topic
        for topic, keywords in _TOPIC_KEYWORDS
        if any(keyword in normalized for keyword in keywords)
    ]
    if "수습기간" in normalized and any(
        keyword in normalized for keyword in ("최저임금", "최저시급")
    ):
        topics.append(ChatTopic.PROBATION_MINIMUM_WAGE)
    if ChatTopic.PROBATION_MINIMUM_WAGE in topics:
        topics = [
            topic
            for topic in topics
            if topic not in (ChatTopic.MINIMUM_WAGE, ChatTopic.WAGE)
        ]
    if ChatTopic.MINIMUM_WAGE in topics and ChatTopic.WAGE in topics:
        topics.remove(ChatTopic.WAGE)
    if not topics:
        return None
    signals = [
        signal
        for signal, keywords in _SIGNAL_KEYWORDS
        if any(keyword in normalized for keyword in keywords)
    ]
    return SafeQuestionFeatures(topics=topics, signals=signals)


def classification_is_consistent(
    classification: Classification,
    features: SafeQuestionFeatures,
) -> bool:
    """Solar가 로컬에서 허용한 주제 밖으로 라우팅하면 거절한다."""

    return classification.topic in features.topics
