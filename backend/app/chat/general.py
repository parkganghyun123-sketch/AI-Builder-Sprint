"""계약서 없이 묻는 일반 노동기준 안내.

질문을 검증된 지식 범주로만 라우팅하고 결정론적 문장으로 답한다. 이전 응답의
주제 코드를 함께 받으면 "그럼 6시간은?" 같은 후속 질문도 같은 기준으로 처리한다.
"""

import re
from enum import Enum

from app.chat.general_provider import (
    GeneralActionId,
    GeneralBlockId,
    GeneralDocumentStatus,
    GeneralPlanContext,
    GeneralProviderError,
    GeneralResponsePlan,
    GeneralStage,
    generate_openai_general_answer,
    generate_openai_general_plan,
    generate_upstage_general_answer,
    generate_upstage_general_plan,
    render_general_natural_answer,
)
from app.chat.knowledge import (
    VERIFIED_KNOWLEDGE,
    GeneralKnowledgeMatch,
    retrieve_general_knowledge,
)
from app.chat.models import (
    GenerationFactCard,
    GenerationFactKind,
    NaturalRealizationInput,
)
from app.config import settings
from app.schemas import (
    ChatAction,
    ChatEvidence,
    ChatEvidenceKind,
    GeneralQuestionResponse,
    GeneralQuestionTopic,
)

WEEKLY_HOLIDAY_URL = "https://1350.moel.go.kr/rtmview.do?id=1000059852"
WEEKLY_HOLIDAY_AMOUNT_URL = (
    "https://1350.moel.go.kr/home/hp/data/faqView.do?faq_idx=1000000822"
)
MINIMUM_WAGE_URL = "https://www.minimumwage.go.kr/minWage/policy/decisionMain.do"
LABOR_STANDARDS_ACT_URL = "https://www.law.go.kr/LSW/lsInfoP.do?lsId=001872"
SHORT_TIME_WORK_URL = "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1027161153"
BREAK_TIME_URL = (
    "https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032123587"
)
MINOR_HOURS_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0069&lsiSeq=265959&urlMode=lsScJoRltInfoR"
MINOR_NIGHT_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0070&lsiSeq=265959&urlMode=lsScJoRltInfoR"
CONTRACT_FORM_URL = (
    "https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230700845"
)
WRITTEN_CONTRACT_LAW_URL = (
    "https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1014516221"
)
UNDER_FIVE_URL = "https://1350.moel.go.kr/rtmview.do?id=1000000868"
GUIDANCE_URL = "https://1350.moel.go.kr/"
ERBA_4_URL = "https://www.law.go.kr/법령/근로자퇴직급여보장법/제4조"
ERBA_8_URL = "https://www.law.go.kr/법령/근로자퇴직급여보장법/제8조"
MOEL_SEVERANCE_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselView.do?inetDcssMngId=202503130158379040853"
ANNUAL_LEAVE_URL = "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1012792285"
EMPLOYEE_SCOPE_URL = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1029727821"
)
DISMISSAL_NOTICE_URL = (
    "https://law.go.kr/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=1000112976"
)
PROBATION_WAGE_URL = "https://www.law.go.kr/법령/최저임금법/제5조"
PROBATION_DECREE_URL = "https://www.law.go.kr/법령/최저임금법시행령/제3조"
EMPLOYMENT_INSURANCE_URL = "https://www.easylaw.go.kr/CSP/CnpClsMain.laf?ccfNo=4&cciNo=2&cnpClsNo=2&csmSeq=706&popMenu=ov"
HEALTH_INSURANCE_URL = "https://www.law.go.kr/법령/국민건강보험법시행령/제9조"
PENSION_URL = "https://www.nps.or.kr/pnsinfo/ntpsklg/getOHAF0097M0.do"
INDUSTRIAL_ACCIDENT_URL = "https://www.law.go.kr/법령/산업재해보상보험법"
MINOR_DOCUMENT_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0066&lsiSeq=265959&urlMode=lsScJoRltInfoR"
MINOR_CONTRACT_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0067&lsiSeq=265959&urlMode=lsScJoRltInfoR"
MINOR_WAGE_CLAIM_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0068&lsiSeq=265959&urlMode=lsScJoRltInfoR"
POSTPARTUM_OVERTIME_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0071&lsiSeq=265959&urlMode=lsScJoRltInfoR"
PREGNANCY_PROTECTION_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0074&lsiSeq=265959&urlMode=lsScJoRltInfoR"
PRENATAL_CHECKUP_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=02&joNo=0074&lsiSeq=265959&urlMode=lsScJoRltInfoR"
NURSING_TIME_URL = "https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0075&lsiSeq=265959&urlMode=lsScJoRltInfoR"
DISABILITY_ACCOMMODATION_URL = "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1031811685"
WAGE_PAYMENT_URL = (
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1025590455"
)
WAGE_STATEMENT_URL = (
    "https://www.law.go.kr/lsLawLinkInfo.do?lsJoLnkSeq=1000610123&chrClsCd=010202"
)
POST_EMPLOYMENT_SETTLEMENT_URL = "https://www.law.go.kr/LSW/lsLawLinkInfo.do?ancYnChk=0&chrClsCd=010202&lsJoLnkSeq=1012828349"

MINIMUM_WAGE_2026 = 10_320

WRITTEN_CONTRACT_SOURCE_ID = "SRC-LSA-17"
CONTRACT_FORM_SOURCE_ID = "SRC-MOEL-CONTRACT-FORMS"


class GeneralQuestionSignal(str, Enum):
    NO_CONTRACT = "NO_CONTRACT"
    NOT_RECEIVED = "NOT_RECEIVED"
    BEFORE_START = "BEFORE_START"
    ALREADY_WORKING = "ALREADY_WORKING"
    ASKS_OKAY = "ASKS_OKAY"
    ASKS_NEXT_ACTION = "ASKS_NEXT_ACTION"
    ASKS_WHY = "ASKS_WHY"


class GeneralQuestionIntent(str, Enum):
    """질문의 주제와 별도로 사용자가 실제로 요구한 답의 형태."""

    ELIGIBILITY = "ELIGIBILITY"
    AMOUNT = "AMOUNT"
    METHOD = "METHOD"
    REQUIREMENTS = "REQUIREMENTS"
    DOCUMENTS = "DOCUMENTS"
    DEADLINE = "DEADLINE"
    PROCEDURE = "PROCEDURE"
    REASON = "REASON"
    GENERAL = "GENERAL"


_WRITTEN_BLOCKS = {
    GeneralBlockId.CORE_STANDARD: (
        "사용자는 임금, 소정근로시간, 휴일 등 주요 근로조건을 서면으로 "
        "적어 근로자에게 교부해야 합니다."
    ),
    GeneralBlockId.BEFORE_WORK: (
        "근무 전이라면 주요 조건을 적은 계약서를 작성하고 사본을 받은 뒤 시작하세요."
    ),
    GeneralBlockId.WORK_STARTED: (
        "이미 근무 중이면 지금 계약서 작성과 사본 교부를 요청하고, 합의·근무·급여 "
        "기록을 보관하세요."
    ),
    GeneralBlockId.CHECK_REQUIRED: (
        "추가 확인 항목: 임금과 급여일, 근무시간과 휴게시간, 근무일과 휴일, "
        "근무장소와 업무, 계약기간을 서로 같은 내용으로 이해했는지 확인하세요."
    ),
}

_NEXT_ACTION_BLOCKS = {
    GeneralDocumentStatus.NOT_WRITTEN: (
        "계약서를 아직 작성하지 않았다면 지금 주요 조건을 서면으로 정리하세요."
    ),
    GeneralDocumentStatus.NOT_RECEIVED: (
        "계약서를 작성했지만 받지 못했다면, 사장님께 서명한 계약서 사본을 요청하세요."
    ),
    GeneralDocumentStatus.UNKNOWN: (
        "계약서 작성 여부와 사본 수령 여부를 확인하고 빠진 부분을 요청하세요."
    ),
}

_BLOCK_SOURCE_IDS = {
    GeneralBlockId.CORE_STANDARD: [WRITTEN_CONTRACT_SOURCE_ID],
    GeneralBlockId.BEFORE_WORK: [],
    GeneralBlockId.WORK_STARTED: [],
    GeneralBlockId.CHECK_REQUIRED: [CONTRACT_FORM_SOURCE_ID],
    GeneralBlockId.NEXT_ACTION: [],
}

_SEVERANCE_SOURCE_IDS = ["SRC-ERBA-4", "SRC-ERBA-8", "SRC-MOEL-SEVERANCE-2025"]
_SEVERANCE_BLOCKS = {
    GeneralBlockId.CORE_LIMITATION: (
        "퇴직급여는 계약 조건뿐 아니라 실제 근무 이력과 퇴직 여부도 충족해야 합니다."
    ),
    GeneralBlockId.LEGAL_INDICATORS: (
        "계속근로기간이 1년 이상이고 4주 평균 주 소정근로시간이 15시간 이상이면 "
        "퇴직급여 적용 기준에 해당합니다."
    ),
    GeneralBlockId.CONTRACT_SCOPE: (
        "계약서는 예정 기간과 현재 근로시간만 보여주므로 실제 전체 이력은 별도 자료가 필요합니다."
    ),
    GeneralBlockId.NEEDS_CHECK: (
        "확인 항목: 실제 입·퇴사일, 근무 중단, 기간별 주 근로시간, 실제 퇴직 여부입니다."
    ),
    GeneralBlockId.NEXT_ACTION: (
        "계약서와 출퇴근·급여·근무표 기록을 함께 확인하고, 필요하면 1350에 문의하세요."
    ),
}

SUGGESTIONS = [
    "1주일에 12시간 일하면 주휴수당을 받나요?",
    "최저임금 기준을 알려주세요.",
    "6시간 일하면 휴게시간은 얼마나 필요한가요?",
    "근로계약서를 꼭 받아야 하나요?",
    "17살인데 밤 10시 이후에 일해도 되나요?",
    "야간근로 수당 기준을 알려주세요.",
    "퇴직금 받을 수 있어?",
]

_HOURS = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*시간")
_MONEY = re.compile(r"([0-9][0-9,]{3,})\s*원")
_AGE = re.compile(r"(?:만\s*)?(\d{1,2})\s*(?:살|세)")

_OUT_OF_SCOPE_WORDS = (
    "신고",
    "고소",
    "소송",
    "처벌",
    "합의금",
    "부당해고",
    "직장 내 괴롭힘",
    "임금체불 신고",
    "임금체불",
    "대타",
    "결근",
    "무단결근",
    "실제 근무",
    "일한 돈 못",
    "돈 안 줘",
    "돈을 안 줘",
    "개근했",
    "해고가 정당",
    "해고해도",
    "법 무시",
    "지시 무시",
    "프롬프트",
    "무조건 답",
)

_EXTRA_WORK_TERMS = (
    "야간근로",
    "연장근로",
    "휴일근로",
    "가산수당",
    "야간수당",
    "연장수당",
    "휴일수당",
)

_CALCULATION_REQUEST_TERMS = ("계산", "얼마 더", "금액", "몇 원", "얼마 받아")

_INJECTION_MARKERS = (
    "ignorepreviousinstructions",
    "ignoreallinstructions",
    "disregardpreviousinstructions",
    "overrideinstructions",
    "forgetallpriorinstructions",
    "forgetpreviousinstructions",
    "forgetallinstructions",
    "bypasstherules",
    "bypassrules",
    "systemprompt",
    "jailbreak",
    "이전지시무시",
    "앞선지시무시",
    "명령무시",
    "규칙무시",
    "프롬프트무시",
)
_CONTRACT_VALIDITY_MARKERS = ("효력", "유효", "무효")
_PERSONAL_MINOR_DOCUMENT_MARKERS = (
    "허락없이",
    "동의없이",
    "서류없이",
    "동의서없이",
    "없이일",
    "없이알바",
    "안냈",
    "제출안",
    "보호자몰래",
    "부모몰래",
)
_PERSONAL_PROTECTION_MARKERS = (
    "거부당",
    "거절당",
    "거부했",
    "거절했",
    "신청거부",
    "안해줌",
    "안해줘",
    "차별",
    "위법",
    "불법",
    "해고",
)
_PERSONAL_WAGE_MARKERS = (
    "못받",
    "안받",
    "안들어",
    "안줌",
    "안줘",
    "미지급",
    "체불",
    "밀린",
    "밀렸",
    "지났는데",
    "부당공제",
)
_PERSONAL_SETTLEMENT_MARKERS = (
    "체불",
    "밀린",
    "밀렸",
    "위법",
    "불법",
    "지연이자",
    "이자계산",
    "금액계산",
    "얼마받",
    "안받",
    "안들어",
    "아직안",
    "넘었는데",
    "지났는데",
)
_ACTUAL_SETTLEMENT_CONTEXT_MARKERS = ("퇴사한지", "퇴직한지", "그만둔지")
_ACTUAL_SETTLEMENT_DISPUTE_MARKERS = (
    "못받",
    "안받",
    "아직안",
    "위법",
    "불법",
    "체불",
    "이자",
)
_WEEKLY_ACTUAL_FACT_MARKERS = (
    "이번주",
    "이번한주",
    "지난주",
    "지난7일",
    "최근7일",
    "일했",
    "근무했",
    "출근했",
    "개근했",
    "결근",
    "대타",
)
_ANNUAL_DENIED_FACT_MARKERS = (
    "실제로연차",
    "연차를못받",
    "연차못받",
    "연차안줬",
    "연차거절",
    "연차사용못",
    "못받",
    "안줬",
    "거절",
    "반려",
    "못쓰",
    "못쓰게",
    "사용금지",
)
_PRESCRIBED_HOURS_MARKERS = (
    "소정근로시간",
    "소정시간",
    "계약상주",
    "계약서상주",
    "약정주",
    "약정한주",
)
_FOLLOW_UP_REAL_WORLD_FACT_MARKERS = (
    "실제로",
    "못받",
    "안줌",
    "안줘",
    "거절",
    "반려",
    "사용못",
    "못쓰",
    "지급안",
    "미지급",
    "안받",
    "안들어",
    "지났는데",
)

_GENERAL_TOPIC_BY_KB_ID = {
    "KB-MW-2026": GeneralQuestionTopic.MINIMUM_WAGE,
    "KB-CONTRACT-TERMS": GeneralQuestionTopic.WRITTEN_CONTRACT,
    "KB-BREAK-2026-07": GeneralQuestionTopic.BREAK_TIME,
    "KB-MINOR-WORKING-TIME": GeneralQuestionTopic.MINOR_WORK,
    "KB-WEEKLY-HOLIDAY-AMOUNT": GeneralQuestionTopic.WEEKLY_HOLIDAY,
    "KB-WEEKLY-HOLIDAY-TIME": GeneralQuestionTopic.WEEKLY_HOLIDAY,
    "KB-EXTRA-WORK": GeneralQuestionTopic.EXTRA_WORK,
    "KB-SEVERANCE-ELIGIBILITY": GeneralQuestionTopic.SEVERANCE_PAY,
    "KB-ANNUAL-LEAVE": GeneralQuestionTopic.ANNUAL_LEAVE,
    "KB-DISMISSAL-NOTICE": GeneralQuestionTopic.DISMISSAL_NOTICE,
    "KB-PROBATION-MINIMUM-WAGE": GeneralQuestionTopic.PROBATION_MINIMUM_WAGE,
    "KB-SOCIAL-INSURANCE": GeneralQuestionTopic.SOCIAL_INSURANCE,
    "KB-MINOR-EMPLOYMENT-DOCUMENTS": GeneralQuestionTopic.MINOR_DOCUMENTS,
    "KB-PREGNANCY-PROTECTION": GeneralQuestionTopic.PREGNANCY_PROTECTION,
    "KB-DISABILITY-ACCOMMODATION": GeneralQuestionTopic.DISABILITY_ACCOMMODATION,
    "KB-WAGE-PAYMENT": GeneralQuestionTopic.WAGE_PAYMENT,
    "KB-POST-EMPLOYMENT-SETTLEMENT": GeneralQuestionTopic.POST_EMPLOYMENT_SETTLEMENT,
}

_KB_ID_BY_GENERAL_TOPIC = {
    topic: kb_id for kb_id, topic in _GENERAL_TOPIC_BY_KB_ID.items()
}


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


def _question_intents(question: str) -> tuple[GeneralQuestionIntent, ...]:
    """한 질문의 복수 요구를 보존한다. 주제 분류와 섞지 않는다."""

    compact = re.sub(r"\s+", "", question)
    intents: list[GeneralQuestionIntent] = []
    money_context = any(
        word in compact
        for word in ("수당", "임금", "급여", "월급", "시급", "퇴직금", "돈")
    )
    if any(word in compact for word in ("금액", "몇원")) or (
        "얼마" in compact and "얼마나" not in compact and money_context
    ):
        intents.append(GeneralQuestionIntent.AMOUNT)
    markers = (
        (GeneralQuestionIntent.ELIGIBILITY, ("받을수", "대상", "해당", "가능")),
        (GeneralQuestionIntent.METHOD, ("계산법", "산식", "어떻게계산", "방법")),
        (GeneralQuestionIntent.REQUIREMENTS, ("조건", "요건", "기준")),
        (GeneralQuestionIntent.DOCUMENTS, ("서류", "준비물", "필요한것")),
        (GeneralQuestionIntent.DEADLINE, ("언제까지", "기한", "며칠", "몇일")),
        (GeneralQuestionIntent.PROCEDURE, ("어떻게해야", "뭐해야", "절차", "신청")),
        (GeneralQuestionIntent.REASON, ("왜", "이유")),
    )
    for intent, words in markers:
        if any(word in compact for word in words):
            intents.append(intent)
    return tuple(intents) or (GeneralQuestionIntent.GENERAL,)


def _weekly_holiday_amount_answer(question: str) -> tuple[str, str]:
    """금액 의도를 놓치지 않되, 보류한 단시간근로자 계산은 수행하지 않는다."""

    return (
        "주휴수당 금액은 현재 자동 계산하지 않습니다. 단시간근로자 여부에 따라 1일 "
        "소정근로시간 산정에 추가 비교 정보가 필요하기 때문입니다. 계산하려면 통상시급, "
        "최근 4주 약정 소정근로시간과 같은 업무 통상근로자의 근로일수를 확인해야 합니다.",
        "실제 지급 여부에는 해당 주 소정근로일 개근과 근로관계 유지 여부도 별도로 "
        "확인해야 합니다.",
    )


def _is_outdated_question(question: str) -> bool:
    compact = re.sub(r"[^가-힣a-z0-9]", "", question.lower())
    years = {int(year) for year in re.findall(r"20\d{2}", question)}
    return bool(years - {2026}) or any(
        marker in compact
        for marker in (
            "내년",
            "작년",
            "지난해",
            "예전법",
            "최신",
            "가장최근",
            "업데이트된법",
            "가장새",
            "제일새로운",
            "최근업데이트",
        )
    )


def _compact_for_safety(question: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", question.lower())


def _attach_retrieval(
    response: GeneralQuestionResponse,
    match: GeneralKnowledgeMatch | None,
) -> GeneralQuestionResponse:
    if match is None:
        return response
    return response.model_copy(
        update={
            "retrieved_kb_ids": [match.entry.kb_id],
            "retrieved_source_ids": list(match.entry.source_ids),
        }
    )


def _is_follow_up(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    return len(compact) <= 40 and (
        bool(re.search(r"\d", compact))
        or any(
            marker in compact
            for marker in ("그럼", "그러면", "왜", "조건", "기준", "어떻게", "뭐", "몇")
        )
    )


def _context_match(context: GeneralQuestionTopic) -> GeneralKnowledgeMatch | None:
    kb_id = _KB_ID_BY_GENERAL_TOPIC.get(context)
    if kb_id is None:
        return None
    entry = next((item for item in VERIFIED_KNOWLEDGE if item.kb_id == kb_id), None)
    if entry is None:
        return None
    return GeneralKnowledgeMatch(entry=entry, score=0.75, matched_aliases=())


def _route_general_question(
    question: str,
    context: GeneralQuestionTopic | None,
) -> tuple[GeneralQuestionTopic, GeneralKnowledgeMatch | None]:
    compact = _compact_for_safety(question)
    if context is not None and any(
        marker in compact for marker in _FOLLOW_UP_REAL_WORLD_FACT_MARKERS
    ):
        return GeneralQuestionTopic.OUT_OF_SCOPE, None
    if (
        any(word in question for word in _OUT_OF_SCOPE_WORDS)
        or _is_outdated_question(question)
        or (
            any(marker in compact for marker in _ACTUAL_SETTLEMENT_CONTEXT_MARKERS)
            and any(marker in compact for marker in _ACTUAL_SETTLEMENT_DISPUTE_MARKERS)
        )
        or any(marker in compact for marker in _PERSONAL_MINOR_DOCUMENT_MARKERS)
        or any(
            marker in compact
            for marker in (
                *_INJECTION_MARKERS,
                *_CONTRACT_VALIDITY_MARKERS,
            )
        )
    ):
        return GeneralQuestionTopic.OUT_OF_SCOPE, None

    matches = retrieve_general_knowledge(question, top_k=3)
    if matches and matches[0].score >= 0.74:
        strong_topics = {
            _GENERAL_TOPIC_BY_KB_ID[match.entry.kb_id]
            for match in matches
            if match.score >= 0.74
        }
        protected_topics = {
            GeneralQuestionTopic.MINOR_WORK,
            GeneralQuestionTopic.PREGNANCY_PROTECTION,
        }
        if (
            GeneralQuestionTopic.EXTRA_WORK in strong_topics
            and strong_topics & protected_topics
        ):
            strong_topics.discard(GeneralQuestionTopic.EXTRA_WORK)
        if len(strong_topics) > 1:
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        topic = next(iter(strong_topics))
        selected_match = next(
            match
            for match in matches
            if _GENERAL_TOPIC_BY_KB_ID[match.entry.kb_id] == topic
        )
        if topic == GeneralQuestionTopic.WEEKLY_HOLIDAY and any(
            marker in compact for marker in _WEEKLY_ACTUAL_FACT_MARKERS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        if topic == GeneralQuestionTopic.ANNUAL_LEAVE and any(
            marker in compact for marker in _ANNUAL_DENIED_FACT_MARKERS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        if topic == GeneralQuestionTopic.MINOR_DOCUMENTS and any(
            marker in compact for marker in _PERSONAL_MINOR_DOCUMENT_MARKERS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        if topic in {
            GeneralQuestionTopic.PREGNANCY_PROTECTION,
            GeneralQuestionTopic.DISABILITY_ACCOMMODATION,
        } and any(marker in compact for marker in _PERSONAL_PROTECTION_MARKERS):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        if topic == GeneralQuestionTopic.WAGE_PAYMENT and any(
            marker in compact for marker in _PERSONAL_WAGE_MARKERS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        if topic == GeneralQuestionTopic.POST_EMPLOYMENT_SETTLEMENT and any(
            marker in compact for marker in _PERSONAL_SETTLEMENT_MARKERS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        return topic, selected_match

    if any(term in question for term in _EXTRA_WORK_TERMS):
        return GeneralQuestionTopic.EXTRA_WORK, None

    if (
        context is not None
        and context != GeneralQuestionTopic.OUT_OF_SCOPE
        and _is_follow_up(question)
    ):
        match = _context_match(context)
        if match is not None:
            return context, match
        if context == GeneralQuestionTopic.EXTRA_WORK:
            return context, None
    return GeneralQuestionTopic.OUT_OF_SCOPE, None


def _weekly_holiday(question: str) -> GeneralQuestionResponse:
    intents = _question_intents(question)
    compact = _compact_for_safety(question)
    limitations = (
        "실제 근무시간이 아니라 계약에서 정한 소정근로시간을 기준으로 보며, "
        "확인할 항목은 해당 주 소정근로일 개근과 해당 주까지 근로관계 유지입니다."
    )
    hours = (
        _hours(question)
        if any(marker in compact for marker in _PRESCRIBED_HOURS_MARKERS)
        else None
    )
    if (
        GeneralQuestionIntent.METHOD in intents
        and GeneralQuestionIntent.AMOUNT not in intents
    ):
        answer = (
            "주휴수당은 1일 소정근로시간에 시간급 임금을 곱해 계산합니다. "
            "단시간근로자의 1일 소정근로시간은 최근 4주 소정근로시간을 같은 기간 "
            "통상근로자의 총 소정근로일수로 나누어 산정합니다."
        )
        limitations = (
            "개인 금액을 계산하려면 단시간근로자 해당 여부, 통상시급과 각 산식의 "
            "입력값을 별도로 확인해야 합니다."
        )
    elif GeneralQuestionIntent.AMOUNT in intents:
        answer, limitations = _weekly_holiday_amount_answer(question)
    elif hours is not None and hours < 15:
        answer = (
            f"입력한 주 {hours:g}시간이 4주 평균 소정근로시간이면 15시간 미만이므로 "
            "주휴수당 시간 조건을 충족하지 않습니다."
        )
    elif hours is not None:
        answer = (
            f"입력한 주 {hours:g}시간이 4주 평균 소정근로시간이면 시간 요건을 "
            "충족합니다. 소정근로일 개근도 주요 조건입니다."
        )
    else:
        answer = (
            "주요 조건은 4주 평균 주 소정근로시간 15시간 이상과 소정근로일 개근입니다."
        )
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.WEEKLY_HOLIDAY,
        answer=answer,
        limitations=limitations,
        evidence=[
            _evidence(
                "주휴일 기준",
                "고용노동부 주휴수당 지급기준",
                WEEKLY_HOLIDAY_URL,
            ),
            _evidence(
                "단시간근로자 시간 기준",
                "근로기준법 제18조 · 4주 평균 주 15시간 기준",
                SHORT_TIME_WORK_URL,
            ),
            _evidence(
                "주휴수당 금액 산식",
                "고용노동부 공식 FAQ · 1일 소정근로시간 × 시간급 임금",
                WEEKLY_HOLIDAY_AMOUNT_URL,
            ),
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
        limitations="월급·일급은 소정근로시간과 최저임금 산입 임금 항목이 필요합니다.",
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
        limitations="실제 휴게 부여와 자유로운 이용 여부는 별도로 확인해야 합니다.",
        evidence=[
            _evidence(
                "휴게시간 기준",
                "근로기준법 제54조 · 4시간에 30분 이상, 8시간에 1시간 이상",
                BREAK_TIME_URL,
            )
        ],
        action=_upload_action("계약서로 휴게시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _extract_written_contract_signals(question: str) -> set[GeneralQuestionSignal]:
    signals: set[GeneralQuestionSignal] = set()
    if any(
        phrase in question
        for phrase in (
            "안썼",
            "안 썼",
            "쓰지 않았",
            "작성 안",
            "작성하지 않았",
            "계약서가 없",
            "계약서 없",
        )
    ):
        signals.add(GeneralQuestionSignal.NO_CONTRACT)
    if any(
        phrase in question
        for phrase in ("못 받", "안 받", "받지 못", "사본 없", "교부받지 못")
    ):
        signals.add(GeneralQuestionSignal.NOT_RECEIVED)
    if any(
        phrase in question
        for phrase in ("시작 전", "근무 전", "일하기 전", "출근 전", "아직 출근")
    ):
        signals.add(GeneralQuestionSignal.BEFORE_START)
    if any(
        phrase in question
        for phrase in ("이미 일", "일하고 있", "근무 중", "출근했", "시작했")
    ):
        signals.add(GeneralQuestionSignal.ALREADY_WORKING)
    if any(phrase in question for phrase in ("괜찮", "문제", "돼?", "되나")):
        signals.add(GeneralQuestionSignal.ASKS_OKAY)
    if any(
        phrase in question
        for phrase in ("어떻게", "어떡", "뭐 해야", "해야 해", "해야 돼")
    ):
        signals.add(GeneralQuestionSignal.ASKS_NEXT_ACTION)
    if any(phrase in question for phrase in ("왜", "이유")):
        signals.add(GeneralQuestionSignal.ASKS_WHY)
    return signals


def _build_plan_context(signals: set[GeneralQuestionSignal]) -> GeneralPlanContext:
    if {
        GeneralQuestionSignal.BEFORE_START,
        GeneralQuestionSignal.ALREADY_WORKING,
    }.issubset(signals):
        stage = GeneralStage.UNKNOWN
    elif GeneralQuestionSignal.ALREADY_WORKING in signals:
        stage = GeneralStage.WORK_STARTED
    elif GeneralQuestionSignal.BEFORE_START in signals:
        stage = GeneralStage.BEFORE_WORK
    else:
        stage = GeneralStage.UNKNOWN
    if GeneralQuestionSignal.NO_CONTRACT in signals:
        status = GeneralDocumentStatus.NOT_WRITTEN
    elif GeneralQuestionSignal.NOT_RECEIVED in signals:
        status = GeneralDocumentStatus.NOT_RECEIVED
    else:
        status = GeneralDocumentStatus.UNKNOWN
    allowed_blocks = [
        GeneralBlockId.CORE_STANDARD,
        GeneralBlockId.CHECK_REQUIRED,
        GeneralBlockId.NEXT_ACTION,
    ]
    if stage == GeneralStage.BEFORE_WORK:
        allowed_blocks.append(GeneralBlockId.BEFORE_WORK)
    if stage == GeneralStage.WORK_STARTED:
        allowed_blocks.append(GeneralBlockId.WORK_STARTED)
    allowed_actions = [GeneralActionId.STANDARD_FORM, GeneralActionId.GUIDANCE_1350]
    if status != GeneralDocumentStatus.NOT_RECEIVED:
        allowed_actions.insert(0, GeneralActionId.DIRECT_INPUT)
    return GeneralPlanContext(
        topic=GeneralQuestionTopic.WRITTEN_CONTRACT.value,
        signals=sorted(signal.value for signal in signals),
        stage=stage,
        document_status=status,
        allowed_block_ids=allowed_blocks,
        block_source_ids={block: _BLOCK_SOURCE_IDS[block] for block in allowed_blocks},
        allowed_action_ids=allowed_actions,
    )


def _deterministic_plan(context: GeneralPlanContext) -> GeneralResponsePlan:
    blocks = [GeneralBlockId.CORE_STANDARD]
    if context.stage == GeneralStage.BEFORE_WORK:
        blocks.append(GeneralBlockId.BEFORE_WORK)
    if context.stage == GeneralStage.WORK_STARTED:
        blocks.append(GeneralBlockId.WORK_STARTED)
    blocks.extend([GeneralBlockId.NEXT_ACTION, GeneralBlockId.CHECK_REQUIRED])
    action = (
        GeneralActionId.STANDARD_FORM
        if context.document_status == GeneralDocumentStatus.NOT_RECEIVED
        else GeneralActionId.DIRECT_INPUT
    )
    return GeneralResponsePlan(
        block_ids=blocks,
        source_ids=[WRITTEN_CONTRACT_SOURCE_ID, CONTRACT_FORM_SOURCE_ID],
        action_id=action,
    )


def _validate_plan(
    plan: GeneralResponsePlan, context: GeneralPlanContext
) -> GeneralResponsePlan:
    if len(plan.block_ids) != len(set(plan.block_ids)) or len(plan.source_ids) != len(
        set(plan.source_ids)
    ):
        raise GeneralProviderError("중복 ID는 사용할 수 없습니다.")
    if not set(plan.block_ids).issubset(context.allowed_block_ids):
        raise GeneralProviderError("허용되지 않은 답변 블록입니다.")
    required = {
        GeneralBlockId.CORE_STANDARD,
        GeneralBlockId.CHECK_REQUIRED,
        GeneralBlockId.NEXT_ACTION,
    }
    if not required.issubset(plan.block_ids):
        raise GeneralProviderError("필수 답변 블록이 누락되었습니다.")
    if context.stage == GeneralStage.BEFORE_WORK and (
        GeneralBlockId.BEFORE_WORK not in plan.block_ids
        or GeneralBlockId.WORK_STARTED in plan.block_ids
    ):
        raise GeneralProviderError("근무 단계와 답변 블록이 맞지 않습니다.")
    if context.stage == GeneralStage.WORK_STARTED and (
        GeneralBlockId.WORK_STARTED not in plan.block_ids
        or GeneralBlockId.BEFORE_WORK in plan.block_ids
    ):
        raise GeneralProviderError("근무 단계와 답변 블록이 맞지 않습니다.")
    if context.stage == GeneralStage.UNKNOWN and {
        GeneralBlockId.BEFORE_WORK,
        GeneralBlockId.WORK_STARTED,
    } & set(plan.block_ids):
        raise GeneralProviderError(
            "미확인 단계에서는 특정 근무 단계를 추정하지 않습니다."
        )
    expected_sources = {
        source
        for block in plan.block_ids
        for source in context.block_source_ids.get(block, [])
    }
    if (
        set(plan.source_ids) != expected_sources
        or plan.action_id not in context.allowed_action_ids
    ):
        raise GeneralProviderError("출처 또는 다음 행동이 허용 목록과 맞지 않습니다.")
    return plan


async def _choose_written_contract_plan(
    context: GeneralPlanContext,
) -> GeneralResponsePlan:
    if settings.openai_api_key:
        try:
            return _validate_plan(await generate_openai_general_plan(context), context)
        except GeneralProviderError:
            pass
    if settings.upstage_api_key:
        try:
            return _validate_plan(await generate_upstage_general_plan(context), context)
        except GeneralProviderError:
            pass
    return _deterministic_plan(context)


def _render_written_contract_plan(
    plan: GeneralResponsePlan, context: GeneralPlanContext
) -> str:
    blocks = {
        **_WRITTEN_BLOCKS,
        GeneralBlockId.NEXT_ACTION: _NEXT_ACTION_BLOCKS[context.document_status],
    }
    ordered = [GeneralBlockId.CORE_STANDARD]
    if context.stage == GeneralStage.BEFORE_WORK:
        ordered.append(GeneralBlockId.BEFORE_WORK)
    elif context.stage == GeneralStage.WORK_STARTED:
        ordered.append(GeneralBlockId.WORK_STARTED)
    ordered.append(GeneralBlockId.NEXT_ACTION)
    return " ".join(
        blocks[block_id] for block_id in ordered if block_id in plan.block_ids
    )


def _action_from_id(action_id: GeneralActionId) -> ChatAction | None:
    return {
        GeneralActionId.DIRECT_INPUT: ChatAction(
            label="말로 들은 조건 직접 입력하기", href="/review?path=B"
        ),
        GeneralActionId.STANDARD_FORM: ChatAction(
            label="표준근로계약서 확인하기", href=CONTRACT_FORM_URL
        ),
        GeneralActionId.GUIDANCE_1350: ChatAction(
            label="고용노동부 1350 안내 보기", href=GUIDANCE_URL
        ),
        GeneralActionId.CONTRACT_UPLOAD: ChatAction(
            label="계약서로 예정 조건 확인하기", href="/upload"
        ),
        GeneralActionId.NONE: None,
    }[action_id]


def _written_contract(
    plan: GeneralResponsePlan, context: GeneralPlanContext
) -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.WRITTEN_CONTRACT,
        answer=_render_written_contract_plan(plan, context),
        limitations=(
            "확인: 임금·급여일, 근무·휴게시간, 근무일·휴일, 장소·업무, 계약기간. "
            "확인이 어렵다면 1350에 문의하세요."
        ),
        evidence=[
            _evidence(
                "주요 근로조건의 서면 명시·교부",
                "근로기준법 제17조",
                WRITTEN_CONTRACT_LAW_URL,
            ),
            _evidence(
                "근로조건 확인 항목",
                "고용노동부 표준근로계약서",
                CONTRACT_FORM_URL,
            ),
        ],
        action=_action_from_id(plan.action_id),
        suggestions=SUGGESTIONS,
    )


def _build_severance_context(
    signals: set[GeneralQuestionSignal],
) -> GeneralPlanContext:
    blocks = [
        GeneralBlockId.CORE_LIMITATION,
        GeneralBlockId.LEGAL_INDICATORS,
        GeneralBlockId.CONTRACT_SCOPE,
        GeneralBlockId.NEEDS_CHECK,
        GeneralBlockId.NEXT_ACTION,
    ]
    status = (
        GeneralDocumentStatus.NOT_WRITTEN
        if GeneralQuestionSignal.NO_CONTRACT in signals
        else GeneralDocumentStatus.UNKNOWN
    )
    return GeneralPlanContext(
        topic=GeneralQuestionTopic.SEVERANCE_PAY.value,
        signals=sorted(signal.value for signal in signals),
        stage=GeneralStage.UNKNOWN,
        document_status=status,
        allowed_block_ids=blocks,
        block_source_ids={
            block: _SEVERANCE_SOURCE_IDS
            if block == GeneralBlockId.LEGAL_INDICATORS
            else []
            for block in blocks
        },
        allowed_action_ids=[
            GeneralActionId.CONTRACT_UPLOAD,
            GeneralActionId.GUIDANCE_1350,
        ],
    )


def _deterministic_severance_plan() -> GeneralResponsePlan:
    return GeneralResponsePlan(
        block_ids=[
            GeneralBlockId.CORE_LIMITATION,
            GeneralBlockId.LEGAL_INDICATORS,
            GeneralBlockId.CONTRACT_SCOPE,
            GeneralBlockId.NEEDS_CHECK,
            GeneralBlockId.NEXT_ACTION,
        ],
        source_ids=_SEVERANCE_SOURCE_IDS,
        action_id=GeneralActionId.CONTRACT_UPLOAD,
    )


def _validate_severance_plan(
    plan: GeneralResponsePlan,
    context: GeneralPlanContext,
) -> GeneralResponsePlan:
    if len(plan.block_ids) != len(set(plan.block_ids)):
        raise GeneralProviderError("중복 답변 블록은 사용할 수 없습니다.")
    if len(plan.source_ids) != len(set(plan.source_ids)):
        raise GeneralProviderError("중복 출처는 사용할 수 없습니다.")
    if set(plan.block_ids) != set(context.allowed_block_ids):
        raise GeneralProviderError("퇴직금 필수 확인 블록이 누락되었습니다.")
    if set(plan.source_ids) != set(_SEVERANCE_SOURCE_IDS):
        raise GeneralProviderError("퇴직금 답변의 출처가 승인 목록과 다릅니다.")
    if plan.action_id not in context.allowed_action_ids:
        raise GeneralProviderError("허용되지 않은 다음 행동입니다.")
    return plan


async def _choose_severance_plan(
    context: GeneralPlanContext,
) -> GeneralResponsePlan:
    if settings.openai_api_key:
        try:
            return _validate_severance_plan(
                await generate_openai_general_plan(context), context
            )
        except GeneralProviderError:
            pass
    if settings.upstage_api_key:
        try:
            return _validate_severance_plan(
                await generate_upstage_general_plan(context), context
            )
        except GeneralProviderError:
            pass
    return _deterministic_severance_plan()


def _severance_pay(
    plan: GeneralResponsePlan,
) -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.SEVERANCE_PAY,
        answer=(
            "계속근로기간이 1년 이상이고 4주 평균 주 소정근로시간이 15시간 이상이면 "
            "퇴직급여 적용 기준에 해당합니다. 실제 근무 이력과 퇴직 여부도 충족해야 합니다."
        ),
        limitations=(
            "확인: 실제 입·퇴사일, 중단 기간, 기간별 주 근로시간, 실제 퇴직 여부. "
            "금액은 별도 자료가 필요합니다."
        ),
        evidence=[
            _evidence(
                "퇴직급여 적용 기준",
                "근로자퇴직급여 보장법 제4조",
                ERBA_4_URL,
            ),
            _evidence(
                "퇴직금제도의 설정 기준",
                "근로자퇴직급여 보장법 제8조",
                ERBA_8_URL,
            ),
            _evidence(
                "계속근로·단시간 근로 확인",
                "고용노동부 퇴직금 상담 기준",
                MOEL_SEVERANCE_URL,
            ),
        ],
        action=_action_from_id(plan.action_id),
        suggestions=SUGGESTIONS,
    )


def _annual_leave() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.ANNUAL_LEAVE,
        answer=(
            "1년간 80% 이상 출근하면 연차 15일, 1년 미만이거나 80% 미만이면 "
            "1개월 개근마다 1일이 발생하는 기준이 있습니다."
        ),
        limitations=(
            "확인: 계속근로기간, 출근율·월 개근, 상시근로자 수, 주 근로시간, 사용 연차."
        ),
        evidence=[
            _evidence("연차 유급휴가 기준", "근로기준법 제60조", ANNUAL_LEAVE_URL),
            _evidence("사업장 적용 범위", "근로기준법 제11조", EMPLOYEE_SCOPE_URL),
            _evidence(
                "단시간근로자 적용 범위", "근로기준법 제18조", SHORT_TIME_WORK_URL
            ),
        ],
        action=_upload_action("계약서로 기간·근로시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _dismissal_notice() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.DISMISSAL_NOTICE,
        answer=(
            "해고예고 기준은 원칙적으로 30일 전에 알리거나 30일분 이상의 통상임금을 "
            "지급하는 내용이며, 계속근로 3개월 미만 등 예외가 있습니다."
        ),
        limitations="확인: 해고 여부, 계속근로기간, 예고, 예외 사유, 통상임금.",
        evidence=[
            _evidence("해고예고와 예외", "근로기준법 제26조", DISMISSAL_NOTICE_URL)
        ],
        action=_upload_action("계약서로 예정 기간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _probation_minimum_wage() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.PROBATION_MINIMUM_WAGE,
        answer=(
            "1년 이상 계약의 수습 시작 후 3개월 이내이고 단순노무 직종이 아니면 "
            "최저임금을 최대 10% 감액할 수 있습니다."
        ),
        limitations="확인: 수습 약정·시작일, 계약기간, 직종, 최저임금 산입 임금.",
        evidence=[
            _evidence("수습근로자 최저임금", "최저임금법 제5조", PROBATION_WAGE_URL),
            _evidence(
                "수습 감액 범위", "최저임금법 시행령 제3조", PROBATION_DECREE_URL
            ),
            _evidence("2026년 최저임금", "최저임금위원회 고시 기준", MINIMUM_WAGE_URL),
        ],
        action=_upload_action("계약서로 수습 조건 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _social_insurance() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.SOCIAL_INSURANCE,
        answer=(
            "4대보험은 보험별 조건을 충족하면 적용됩니다. 산재는 업종, 고용은 근로시간·기간, "
            "건강은 월 근로시간, 국민연금은 기간·시간·소득·근로일수·연령을 각각 봅니다."
        ),
        limitations="확인: 사업장·고용형태, 근로시간·기간, 소득·근로일수·연령과 보험별 예외.",
        evidence=[
            _evidence("산재보험 적용", "산업재해보상보험법", INDUSTRIAL_ACCIDENT_URL),
            _evidence(
                "고용보험 적용",
                "찾기쉬운 생활법령 고용보험 안내",
                EMPLOYMENT_INSURANCE_URL,
            ),
            _evidence(
                "건강보험 적용", "국민건강보험법 시행령 제9조", HEALTH_INSURANCE_URL
            ),
            _evidence("국민연금 적용", "국민연금 사업장가입자 기준", PENSION_URL),
        ],
        action=_upload_action("계약서로 근로시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _minor_documents() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.MINOR_DOCUMENTS,
        answer=(
            "18세 미만이면 사업장에 연령을 증명하는 가족관계기록사항에 관한 증명서와 "
            "친권자·후견인 동의서를 갖춰야 합니다. "
            "대리 계약은 불가하며, 본인에게 근로조건 문서를 교부하고 본인이 임금을 청구합니다."
        ),
        limitations="확인: 실제 나이, 서류 비치, 계약 주체, 근로조건 문서 교부. 계약 효력은 별도 판단입니다.",
        evidence=[
            _evidence(
                "연소자 증명서와 동의서", "근로기준법 제66조", MINOR_DOCUMENT_URL
            ),
            _evidence("미성년자 근로계약", "근로기준법 제67조", MINOR_CONTRACT_URL),
            _evidence(
                "미성년자의 임금 청구", "근로기준법 제68조", MINOR_WAGE_CLAIM_URL
            ),
        ],
        action=_upload_action("계약서로 근로조건 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _pregnancy_protection() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.PREGNANCY_PROTECTION,
        answer=(
            "임신 중 시간외근로는 금지되고 야간·휴일근로에는 별도 요건이 적용됩니다. "
            "근로자가 신청하면 12주 이내·32주 이후에는 원칙적으로 1일 2시간 단축하며, "
            "8시간 미만이면 단축 후 6시간이 되도록 합니다. 출퇴근 변경·태아검진, 산후 "
            "상한·유급 수유시간 기준도 있습니다."
        ),
        limitations="확인: 임신 주수·출산일, 신청, 실제 근무시각, 야간·휴일근로 요건. 임신·산후 기준은 구분합니다.",
        evidence=[
            _evidence("임신 중 야간·휴일근로", "근로기준법 제70조", MINOR_NIGHT_URL),
            _evidence("산후 시간외근로", "근로기준법 제71조", POSTPARTUM_OVERTIME_URL),
            _evidence("임산부 보호", "근로기준법 제74조", PREGNANCY_PROTECTION_URL),
            _evidence("태아검진 시간", "근로기준법 제74조의2", PRENATAL_CHECKUP_URL),
            _evidence("유급 수유시간", "근로기준법 제75조", NURSING_TIME_URL),
        ],
        action=_upload_action("계약서로 근로시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _disability_accommodation() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.DISABILITY_ACCOMMODATION,
        answer=(
            "사용자는 장애인이 장애가 없는 사람과 동등한 조건에서 직무를 수행할 수 있도록 "
            "정당한 편의를 제공해야 합니다. 근무시간 조정, 업무 전달 방식, 시설 이용 등 "
            "필요한 편의는 담당 직무와 사업장 상황을 바탕으로 구체적으로 협의할 항목입니다."
        ),
        limitations="확인: 담당 직무, 필요한 편의, 시설·업무 방식, 협의 내용. 차별·위반 여부는 별도 판단입니다.",
        evidence=[
            _evidence(
                "장애인 근로자의 정당한 편의",
                "장애인차별금지 및 권리구제 등에 관한 법률 제11조",
                DISABILITY_ACCOMMODATION_URL,
            )
        ],
        action=_upload_action("계약서로 업무와 근무조건 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _wage_payment() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.WAGE_PAYMENT,
        answer=(
            "임금은 원칙적으로 매월 1회 이상 정한 날에 통화로 직접 전액 지급해야 합니다. "
            "지급할 때 구성항목·계산방법·공제 내역을 적은 임금명세서도 교부해야 합니다."
        ),
        limitations="확인: 계약 지급일·방법, 실제 입금·공제, 명세서 교부와 법령·단체협약상 예외.",
        evidence=[
            _evidence("임금 지급 원칙", "근로기준법 제43조", WAGE_PAYMENT_URL),
            _evidence("임금명세서 교부", "근로기준법 제48조", WAGE_STATEMENT_URL),
        ],
        action=_upload_action("계약서로 지급일과 임금조건 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _post_employment_settlement() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.POST_EMPLOYMENT_SETTLEMENT,
        answer=(
            "근로자가 실제로 퇴직한 경우 사용자는 원칙적으로 지급 사유가 발생한 때부터 "
            "14일 이내에 임금, 보상금과 그 밖의 금품을 지급해야 합니다. 특별한 사정이 "
            "있는 경우에는 당사자 사이의 합의로 지급기일을 연장할 수 있습니다."
        ),
        limitations="확인: 실제 퇴직일, 금품 종류·금액·지급내역, 특별한 사정, 연장 합의와 지급일.",
        evidence=[
            _evidence(
                "퇴직 후 금품 지급기한",
                "근로기준법 제36조 · 원칙적으로 지급 사유 발생일부터 14일 이내",
                POST_EMPLOYMENT_SETTLEMENT_URL,
            )
        ],
        action=_upload_action("계약서로 계약기간과 임금조건 확인하기"),
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
        limitations="확인: 나이, 계약기간, 실제 근무시각, 당사자 동의와 고용노동부장관 인가.",
        evidence=[
            _evidence(
                "18세 미만 근로시간",
                "근로기준법 제69조 · 1일 7시간, 1주 35시간",
                MINOR_HOURS_URL,
            ),
            _evidence(
                "18세 미만 야간·휴일근로",
                "근로기준법 제70조",
                MINOR_NIGHT_URL,
            ),
        ],
        action=_upload_action("계약서 근무시간 확인하기"),
        suggestions=SUGGESTIONS,
    )


def _extra_work() -> GeneralQuestionResponse:
    return GeneralQuestionResponse(
        topic=GeneralQuestionTopic.EXTRA_WORK,
        answer=(
            "적용 대상 사업장에서 연장·야간·휴일근로를 하면 가산임금 기준이 적용됩니다. "
            "야간근로는 22시부터 06시까지입니다."
        ),
        limitations="확인: 상시근로자 수, 실제 근무시각, 휴일, 합의. 5인 미만은 적용 규정이 다를 수 있습니다.",
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
        answer="개별 사실과 기록이 필요한 질문이어서 일반 기준만으로 결론 낼 수 없습니다. 1350 또는 전문가에게 확인하세요.",
        limitations="해고·신고·분쟁과 실제 근무기록이 필요한 판단은 지원하지 않습니다.",
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


def _ensure_direct_answer(
    question: str,
    response: GeneralQuestionResponse,
) -> GeneralQuestionResponse:
    """주제는 맞지만 사용자가 요구한 답의 형태를 놓치는 회귀를 막는다."""

    intents = _question_intents(question)
    if GeneralQuestionIntent.AMOUNT not in intents:
        return response
    if response.topic in {
        GeneralQuestionTopic.WEEKLY_HOLIDAY,
        GeneralQuestionTopic.MINIMUM_WAGE,
    }:
        return response

    missing_by_topic = {
        GeneralQuestionTopic.SEVERANCE_PAY: (
            "퇴직금 계산에는 실제 퇴직일, 직전 3개월 임금 총액·총일수, 계속근로기간과 "
            "기간별 주 근로시간이 필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
        GeneralQuestionTopic.EXTRA_WORK: (
            "가산수당 계산에는 통상시급, 날짜별 실제 시작·종료·휴게시간, 휴일 여부와 "
            "상시근로자 수가 필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
        GeneralQuestionTopic.ANNUAL_LEAVE: (
            "연차 금액 계산에는 수당 종류, 남은 연차, 통상임금 자료와 퇴직·정산 시점이 "
            "필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
        GeneralQuestionTopic.DISMISSAL_NOTICE: (
            "해고예고수당 계산에는 통상임금 자료, 근로시간, 실제 해고일·예고일과 예외 "
            "해당 여부가 필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
        GeneralQuestionTopic.WAGE_PAYMENT: (
            "임금 계산에는 임금 형태·통상시급, 실제 근무기록, 지급액과 공제 내역이 "
            "필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
        GeneralQuestionTopic.POST_EMPLOYMENT_SETTLEMENT: (
            "퇴직 후 정산 계산에는 금품별 산정 자료, 실제 퇴직일, 지급 내역과 지급기일 "
            "연장 합의가 필요합니다. 현재 질문만으로는 계산할 수 없습니다."
        ),
    }
    direct = missing_by_topic.get(response.topic)
    if direct is None:
        direct = (
            "요청하신 금액은 현재 질문과 확인된 자료만으로 계산할 수 없습니다. "
            "계산하려는 금액의 종류와 그 산식에 필요한 근로·임금 정보를 알려주세요."
        )
    return response.model_copy(update={"answer": direct})


_HANDLERS = {
    GeneralQuestionTopic.WEEKLY_HOLIDAY: _weekly_holiday,
    GeneralQuestionTopic.MINIMUM_WAGE: _minimum_wage,
    GeneralQuestionTopic.BREAK_TIME: _break_time,
    GeneralQuestionTopic.MINOR_WORK: _minor_work,
    GeneralQuestionTopic.EXTRA_WORK: lambda _: _extra_work(),
    GeneralQuestionTopic.ANNUAL_LEAVE: lambda _: _annual_leave(),
    GeneralQuestionTopic.DISMISSAL_NOTICE: lambda _: _dismissal_notice(),
    GeneralQuestionTopic.PROBATION_MINIMUM_WAGE: lambda _: _probation_minimum_wage(),
    GeneralQuestionTopic.SOCIAL_INSURANCE: lambda _: _social_insurance(),
    GeneralQuestionTopic.MINOR_DOCUMENTS: lambda _: _minor_documents(),
    GeneralQuestionTopic.PREGNANCY_PROTECTION: lambda _: _pregnancy_protection(),
    GeneralQuestionTopic.DISABILITY_ACCOMMODATION: lambda _: _disability_accommodation(),
    GeneralQuestionTopic.WAGE_PAYMENT: lambda _: _wage_payment(),
    GeneralQuestionTopic.POST_EMPLOYMENT_SETTLEMENT: lambda _: _post_employment_settlement(),
    GeneralQuestionTopic.OUT_OF_SCOPE: lambda _: _out_of_scope(),
}


async def _naturalize_general_response(
    response: GeneralQuestionResponse,
    intents: set[GeneralQuestionIntent],
) -> GeneralQuestionResponse:
    """승인 답변·한계 문장을 보존한 채 비식별 연결 표현만 자연화한다."""

    if not settings.openai_api_key and not settings.upstage_api_key:
        return response
    cards = [
        GenerationFactCard(
            fact_id="FACT-ANSWER",
            kind=GenerationFactKind.DETERMINISTIC_CONCLUSION,
            text=response.answer,
        )
    ]
    context = NaturalRealizationInput(
        selection_keys=[
            response.topic.value,
            *(item.value for item in sorted(intents, key=lambda item: item.value)),
        ],
        fact_cards=cards,
    )
    if settings.openai_api_key:
        try:
            generated = await generate_openai_general_answer(context)
            rendered = render_general_natural_answer(generated, context)
            if rendered is not None:
                return response.model_copy(update={"answer": rendered})
        except GeneralProviderError:
            pass
    if settings.upstage_api_key:
        try:
            generated = await generate_upstage_general_answer(context)
            rendered = render_general_natural_answer(generated, context)
            if rendered is not None:
                return response.model_copy(update={"answer": rendered})
        except GeneralProviderError:
            pass
    return response


async def answer_general_question(
    question: str,
    context: GeneralQuestionTopic | None = None,
) -> GeneralQuestionResponse:
    normalized = question.strip().lower()
    topic, match = _route_general_question(normalized, context)
    if topic == GeneralQuestionTopic.WRITTEN_CONTRACT:
        signals = _extract_written_contract_signals(normalized)
        plan_context = _build_plan_context(signals)
        plan = await _choose_written_contract_plan(plan_context)
        response = _written_contract(plan, plan_context)
        return _attach_retrieval(_ensure_direct_answer(normalized, response), match)
    if topic == GeneralQuestionTopic.SEVERANCE_PAY:
        signals = _extract_written_contract_signals(normalized)
        plan_context = _build_severance_context(signals)
        plan = await _choose_severance_plan(plan_context)
        response = _severance_pay(plan)
        return _attach_retrieval(_ensure_direct_answer(normalized, response), match)
    response = _HANDLERS[topic](normalized)
    deterministic = _attach_retrieval(
        _ensure_direct_answer(normalized, response), match
    )
    if topic == GeneralQuestionTopic.OUT_OF_SCOPE:
        return deterministic
    return await _naturalize_general_response(
        deterministic,
        _question_intents(normalized),
    )
