"""허용 목록 기반의 짧은 일상대화 분류와 결정론적 답변."""

import re
import unicodedata
from enum import Enum


class SmallTalkKind(str, Enum):
    GREETING = "GREETING"
    THANKS = "THANKS"
    GOODBYE = "GOODBYE"
    IDENTITY = "IDENTITY"
    CAPABILITIES = "CAPABILITIES"
    MOOD = "MOOD"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


SMALL_TALK_SUGGESTIONS = [
    "1주일에 12시간 일하면 주휴수당을 받나요?",
    "2026년 최저임금은 얼마인가요?",
    "6시간 일하면 휴게시간은 얼마나 필요한가요?",
]

_PHRASES: tuple[tuple[SmallTalkKind, frozenset[str]], ...] = (
    (
        SmallTalkKind.GREETING,
        frozenset(
            {
                "안녕",
                "안녕하세요",
                "안녕하십니까",
                "반가워",
                "반가워요",
                "반갑습니다",
                "하이",
                "헬로",
                "좋은아침",
                "좋은저녁",
            }
        ),
    ),
    (
        SmallTalkKind.THANKS,
        frozenset({"고마워", "고마워요", "감사", "감사해요", "감사합니다", "땡큐"}),
    ),
    (
        SmallTalkKind.GOODBYE,
        frozenset({"잘가", "잘가요", "안녕히계세요", "다음에봐", "또보자", "바이"}),
    ),
    (
        SmallTalkKind.IDENTITY,
        frozenset(
            {
                "너는누구야",
                "누구야",
                "정체가뭐야",
                "이름이뭐야",
                "무슨챗봇이야",
            }
        ),
    ),
    (
        SmallTalkKind.CAPABILITIES,
        frozenset(
            {
                "뭘물어볼수있어",
                "뭐물어볼수있어",
                "무엇을물어볼수있어",
                "뭘할수있어",
                "뭐할수있어",
                "사용법알려줘",
                "어떻게사용해",
            }
        ),
    ),
    (
        SmallTalkKind.MOOD,
        frozenset(
            {
                "기분어때",
                "오늘기분어때",
                "잘지내",
                "잘지내요",
                "뭐해",
                "뭐하고있어",
            }
        ),
    ),
    (
        SmallTalkKind.OUT_OF_DOMAIN,
        frozenset(
            {
                "오늘날씨어때",
                "날씨알려줘",
                "오늘뉴스알려줘",
                "점심뭐먹지",
                "저녁뭐먹지",
            }
        ),
    ),
)

_ANSWERS = {
    SmallTalkKind.GREETING: (
        "안녕하세요! 근로계약과 아르바이트 권리에 관해 궁금한 점을 물어보세요."
    ),
    SmallTalkKind.THANKS: (
        "도움이 되었다니 다행이에요! 다른 근로조건도 궁금하면 이어서 물어보세요."
    ),
    SmallTalkKind.GOODBYE: (
        "네, 다음에 또 궁금한 점이 생기면 찾아주세요. 안전하게 일하세요!"
    ),
    SmallTalkKind.IDENTITY: (
        "저는 근로계약서와 노동 기준을 쉽게 확인할 수 있도록 돕는 페어사인 챗봇이에요."
    ),
    SmallTalkKind.CAPABILITIES: (
        "최저임금, 주휴수당, 휴게시간, 근로계약서, 퇴직금 등을 물어볼 수 있어요. "
        "예를 들어 ‘주 12시간 일하면 주휴수당을 받을 수 있어?’라고 질문해 보세요."
    ),
    SmallTalkKind.MOOD: (
        "저는 언제든 도와드릴 준비가 되어 있어요! 오늘 일하면서 궁금했던 근로조건이 있나요?"
    ),
    SmallTalkKind.OUT_OF_DOMAIN: (
        "그 내용은 안내하기 어려워요. 대신 근로계약이나 아르바이트 권리에 관한 질문은 도와드릴 수 있어요."
    ),
}


def _compact(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", normalized)


def classify_small_talk(question: str) -> SmallTalkKind | None:
    """짧고 명시적인 허용 문구만 일상대화로 인정한다."""

    compact = _compact(question)
    for kind, phrases in _PHRASES:
        if compact in phrases:
            return kind
    return None


def small_talk_answer(kind: SmallTalkKind) -> str:
    return _ANSWERS[kind]
