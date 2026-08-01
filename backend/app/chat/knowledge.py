"""검증된 KB 항목만 대상으로 하는 작은 로컬 검색 코퍼스.

이 모듈은 임의의 웹 문서나 모델 지식을 검색하지 않는다. 각 항목은 KB.md에서
검토된 항목과 source_id를 명시적으로 옮긴 스냅샷이다. 법정 판단과 계산에는 이
검색 결과를 사용하지 않고, 결정론적 답변의 설명문을 생성할 때만 사용한다.
"""

import re
from dataclasses import dataclass

from app.chat.features import QuerySignal
from app.chat.models import ChatTopic, RetrievedKnowledge


@dataclass(frozen=True)
class KnowledgeEntry:
    kb_id: str
    title: str
    topics: frozenset[ChatTopic]
    source_ids: tuple[str, ...]
    text: str


VERIFIED_KNOWLEDGE: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        kb_id="KB-MW-2026",
        title="2026년 최저임금",
        topics=frozenset({ChatTopic.MINIMUM_WAGE}),
        source_ids=("SRC-MINWAGE-2026",),
        text=(
            "2026년 적용 시간급 최저임금은 10,320원이다. 계약에서 확인된 시간급과 "
            "비교하며, 월급·일급 계약은 소정근로시간 산정 정보가 부족하면 추정하지 않는다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-CONTRACT-TERMS",
        title="근로계약서 필수 기재사항",
        topics=frozenset({ChatTopic.MISSING_CLAUSES}),
        source_ids=("SRC-LSA-17", "SRC-MOEL-CONTRACT-FORMS"),
        text=(
            "근로계약에는 임금, 소정근로시간, 휴일, 연차 유급휴가 등 법정 사항을 "
            "명시하고 서면을 교부해야 한다. 누락 결과는 확인된 입력에서 찾지 못했다는 뜻이다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-BREAK-2026-07",
        title="휴게시간",
        topics=frozenset({ChatTopic.BREAK_TIME}),
        source_ids=("SRC-LSA-54-CURRENT",),
        text=(
            "2026년 7월 기준 근로시간 4시간에는 30분 이상, 8시간에는 1시간 이상의 "
            "휴게를 근로시간 도중에 부여하며 자유롭게 이용할 수 있어야 한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-MINOR-WORKING-TIME",
        title="15세 이상 18세 미만 근로시간",
        topics=frozenset({ChatTopic.WORKING_HOURS}),
        source_ids=("SRC-LSA-69", "SRC-LSA-70"),
        text=(
            "15세 이상 18세 미만의 기본 근로시간은 1일 7시간, 1주 35시간이며 "
            "22시부터 06시까지의 야간근로에는 별도 요건이 있다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-WEEKLY-HOLIDAY-TIME",
        title="주휴 시간 요건",
        topics=frozenset({ChatTopic.WEEKLY_HOLIDAY}),
        source_ids=("SRC-LSA-18", "SRC-MOEL-WEEKLY-HOLIDAY"),
        text=(
            "주휴 관련 시간 요건은 4주 평균 1주 소정근로시간 15시간 이상이다. "
            "시간 요건 충족만으로 실제 지급 대상을 확정하지 않으며 개근 등 사실을 확인해야 한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-SEVERANCE-ELIGIBILITY",
        title="퇴직급여 관련 계약 조건",
        topics=frozenset({ChatTopic.SEVERANCE_PAY}),
        source_ids=(
            "SRC-ERBA-4",
            "SRC-ERBA-8",
            "SRC-MOEL-SEVERANCE-2025",
        ),
        text=(
            "퇴직급여 관련 계약 지표는 예정 근로기간 1년 이상과 4주 평균 주 "
            "소정근로시간 15시간 이상이다. 실제 계속근로와 퇴직 여부는 별도로 확인한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-ANNUAL-LEAVE",
        title="연차 관련 계약 지표",
        topics=frozenset({ChatTopic.ANNUAL_LEAVE}),
        source_ids=("SRC-LSA-60", "SRC-LSA-11", "SRC-LSA-18"),
        text=(
            "연차는 계속근로기간, 출근율 또는 월 개근, 상시근로자 수, 주 소정근로시간 "
            "등을 함께 확인해야 한다. 계약에서는 기간과 시간 지표만 확인한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-DISMISSAL-NOTICE",
        title="해고예고 관련 계약 지표",
        topics=frozenset({ChatTopic.DISMISSAL_NOTICE}),
        source_ids=("SRC-LSA-26",),
        text=(
            "해고예고는 원칙적으로 30일 전 예고 또는 30일분 이상의 통상임금을 "
            "규정하며 계속근로 3개월 미만 등 예외가 있다. 계약 예정기간만으로 수당 여부를 확정하지 않는다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-PROBATION-MINIMUM-WAGE",
        title="수습 최저임금",
        topics=frozenset({ChatTopic.PROBATION_MINIMUM_WAGE}),
        source_ids=("SRC-MWA-5", "SRC-MWA-DECREE-3", "SRC-MINWAGE-2026"),
        text=(
            "수습 감액에는 1년 이상 계약, 수습 시작 후 3개월 이내, 최대 10% 등의 "
            "조건이 있고 단순노무 종사자는 제외된다. 모든 전제를 확인하기 전에는 감액 적용을 단정하지 않는다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-SOCIAL-INSURANCE",
        title="4대보험별 확인",
        topics=frozenset({ChatTopic.SOCIAL_INSURANCE}),
        source_ids=(
            "SRC-IACI-COVERAGE",
            "SRC-EASYLAW-EMPLOYMENT-INSURANCE",
            "SRC-NHIS-DECREE-9",
            "SRC-NPS-COVERAGE",
        ),
        text=(
            "산재보험, 고용보험, 건강보험, 국민연금은 적용 기준과 예외가 서로 다르므로 "
            "가입 여부를 하나로 묶어 단정하지 않고 보험별 사실을 확인한다."
        ),
    ),
)


_SIGNAL_TERMS: dict[QuerySignal, frozenset[str]] = {
    QuerySignal.AMOUNT: frozenset({"금액", "시간급", "임금", "수당"}),
    QuerySignal.DATE: frozenset({"기간", "시점", "일"}),
    QuerySignal.REQUIREMENT: frozenset({"요건", "기준", "조건"}),
    QuerySignal.ELIGIBILITY: frozenset({"충족", "적용", "대상", "확인"}),
    QuerySignal.MISSING: frozenset({"누락", "기재", "서면"}),
}


def _terms(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[가-힣A-Za-z0-9]+", text)
        if len(token) >= 2
    }


def retrieve_knowledge(
    question: str,
    *,
    topic: ChatTopic,
    signals: list[QuerySignal],
    top_k: int = 3,
) -> list[tuple[KnowledgeEntry, RetrievedKnowledge]]:
    """질문을 로컬에서만 점수화하고 검증 코퍼스의 상위 항목을 반환한다."""

    query_terms = _terms(question)
    for signal in signals:
        query_terms.update(_SIGNAL_TERMS[signal])

    ranked: list[tuple[float, KnowledgeEntry]] = []
    for entry in VERIFIED_KNOWLEDGE:
        if topic not in entry.topics:
            continue
        document_terms = _terms(f"{entry.title} {entry.text}")
        overlap = len(query_terms & document_terms) / max(len(query_terms), 1)
        score = min(1.0, 0.75 + (0.25 * overlap))
        if score >= 0.75:
            ranked.append((score, entry))

    ranked.sort(key=lambda item: (-item[0], item[1].kb_id))
    return [
        (
            entry,
            RetrievedKnowledge(
                kb_id=entry.kb_id,
                title=entry.title,
                source_ids=list(entry.source_ids),
                score=round(score, 3),
            ),
        )
        for score, entry in ranked[:top_k]
    ]
