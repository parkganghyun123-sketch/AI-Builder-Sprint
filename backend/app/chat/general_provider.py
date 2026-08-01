"""일반 질문용 비식별 설명 계획 제공자.

모델은 질문 원문이나 개인정보를 받지 않고, 승인된 블록·행동 ID와 순서만 고른다.
사용자에게 보이는 문장은 서버가 승인 원문으로 렌더링한다.
"""

import json
from enum import Enum

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.chat.openai_provider import OpenAIProviderError, _request_structured
from app.config import settings

UPSTAGE_CHAT_URL = "https://api.upstage.ai/v1/chat/completions"
UPSTAGE_CHAT_MODEL = "solar-pro3"


class GeneralStage(str, Enum):
    BEFORE_WORK = "BEFORE_WORK"
    WORK_STARTED = "WORK_STARTED"
    UNKNOWN = "UNKNOWN"


class GeneralDocumentStatus(str, Enum):
    NOT_WRITTEN = "NOT_WRITTEN"
    NOT_RECEIVED = "NOT_RECEIVED"
    UNKNOWN = "UNKNOWN"


class GeneralBlockId(str, Enum):
    CORE_STANDARD = "CORE_STANDARD"
    BEFORE_WORK = "BEFORE_WORK"
    WORK_STARTED = "WORK_STARTED"
    CHECK_REQUIRED = "CHECK_REQUIRED"
    NEXT_ACTION = "NEXT_ACTION"
    CORE_LIMITATION = "CORE_LIMITATION"
    LEGAL_INDICATORS = "LEGAL_INDICATORS"
    CONTRACT_SCOPE = "CONTRACT_SCOPE"
    NEEDS_CHECK = "NEEDS_CHECK"


class GeneralActionId(str, Enum):
    DIRECT_INPUT = "DIRECT_INPUT"
    STANDARD_FORM = "STANDARD_FORM"
    GUIDANCE_1350 = "GUIDANCE_1350"
    CONTRACT_UPLOAD = "CONTRACT_UPLOAD"
    NONE = "NONE"


class GeneralPlanContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    signals: list[str]
    stage: GeneralStage
    document_status: GeneralDocumentStatus
    allowed_block_ids: list[GeneralBlockId]
    block_source_ids: dict[GeneralBlockId, list[str]]
    allowed_action_ids: list[GeneralActionId]


class GeneralResponsePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_ids: list[GeneralBlockId] = Field(min_length=1, max_length=5)
    source_ids: list[str] = Field(max_length=5)
    action_id: GeneralActionId


GENERAL_PLAN_INSTRUCTIONS = """당신은 FairSign 일반 질문 설명 계획 선택기입니다.
입력은 질문 원문이 아니라 비식별 신호, 단계, 문서 상태와 승인 ID 목록입니다.
- 법적 판단, 계산, 문장 작성을 하지 마세요.
- allowed_block_ids에서 필요한 블록을 골라 이해하기 좋은 순서로 배열하세요.
- WRITTEN_CONTRACT에서 stage가 UNKNOWN이면 BEFORE_WORK와 WORK_STARTED를 넣지 말고, 핵심 의무와 중립적인 다음 행동만 고르세요.
- source_ids는 선택 블록에 매핑된 출처 ID의 정확한 합집합이어야 합니다.
- action_id는 allowed_action_ids 중 하나만 고르세요.
- 입력에 없는 ID, 필드, 자유 텍스트를 만들지 마세요.
"""

GENERAL_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "block_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "string",
                "enum": [item.value for item in GeneralBlockId],
            },
        },
        "source_ids": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "action_id": {
            "type": "string",
            "enum": [item.value for item in GeneralActionId],
        },
    },
    "required": ["block_ids", "source_ids", "action_id"],
}


class GeneralProviderError(Exception):
    """원문이나 제공자 응답을 노출하지 않는 안전한 오류."""


async def generate_openai_general_plan(
    context: GeneralPlanContext,
) -> GeneralResponsePlan:
    try:
        return await _request_structured(
            instructions=GENERAL_PLAN_INSTRUCTIONS,
            input_data=context.model_dump(mode="json"),
            schema_name="fairsign_general_question_plan",
            schema=GENERAL_PLAN_SCHEMA,
            output_model=GeneralResponsePlan,
        )
    except OpenAIProviderError:
        raise GeneralProviderError(
            "일반 질문 계획 서비스를 사용할 수 없습니다."
        ) from None


async def generate_upstage_general_plan(
    context: GeneralPlanContext,
) -> GeneralResponsePlan:
    if not settings.upstage_api_key:
        raise GeneralProviderError("일반 질문 계획 서비스를 사용할 수 없습니다.")

    payload = {
        "model": UPSTAGE_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": GENERAL_PLAN_INSTRUCTIONS},
            {"role": "user", "content": context.model_dump_json()},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                UPSTAGE_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {settings.upstage_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError:
        raise GeneralProviderError(
            "일반 질문 계획 서비스를 사용할 수 없습니다."
        ) from None

    if response.status_code >= 400:
        raise GeneralProviderError("일반 질문 계획 서비스를 사용할 수 없습니다.")
    try:
        body = response.json()
        raw = body["choices"][0]["message"]["content"]
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return GeneralResponsePlan.model_validate(parsed)
    except (KeyError, IndexError, TypeError, ValueError, ValidationError):
        raise GeneralProviderError(
            "일반 질문 계획 서비스를 사용할 수 없습니다."
        ) from None
