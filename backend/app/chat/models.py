"""챗봇 내부·API 모델."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ContractTerms


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
    UNSUPPORTED = "UNSUPPORTED"


class Classification(BaseModel):
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


class GroundedGenerationInput(BaseModel):
    """개인정보와 계약 원문을 제외한 생성용 허용 컨텍스트."""

    selection_keys: list[str]
    candidate_sentences: dict[str, str]
    sentence_source_ids: dict[str, list[str]]
    allowed_source_ids: list[str]


class GroundedGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_ids: list[str] = Field(min_length=1, max_length=3)
    source_ids: list[str] = Field(min_length=1, max_length=5)


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
