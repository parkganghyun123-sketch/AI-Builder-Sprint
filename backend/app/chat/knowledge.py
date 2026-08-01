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


@dataclass(frozen=True)
class GeneralKnowledgeMatch:
    """일반 질문에서 실제로 검색된 검증 지식과 로컬 점수 근거."""

    entry: KnowledgeEntry
    score: float
    matched_aliases: tuple[str, ...]


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
        kb_id="KB-WEEKLY-HOLIDAY-AMOUNT",
        title="주휴수당 조건부 금액 계산",
        topics=frozenset({ChatTopic.WEEKLY_HOLIDAY}),
        source_ids=(
            "SRC-MOEL-WEEKLY-HOLIDAY-AMOUNT",
            "SRC-LSA-DECREE-SCHEDULE-2",
        ),
        text=(
            "단시간근로자의 조건부 1주분 주휴수당은 4주 소정근로시간을 같은 기간 "
            "통상근로자의 총 소정근로일수로 나눈 1일 소정근로시간에 통상시급을 곱한다. "
            "현재는 단시간근로자 비교 정보를 안전하게 입력받지 않으므로 금액을 자동 "
            "계산하지 않고 필요한 값을 안내한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-EXTRA-WORK",
        title="연장·야간·휴일근로 가산임금",
        topics=frozenset({ChatTopic.EXTRA_WORK}),
        source_ids=("SRC-LSA-11", "SRC-LSA-56", "SRC-MOEL-UNDER-5"),
        text=(
            "연장·야간·휴일근로 수당은 통상시급, 날짜별 실제 근무시각과 휴게, "
            "휴일 여부, 사업장 상시근로자 수를 확인해야 한다. 필요한 사실이 없으면 "
            "지급 여부나 금액을 계산하지 않는다."
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
    KnowledgeEntry(
        kb_id="KB-MINOR-EMPLOYMENT-DOCUMENTS",
        title="18세 미만 근로자의 서류와 계약 권리",
        topics=frozenset({ChatTopic.UNSUPPORTED}),
        source_ids=("SRC-LSA-66", "SRC-LSA-67", "SRC-LSA-68"),
        text=(
            "사용자는 18세 미만 근로자의 연령 증명서와 친권자 또는 후견인의 동의서를 "
            "사업장에 갖추어 두어야 한다. 친권자나 후견인은 미성년자의 근로계약을 대신 "
            "체결할 수 없고, 사용자는 근로조건을 본인에게 서면 또는 전자문서로 교부해야 "
            "하며 미성년자는 자신의 임금을 독자적으로 청구할 수 있다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-PREGNANCY-PROTECTION",
        title="임신·출산 후 근로 보호",
        topics=frozenset({ChatTopic.UNSUPPORTED}),
        source_ids=(
            "SRC-LSA-70",
            "SRC-LSA-71",
            "SRC-LSA-74",
            "SRC-LSA-74-2",
            "SRC-LSA-75",
        ),
        text=(
            "임신 중 시간외근로 제한, 야간·휴일근로의 별도 요건, 임신 12주 이내 또는 "
            "32주 이후의 근로시간 단축(원칙 1일 2시간, 1일 근로시간이 8시간 미만이면 "
            "단축 후 6시간 기준), 출퇴근 시각 변경과 태아검진 시간 기준이 있다. 산후 1년이 "
            "지나지 않은 여성의 시간외근로 상한과 생후 1년 미만 유아가 있는 여성 근로자가 "
            "청구하는 1일 2회 각각 30분 이상의 유급 수유시간 기준도 별도로 확인한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-DISABILITY-ACCOMMODATION",
        title="장애인 근로자의 정당한 편의",
        topics=frozenset({ChatTopic.UNSUPPORTED}),
        source_ids=("SRC-ADA-11",),
        text=(
            "사용자는 장애인이 장애가 없는 사람과 동등한 조건에서 직무를 수행할 수 있도록 "
            "정당한 편의를 제공해야 한다. 필요한 편의는 근무시간, 업무 전달 방식, 시설 이용 "
            "등 직무와 사업장 상황에 따라 달라질 수 있다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-WAGE-PAYMENT",
        title="임금 지급일과 임금명세서",
        topics=frozenset({ChatTopic.UNSUPPORTED}),
        source_ids=("SRC-LSA-43", "SRC-LSA-48"),
        text=(
            "임금은 원칙적으로 통화로 근로자에게 직접 전액 지급하고, 매월 1회 이상 일정한 "
            "날짜를 정하여 지급한다. 임금을 지급할 때에는 구성항목, 계산방법과 공제 내역 등 "
            "법정 사항이 적힌 임금명세서를 서면 또는 전자문서로 교부해야 한다."
        ),
    ),
    KnowledgeEntry(
        kb_id="KB-POST-EMPLOYMENT-SETTLEMENT",
        title="퇴직 후 임금·금품 지급기한",
        topics=frozenset({ChatTopic.UNSUPPORTED}),
        source_ids=("SRC-LSA-36",),
        text=(
            "근로자가 퇴직한 경우 사용자는 원칙적으로 지급 사유가 발생한 때부터 14일 "
            "이내에 임금, 보상금과 그 밖의 금품을 지급해야 한다. 특별한 사정이 있는 "
            "경우에는 당사자 사이의 합의로 지급기일을 연장할 수 있다."
        ),
    ),
)


# 사용자 표현을 법률 용어로 바꾸기 위한 로컬 검색 사전이다. 이 문구 자체는 답변에
# 사용하지 않으며, 매칭된 뒤에는 반드시 VERIFIED_KNOWLEDGE의 원문과 출처만 사용한다.
_GENERAL_ALIASES: dict[str, tuple[str, ...]] = {
    "KB-MW-2026": (
        "최저임금",
        "최저시급",
        "법정시급",
        "법으로정한시급",
        "시급최소",
        "시급하한",
        "시급기준",
        "임금최소",
    ),
    "KB-CONTRACT-TERMS": (
        "근로계약서",
        "알바계약서",
        "계약서",
        "서면계약",
        "계약서사본",
        "근로조건서류",
    ),
    "KB-BREAK-2026-07": (
        "휴게시간",
        "쉬는시간",
        "휴식시간",
        "쉬는타임",
        "몇분쉬",
        "중간에쉬",
    ),
    "KB-MINOR-WORKING-TIME": (
        "미성년",
        "청소년알바",
        "연소자",
        "18세미만",
        "17살",
        "17세",
        "16살",
        "16세",
    ),
    "KB-WEEKLY-HOLIDAY-TIME": (
        "주휴",
        "주휴수당",
        "유급주휴일",
        "쉬는날돈",
        "쉬는날에도돈",
        "일주일쉬는날수당",
    ),
    "KB-WEEKLY-HOLIDAY-AMOUNT": (
        "주휴수당얼마",
        "주휴수당금액",
        "주휴수당계산",
        "주휴계산법",
    ),
    "KB-EXTRA-WORK": (
        "야간수당",
        "연장수당",
        "휴일수당",
        "가산수당",
        "야간근로",
        "연장근로",
        "휴일근로",
    ),
    "KB-SEVERANCE-ELIGIBILITY": (
        "퇴직금",
        "퇴직급여",
        "퇴사할때돈",
        "그만두면받는돈",
        "그만둘때받는돈",
    ),
    "KB-ANNUAL-LEAVE": (
        "연차",
        "연차휴가",
        "월차",
        "유급휴가",
        "휴가며칠",
        "휴가가쌓",
    ),
    "KB-DISMISSAL-NOTICE": (
        "해고예고",
        "해고예고수당",
        "예고수당",
        "30일전통보",
        "한달전통보",
        "갑자기잘렸",
        "갑자기그만두래",
    ),
    "KB-PROBATION-MINIMUM-WAGE": (
        "수습최저임금",
        "수습시급",
        "수습기간시급",
        "교육기간시급",
        "트레이닝기간시급",
        "처음3개월시급",
    ),
    "KB-SOCIAL-INSURANCE": (
        "4대보험",
        "사대보험",
        "사회보험",
        "고용보험",
        "산재보험",
        "건강보험",
        "국민연금",
        "보험가입",
        "보험떼",
    ),
    "KB-MINOR-EMPLOYMENT-DOCUMENTS": (
        "부모동의서",
        "부모님동의서",
        "친권자동의서",
        "후견인동의서",
        "가족관계증명서",
        "미성년자필요서류",
        "청소년알바서류",
        "미성년자계약대리",
        "미성년자임금청구",
    ),
    "KB-PREGNANCY-PROTECTION": (
        "임신보호",
        "임산부보호",
        "임신중근로",
        "임신중야간근로",
        "임신중시간외근로",
        "임신기근로시간단축",
        "임신근로시간단축",
        "태아검진시간",
        "출퇴근시간변경",
        "산후시간외근로",
        "수유시간",
    ),
    "KB-DISABILITY-ACCOMMODATION": (
        "장애인근로자편의",
        "장애인정당한편의",
        "업무편의제공",
        "근무환경조정",
        "휠체어근무환경",
        "장애인업무지원",
    ),
    "KB-WAGE-PAYMENT": (
        "임금지급원칙",
        "월급지급일",
        "급여지급일",
        "월급날",
        "임금명세서",
        "급여명세서",
        "임금지급날짜",
    ),
    "KB-POST-EMPLOYMENT-SETTLEMENT": (
        "퇴직후임금",
        "퇴사후임금",
        "퇴직후월급",
        "퇴사후월급",
        "퇴직후금품",
        "퇴직후14일",
        "퇴사후14일",
        "퇴직금품청산",
        "일을그만둔뒤남은돈",
        "그만둔뒤남은돈",
        "알바를그만두면남은급여",
        "그만두면남은급여",
    ),
}


# 하나의 단어로는 뜻이 모호한 표현을 두 개 이상의 의미 단서로만 매칭한다.
_GENERAL_CONCEPT_GROUPS: dict[str, tuple[tuple[tuple[str, ...], ...], ...]] = {
    "KB-MW-2026": ((("시급", "임금"), ("최소", "기준", "법정", "낮", "괜찮")),),
    "KB-CONTRACT-TERMS": (
        (("서류", "계약"), ("쓰", "썼", "작성", "받", "사본", "없")),
    ),
    "KB-BREAK-2026-07": (
        (("일하면", "일할", "근무", "알바"), ("쉬어", "쉬는", "휴식", "몇분")),
    ),
    "KB-MINOR-WORKING-TIME": (
        (
            ("15살", "15세", "16살", "16세", "17살", "17세", "청소년"),
            ("밤", "야간", "근무", "알바"),
        ),
    ),
    "KB-WEEKLY-HOLIDAY-TIME": (
        (("일주일", "한주", "주당"), ("쉬는날", "휴일"), ("돈", "수당", "유급")),
    ),
    "KB-SEVERANCE-ELIGIBILITY": (
        (("퇴사", "그만두", "일그만"), ("돈", "급여", "수당")),
    ),
    "KB-ANNUAL-LEAVE": (
        (
            ("휴가", "쉬는날"),
            ("며칠", "쌓", "유급", "사용", "신청", "거절", "반려", "못쓰"),
        ),
    ),
    "KB-DISMISSAL-NOTICE": (
        (("해고", "잘렸", "그만두래"), ("예고", "통보", "갑자기", "수당", "돈")),
    ),
    "KB-PROBATION-MINIMUM-WAGE": (
        (("수습", "교육기간", "트레이닝", "처음3개월"), ("시급", "임금", "최저")),
    ),
    "KB-SOCIAL-INSURANCE": ((("보험", "연금"), ("가입", "대상", "떼", "들어")),),
    "KB-MINOR-EMPLOYMENT-DOCUMENTS": (
        (
            ("미성년", "청소년", "18세미만", "17세", "16세"),
            ("서류", "동의", "계약", "임금"),
        ),
        (
            ("부모", "보호자", "친권자", "후견인", "법정대리인"),
            ("동의", "서류", "계약", "대신"),
        ),
    ),
    "KB-PREGNANCY-PROTECTION": (
        (
            ("임신", "임산부", "산후", "출산후"),
            ("근로", "야간", "휴일", "시간외", "단축", "출퇴근"),
        ),
        (("태아", "검진"), ("시간", "휴가", "보장")),
        (("수유", "모유"), ("시간", "휴게")),
    ),
    "KB-DISABILITY-ACCOMMODATION": (
        (("장애인", "장애", "휠체어"), ("편의", "조정", "지원", "근무환경")),
    ),
    "KB-WAGE-PAYMENT": (
        (
            ("임금", "월급", "급여"),
            ("지급일", "지급날짜", "날짜", "원칙", "명세서", "대장"),
        ),
    ),
    "KB-POST-EMPLOYMENT-SETTLEMENT": (
        (
            ("퇴직후", "퇴사후", "그만둔후", "그만둔뒤", "그만두면"),
            ("임금", "월급", "급여", "돈", "금품", "지급", "정산"),
        ),
        (("퇴직", "퇴사"), ("14일", "지급기한", "언제까지")),
    ),
}


def _compact(text: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", text.lower())


def retrieve_general_knowledge(
    question: str,
    *,
    top_k: int = 3,
) -> list[GeneralKnowledgeMatch]:
    """주제를 미리 정하지 않고 검증된 10개 KB 항목 전체를 검색한다.

    직접 동의어뿐 아니라 여러 의미 단서의 동시 출현과 실제 KB 텍스트 토큰 겹침을
    함께 점수화한다. 낮은 점수와 근접한 복수 결과의 처리 여부는 호출자가 결정한다.
    """

    compact = _compact(question)
    query_terms = _terms(question)
    matches: list[GeneralKnowledgeMatch] = []
    for entry in VERIFIED_KNOWLEDGE:
        aliases = _GENERAL_ALIASES.get(entry.kb_id, ())
        matched_aliases = tuple(
            alias for alias in aliases if _compact(alias) in compact
        )
        alias_score = 0.0
        if matched_aliases:
            longest = max(len(_compact(alias)) for alias in matched_aliases)
            alias_score = min(0.94, 0.76 + (longest * 0.025))
            alias_score = min(0.97, alias_score + 0.02 * (len(matched_aliases) - 1))

        concept_score = 0.0
        for group in _GENERAL_CONCEPT_GROUPS.get(entry.kb_id, ()):
            if all(
                any(term in compact for term in alternatives) for alternatives in group
            ):
                concept_score = max(concept_score, 0.82 if len(group) >= 3 else 0.76)

        document_terms = _terms(f"{entry.title} {entry.text}")
        overlap_count = len(query_terms & document_terms)
        overlap = overlap_count / max(len(query_terms), 1)
        lexical_score = min(0.68, overlap * 1.4) if overlap_count >= 2 else 0.0
        score = max(alias_score, concept_score, lexical_score)

        # "계약서에 휴게시간이…"처럼 계약서는 다른 근로조건 질문의 배경으로 자주
        # 등장한다. 작성·교부 단서가 없고 일반어 "계약서"만 맞으면 주제로 쓰지 않는다.
        if (
            entry.kb_id == "KB-CONTRACT-TERMS"
            and set(matched_aliases).issubset({"계약서"})
            and concept_score == 0.0
        ):
            score = min(score, 0.65)

        # 더 구체적인 수습 질문은 일반 최저임금 검색보다 우선한다.
        if entry.kb_id == "KB-PROBATION-MINIMUM-WAGE" and any(
            term in compact for term in ("수습", "교육기간", "트레이닝", "처음3개월")
        ):
            score = min(1.0, score + 0.08)
        if entry.kb_id == "KB-MW-2026" and any(
            term in compact for term in ("수습", "교육기간", "트레이닝", "처음3개월")
        ):
            score = min(score, 0.65)

        minor_document_terms = (
            "서류",
            "동의",
            "가족관계",
            "친권자",
            "후견인",
            "법정대리인",
            "대신",
        )
        if entry.kb_id == "KB-MINOR-EMPLOYMENT-DOCUMENTS" and any(
            term in compact for term in minor_document_terms
        ):
            score = min(1.0, score + 0.1)
        if entry.kb_id == "KB-MINOR-WORKING-TIME" and any(
            term in compact for term in minor_document_terms
        ):
            score = min(score, 0.65)

        settlement_terms = (
            "남은급여",
            "남은돈",
            "언제줘",
            "며칠안",
            "정산",
            "지급기한",
            "14일",
        )
        if entry.kb_id == "KB-POST-EMPLOYMENT-SETTLEMENT" and any(
            term in compact for term in settlement_terms
        ):
            score = min(1.0, score + 0.08)
        if entry.kb_id == "KB-SEVERANCE-ELIGIBILITY" and any(
            term in compact for term in settlement_terms
        ):
            score = min(score, 0.65)

        if score >= 0.5:
            matches.append(
                GeneralKnowledgeMatch(
                    entry=entry,
                    score=round(score, 3),
                    matched_aliases=matched_aliases,
                )
            )

    matches.sort(key=lambda match: (-match.score, match.entry.kb_id))
    return matches[:top_k]


_SIGNAL_TERMS: dict[QuerySignal, frozenset[str]] = {
    QuerySignal.AMOUNT: frozenset({"금액", "시간급", "임금", "수당"}),
    QuerySignal.METHOD: frozenset({"계산", "산식", "시간급", "소정근로시간"}),
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
        if (
            entry.kb_id == "KB-WEEKLY-HOLIDAY-AMOUNT"
            and QuerySignal.AMOUNT not in signals
            and QuerySignal.METHOD not in signals
        ):
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
