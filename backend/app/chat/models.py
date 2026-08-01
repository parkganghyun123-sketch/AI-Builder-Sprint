"""챗봇 내부·API 모델."""

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ContractTerms

FACT_PLACEHOLDER_RE = re.compile(r"\{\{(FACT-[A-Z0-9-]+)\}\}")
APPROVED_NATURAL_CONNECTIVES = frozenset(
    {
        "",
        " ",
        ".",
        ", ",
        "과 ",
        "와 ",
        " 다만 ",
        " 그리고 ",
        " 또한 ",
        " 추가로 확인할 내용은 ",
        " 함께 확인할 내용은 ",
        ". 추가로 확인할 내용은 ",
        ". 함께 확인할 내용은 ",
        " 먼저 확인해 주세요.",
        " 함께 확인해 주세요.",
        " 핵심부터 안내드렸어요.",
        " 먼저 확인할 내용은 여기까지예요.",
    }
)


def natural_template_uses_approved_connectives(template: str) -> bool:
    """자리표시자 사이의 모든 텍스트가 서버 승인 연결구인지 검사한다."""

    cursor = 0
    for match in FACT_PLACEHOLDER_RE.finditer(template):
        if template[cursor : match.start()] not in APPROVED_NATURAL_CONNECTIVES:
            return False
        cursor = match.end()
    return template[cursor:] in APPROVED_NATURAL_CONNECTIVES


class ChatIntent(str, Enum):
    FIELD_LOOKUP = "FIELD_LOOKUP"
    CALCULATION = "CALCULATION"
    MISSING_CLAUSE = "MISSING_CLAUSE"
    LEGAL_STANDARD = "LEGAL_STANDARD"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ChatTopic(str, Enum):
    WEEKLY_HOLIDAY = "WEEKLY_HOLIDAY"
    MINIMUM_WAGE = "MINIMUM_WAGE"
    BREAK_TIME = "BREAK_TIME"
    WORKING_HOURS = "WORKING_HOURS"
    WAGE = "WAGE"
    PAYDAY = "PAYDAY"
    CONTRACT_PERIOD = "CONTRACT_PERIOD"
    WORKPLACE = "WORKPLACE"
    JOB = "JOB"
    MISSING_CLAUSES = "MISSING_CLAUSES"
    SEVERANCE_PAY = "SEVERANCE_PAY"
    SOCIAL_INSURANCE = "SOCIAL_INSURANCE"
    ANNUAL_LEAVE = "ANNUAL_LEAVE"
    DISMISSAL_NOTICE = "DISMISSAL_NOTICE"
    PROBATION_MINIMUM_WAGE = "PROBATION_MINIMUM_WAGE"
    EXTRA_WORK = "EXTRA_WORK"
    UNSUPPORTED = "UNSUPPORTED"


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ChatIntent
    topic: ChatTopic


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    terms: ContractTerms
    worker_birth_date: str | None = None

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("질문을 입력해 주세요.")
        return stripped


class EvidenceKind(str, Enum):
    CONTRACT = "CONTRACT"
    LEGAL = "LEGAL"
    CALCULATION = "CALCULATION"


class ChatEvidence(BaseModel):
    kind: EvidenceKind
    title: str
    detail: str


class ConditionGroups(BaseModel):
    met: list[str]
    unmet: list[str]
    needs_check: list[str]


class RetrievedKnowledge(BaseModel):
    """응답을 생성할 때 실제로 검색된 검증 KB 항목."""

    kb_id: str
    title: str
    source_ids: list[str]
    score: float = Field(ge=0, le=1)


class AnswerMode(str, Enum):
    DETERMINISTIC_TEMPLATE = "DETERMINISTIC_TEMPLATE"
    GROUNDED_GENERATION = "GROUNDED_GENERATION"
    NATURAL_GROUNDED_GENERATION = "NATURAL_GROUNDED_GENERATION"
    OPENAI_GROUNDED_GENERATION = "OPENAI_GROUNDED_GENERATION"
    OPENAI_NATURAL_REALIZATION = "OPENAI_NATURAL_REALIZATION"
    UPSTAGE_NATURAL_REALIZATION = "UPSTAGE_NATURAL_REALIZATION"


class GenerationFactKind(str, Enum):
    DETERMINISTIC_CONCLUSION = "DETERMINISTIC_CONCLUSION"
    MET = "MET"
    UNMET = "UNMET"
    NEEDS_CHECK = "NEEDS_CHECK"
    LIMITATION = "LIMITATION"


class GenerationFactCard(BaseModel):
    """Solar에 전달할 수 있는 비식별·결정론적 사실 한 건."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(pattern=r"^FACT-[A-Z0-9-]+$")
    kind: GenerationFactKind
    text: str = Field(min_length=1, max_length=300)


class GenerationTransferScope(BaseModel):
    """외부 모델 전송 범위를 API 입력 자체에 명시한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_payload: tuple[
        Literal[
            "SELECTION_KEYS",
            "VERIFIED_KB_SENTENCES",
            "DETERMINISTIC_FACT_CARDS",
        ],
        ...,
    ] = (
        "SELECTION_KEYS",
        "VERIFIED_KB_SENTENCES",
        "DETERMINISTIC_FACT_CARDS",
    )
    question_original_sent: Literal[False] = False
    contract_original_sent: Literal[False] = False
    personal_information_sent: Literal[False] = False
    worker_birth_date_sent: Literal[False] = False
    workplace_sent: Literal[False] = False


class GroundedGenerationInput(BaseModel):
    """개인정보와 계약 원문을 제외한 생성용 허용 컨텍스트."""

    model_config = ConfigDict(extra="forbid")

    selection_keys: list[str]
    candidate_sentences: dict[str, str]
    sentence_source_ids: dict[str, list[str]]
    allowed_source_ids: list[str]
    fact_cards: list[GenerationFactCard] = Field(default_factory=list, max_length=12)
    transfer_scope: GenerationTransferScope = Field(
        default_factory=GenerationTransferScope
    )


class NaturalRealizationInput(BaseModel):
    """일반 질문 자연어 연결에 쓰는 비식별·승인 사실 컨텍스트."""

    model_config = ConfigDict(extra="forbid")

    selection_keys: list[str]
    fact_cards: list[GenerationFactCard] = Field(min_length=1, max_length=4)
    transfer_scope: GenerationTransferScope = Field(
        default_factory=GenerationTransferScope
    )


class NaturalAnswerRealization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    natural_answer_template: str = Field(min_length=1, max_length=1200)
    required_fact_ids: list[str] = Field(min_length=1, max_length=4)


class NaturalSentenceConnector(str, Enum):
    CONTRACT_SUMMARY = "CONTRACT_SUMMARY"
    ADDITIONAL_CHECK = "ADDITIONAL_CHECK"
    LEGAL_CONTEXT = "LEGAL_CONTEXT"


class GroundedNaturalSentence(BaseModel):
    """자유 사실 서술 없이 문장 조립 방법과 근거만 고르는 Solar 출력."""

    model_config = ConfigDict(extra="forbid")

    connector: NaturalSentenceConnector
    fact_ids: list[str] = Field(min_length=1, max_length=5)
    kb_sentence_id: str
    source_ids: list[str] = Field(min_length=1, max_length=5)


class GroundedGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_ids: list[str] = Field(min_length=1, max_length=3)
    source_ids: list[str] = Field(min_length=1, max_length=5)
    natural_sentences: list[GroundedNaturalSentence] = Field(
        default_factory=list,
        max_length=3,
    )
    natural_answer_template: str | None = Field(default=None, max_length=1600)
    required_fact_ids: list[str] = Field(default_factory=list, max_length=12)


class OpenAIConnectorKind(str, Enum):
    CONTRACT_CONTEXT = "CONTRACT_CONTEXT"
    ADDITIONAL_CONTEXT = "ADDITIONAL_CONTEXT"
    LEGAL_CONTEXT = "LEGAL_CONTEXT"


class OpenAIClaimKind(str, Enum):
    CONFIRMED_FACT = "CONFIRMED_FACT"
    CONDITION_MET = "CONDITION_MET"
    CONDITION_UNMET = "CONDITION_UNMET"
    NEEDS_CHECK = "NEEDS_CHECK"


class OpenAIExplanationStep(BaseModel):
    """GPT가 고른 승인된 연결·주장 종류와 근거 ID만 담는 설명 계획."""

    model_config = ConfigDict(extra="forbid")

    connector_kind: OpenAIConnectorKind
    claim_kind: OpenAIClaimKind
    fact_ids: list[str] = Field(min_length=1, max_length=5)
    kb_sentence_ids: list[str] = Field(min_length=1, max_length=3)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class OpenAIGroundedGeneration(BaseModel):
    """strict 설명 계획과 선택적 사실-자리표시자 자연어 템플릿."""

    model_config = ConfigDict(extra="forbid")

    steps: list[OpenAIExplanationStep] = Field(min_length=1, max_length=3)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    natural_answer_template: str | None = Field(default=None, max_length=1600)
    required_fact_ids: list[str] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    intent: ChatIntent
    topic: ChatTopic
    answer: str
    evidence: list[ChatEvidence]
    limitation: str | None = None
    condition_groups: ConditionGroups | None = None
    retrieved_knowledge: list[RetrievedKnowledge] = Field(default_factory=list)
    answer_mode: AnswerMode = AnswerMode.DETERMINISTIC_TEMPLATE
    suggested_questions: list[str]
