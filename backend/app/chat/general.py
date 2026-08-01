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
    generate_openai_general_plan,
    generate_upstage_general_plan,
)
from app.chat.knowledge import (
    VERIFIED_KNOWLEDGE,
    GeneralKnowledgeMatch,
    retrieve_general_knowledge,
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


_WRITTEN_BLOCKS = {
    GeneralBlockId.CORE_STANDARD: (
        "사장님(법에서는 사용자라고 부릅니다)은 임금, 소정근로시간, 휴일 등 "
        "주요 근로조건을 서면으로 적어 근로자에게 주어야 합니다."
    ),
    GeneralBlockId.BEFORE_WORK: (
        "근무 시작 전이라면: 사장님과 임금, 근무시간, 휴일 같은 조건을 적은 "
        "계약서를 작성하고, 서명한 계약서 한 부를 받은 뒤 시작하는 것이 좋습니다."
    ),
    GeneralBlockId.WORK_STARTED: (
        "이미 근무를 시작했다면: 지금이라도 사장님께 합의한 근로조건을 서면으로 "
        "적어 달라고 요청하고, 지금까지 주고받은 메시지와 출퇴근·근무·급여 기록을 "
        "함께 보관하세요."
    ),
    GeneralBlockId.CHECK_REQUIRED: (
        "추가 확인 항목: 임금과 급여일, 근무시간과 휴게시간, 근무일과 휴일, "
        "근무장소와 업무, 계약기간을 서로 같은 내용으로 이해했는지 확인하세요."
    ),
}

_NEXT_ACTION_BLOCKS = {
    GeneralDocumentStatus.NOT_WRITTEN: (
        "계약서를 아직 작성하지 않았다면 그냥 넘기지 말고, 지금 사장님과 주요 "
        "조건을 서면으로 정리하세요."
    ),
    GeneralDocumentStatus.NOT_RECEIVED: (
        "계약서를 작성했지만 받지 못했다면, 사장님께 서명한 계약서 사본을 요청하세요."
    ),
    GeneralDocumentStatus.UNKNOWN: (
        "계약서 작성 여부와 사본을 받았는지부터 확인하고, 빠진 쪽을 사장님께 요청하세요."
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
        "지금 질문만으로는 퇴직금 지급 대상인지 확정할 수 없습니다. 퇴직금은 "
        "계약서 한 장의 현재 조건만이 아니라 실제 근무 이력과 퇴직 여부를 함께 확인해야 합니다."
    ),
    GeneralBlockId.LEGAL_INDICATORS: (
        "확인 기준: 계속근로기간이 통상 1년 이상인지, 4주를 평균한 1주 소정근로시간이 "
        "15시간 이상인지 확인해야 합니다. 이 두 숫자만으로 지급 대상을 확정하지는 않습니다."
    ),
    GeneralBlockId.CONTRACT_SCOPE: (
        "계약서는 예정한 계약기간과 현재 소정근로시간을 보여줄 수 있지만, 실제 입·퇴사일과 "
        "전체 근무기간의 시간 변화까지 그대로 보여주지는 않을 수 있습니다."
    ),
    GeneralBlockId.NEEDS_CHECK: (
        "추가 확인 항목: 실제 입사일과 퇴사일, 근무가 중단된 기간, 기간별 주 소정근로시간의 "
        "변화와 주 15시간 미만인 기간, 실제 퇴직 여부, 계약 내용과 실제 근무의 차이입니다."
    ),
    GeneralBlockId.NEXT_ACTION: (
        "다음 단계: 계약서가 있으면 올려 예정 조건을 확인하고, 계약서가 없으면 사장님과 합의한 "
        "조건 및 출퇴근·급여·근무표 기록을 모아 확인하세요. 필요하면 고용노동부 1350에 문의하세요."
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
    "KB-WEEKLY-HOLIDAY-TIME": GeneralQuestionTopic.WEEKLY_HOLIDAY,
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
        strong_topics = {match.entry.kb_id for match in matches if match.score >= 0.74}
        if len(strong_topics) > 1:
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        topic = _GENERAL_TOPIC_BY_KB_ID[matches[0].entry.kb_id]
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
        if topic != GeneralQuestionTopic.MINIMUM_WAGE and any(
            term in question for term in _CALCULATION_REQUEST_TERMS
        ):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
        return topic, matches[0]

    if any(term in question for term in _EXTRA_WORK_TERMS):
        if any(term in question for term in _CALCULATION_REQUEST_TERMS):
            return GeneralQuestionTopic.OUT_OF_SCOPE, None
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
    compact = _compact_for_safety(question)
    hours = (
        _hours(question)
        if any(marker in compact for marker in _PRESCRIBED_HOURS_MARKERS)
        else None
    )
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
            "주휴일은 일반적으로 4주 평균 1주 소정근로시간이 15시간 이상인지와 "
            "약정한 근무일의 개근 여부 등을 확인합니다. 소정근로시간이 15시간 "
            "미만이면 시간 기준에서 제외되지만, 질문에 적은 실제 근무시간을 "
            "소정근로시간으로 대신하여 판단하지 않습니다."
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
                "고용노동부 주휴수당 지급기준",
                WEEKLY_HOLIDAY_URL,
            ),
            _evidence(
                "단시간근로자 시간 기준",
                "근로기준법 제18조 · 4주 평균 주 15시간 기준",
                SHORT_TIME_WORK_URL,
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
    if stage in (GeneralStage.BEFORE_WORK, GeneralStage.UNKNOWN):
        allowed_blocks.append(GeneralBlockId.BEFORE_WORK)
    if stage in (GeneralStage.WORK_STARTED, GeneralStage.UNKNOWN):
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
    blocks = [GeneralBlockId.NEXT_ACTION, GeneralBlockId.CORE_STANDARD]
    if context.stage in (GeneralStage.BEFORE_WORK, GeneralStage.UNKNOWN):
        blocks.append(GeneralBlockId.BEFORE_WORK)
    if context.stage in (GeneralStage.WORK_STARTED, GeneralStage.UNKNOWN):
        blocks.append(GeneralBlockId.WORK_STARTED)
    blocks.append(GeneralBlockId.CHECK_REQUIRED)
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
    if context.stage == GeneralStage.UNKNOWN and not {
        GeneralBlockId.BEFORE_WORK,
        GeneralBlockId.WORK_STARTED,
    }.issubset(plan.block_ids):
        raise GeneralProviderError("미확인 단계에서는 두 경우를 모두 안내해야 합니다.")
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
    return "\n\n".join(blocks[block_id] for block_id in plan.block_ids)


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
            "실제 합의 내용과 계약서를 작성·받지 못한 경위는 질문만으로 확인할 수 "
            "없습니다. 사장님과 확인이 어렵다면 고용노동부 1350에 문의하세요."
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
        answer="\n\n".join(_SEVERANCE_BLOCKS[block] for block in plan.block_ids),
        limitations=(
            "지급 대상이나 금액을 확정하지 않습니다. 계약 조건과 실제 근무 이력이 "
            "다르면 실제 기록을 추가로 확인해야 합니다."
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
            "연차 발생 여부를 확인하려면 계속근로기간, 1년간 출근율 또는 1개월 개근, "
            "상시근로자 수, 주 소정근로시간을 함께 봐야 합니다. 기준에는 1년간 80% "
            "이상 출근 시 15일, 1년 미만 또는 80% 미만이면 1개월 개근마다 1일이 "
            "포함됩니다."
        ),
        limitations=(
            "질문만으로는 실제 계속근로기간, 출근율·월 개근, 상시근로자 수, 사용한 "
            "연차를 확인할 수 없어 개인의 연차 발생 여부나 일수를 확정하지 않습니다."
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
        limitations=(
            "실제 해고인지 계약기간 만료인지, 해고 당시 계속근로기간, 예고 여부, "
            "예외 사유와 통상임금을 확인해야 하므로 지급 대상이나 금액을 확정하지 않습니다."
        ),
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
            "수습 중 최저임금 감액을 검토하려면 1년 이상 근로계약인지, 수습 시작 후 "
            "3개월 이내인지, 단순노무 직종이 아닌지 등을 함께 확인해야 합니다. 감액 "
            "폭은 최대 10% 범위라는 기준이 있습니다."
        ),
        limitations=(
            "수습 약정, 실제 수습 시작일, 직종, 최저임금에 넣어 비교할 임금 항목을 "
            "확인하기 전에는 감액 적용 여부나 개인의 최저 시급을 확정하지 않습니다."
        ),
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
            "4대보험은 하나의 기준으로 가입 여부를 정하지 않습니다. 산재보험은 적용 "
            "원칙과 업종 예외, 고용보험은 근로시간과 계속근로·일용근로 예외, 건강보험은 "
            "월 소정근로시간, 국민연금은 근로기간·시간·소득·근로일수·연령을 각각 확인합니다."
        ),
        limitations=(
            "사업장과 고용형태, 월·주 근로시간, 계속근로기간, 소득, 근로일수와 연령을 "
            "보험별로 확인해야 하므로 네 보험의 개인 가입 대상을 한꺼번에 확정하지 않습니다."
        ),
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
            "18세 미만 근로자를 고용할 때 사용자는 연령을 증명하는 가족관계기록사항 "
            "증명서와 친권자 또는 후견인의 동의서를 사업장에 갖추어 두어야 합니다. "
            "친권자나 후견인이 근로계약을 대신 체결할 수는 없고, 근로조건을 적은 서면 "
            "또는 전자문서는 근로자 본인에게 교부해야 합니다. 미성년자는 자신의 임금을 "
            "독자적으로 청구할 수 있습니다."
        ),
        limitations=(
            "추가 확인 항목: 근로자의 실제 나이, 연령 증명서와 동의서 비치 여부, 계약을 "
            "누가 체결했는지, 근로조건 문서를 본인에게 교부했는지입니다. 이 정보만으로 "
            "개별 계약의 효력이나 법 위반 여부를 확정하지 않습니다."
        ),
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
            "임신 중에는 시간외근로 제한과 야간·휴일근로의 별도 요건이 있습니다. 임신 "
            "12주 이내 또는 32주 이후에는 1일 2시간 근로시간 단축 기준이 있습니다. 다만 "
            "1일 소정근로시간이 8시간 미만이면 단축 후 1일 근로시간이 6시간이 되도록 하는 "
            "범위에서 단축합니다. 출퇴근 "
            "시각 변경과 태아검진 시간도 확인할 수 있습니다. 산후 1년이 지나지 않은 여성의 "
            "시간외근로 상한과 생후 1년 미만 유아가 있는 여성 근로자가 청구할 수 있는 1일 "
            "2회 각각 30분 이상의 유급 수유시간은 별도 기준입니다."
        ),
        limitations=(
            "추가 확인 항목: 임신 여부와 주수 또는 출산일, 신청 내용, 실제 근무시간과 근무 "
            "시각, 야간·휴일근로의 별도 요건 충족 여부입니다. 임신 중 기준과 산후 기준을 "
            "구분하며 개인의 적용 여부나 위반 여부를 확정하지 않습니다."
        ),
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
        limitations=(
            "추가 확인 항목: 담당 직무, 업무 수행에 필요한 구체적 편의, 현재 시설과 업무 "
            "방식, 사업주와 협의한 내용입니다. 장애 여부를 추정하거나 채용 의무·차별·위반 "
            "여부를 확정하지 않습니다."
        ),
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
            "임금은 원칙적으로 통화로 근로자에게 직접 전액 지급하고, 매월 1회 이상 "
            "일정한 날짜를 정하여 지급합니다. 임금을 지급할 때에는 구성항목, 계산방법과 "
            "공제 내역 등 법정 사항이 적힌 임금명세서를 서면 또는 전자문서로 교부해야 합니다."
        ),
        limitations=(
            "추가 확인 항목: 계약서의 지급일과 지급방법, 실제 입금일과 지급액, 공제 사유, "
            "임금명세서 교부 여부입니다. 법령 또는 단체협약에 따른 예외와 실제 미지급·체불 "
            "여부는 별도로 확인해야 하며 여기서 금액이나 위반 여부를 확정하지 않습니다."
        ),
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
        limitations=(
            "추가 확인 항목: 실제 퇴직일, 지급 대상 금품의 종류와 금액, 이미 지급된 내역, "
            "특별한 사정과 기일 연장 합의 여부 및 합의한 지급일입니다. 계약 종료 예정일을 "
            "실제 퇴직일로 추정하지 않으며 체불·위법 여부, 지급액이나 지연이자를 확정·계산하지 않습니다."
        ),
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
        limitations=(
            "나이, 계약기간, 실제 근무시각과 고용노동부장관 인가 여부 등에 따라 "
            "달라질 수 있으므로 개인별 허용 여부를 단정하지 않습니다."
        ),
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
        return _attach_retrieval(_written_contract(plan, plan_context), match)
    if topic == GeneralQuestionTopic.SEVERANCE_PAY:
        signals = _extract_written_contract_signals(normalized)
        plan_context = _build_severance_context(signals)
        plan = await _choose_severance_plan(plan_context)
        return _attach_retrieval(_severance_pay(plan), match)
    return _attach_retrieval(_HANDLERS[topic](normalized), match)
