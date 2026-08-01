"""OpenAI Responses API 기반 근거 제한 설명·자연어 연결 제공자.

질문·계약서 원문·개인정보는 받지도 보내지도 않는다. 호출 입력은 비식별 선택 키,
코드가 확정한 사실 카드, 검증된 KB 문장과 그 출처 매핑으로 제한하며 모든 요청은
``store: false``다. 자연어는 필수 사실 자리표시자 사이 연결만 허용하고 서버가 검증한다.
"""

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.chat.models import (
    APPROVED_NATURAL_CONNECTIVES,
    GroundedGenerationInput,
    NaturalAnswerRealization,
    NaturalRealizationInput,
    OpenAIGroundedGeneration,
)
from app.config import settings

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

GENERATION_INSTRUCTIONS = """당신은 FairSign의 근로계약 설명 계획 선택기입니다.
입력에는 비식별 분류 키, 코드가 이미 확정한 사실 카드, 검증된 KB 문장만 있습니다.
사용자의 원 질문과 계약서 원문은 제공되지 않습니다.
- 문장을 작성하지 말고 승인된 enum과 입력에 있는 ID만 선택하세요.
- 법적 자격·위법 여부를 판단하거나 숫자를 계산하지 마세요.
- connector_kind는 CONTRACT_CONTEXT, ADDITIONAL_CONTEXT, LEGAL_CONTEXT 중 하나입니다.
- claim_kind는 CONFIRMED_FACT, CONDITION_MET, CONDITION_UNMET, NEEDS_CHECK 중 하나입니다.
- 각 단계에 fact_ids, kb_sentence_ids, 그 KB에 정확히 매핑된 source_ids를 넣으세요.
- 전체 source_ids에는 모든 단계에서 사용한 출처 ID를 중복 없이 모으세요.
- 자연스러운 답변을 만들 수 있으면 natural_answer_template에 FACT 자리표시자를 사용하세요.
- 템플릿은 {{FACT-CONCLUSION}}으로 시작하고 fact_cards의 모든 fact_id를 정확히 한 번씩 포함하세요.
- 자리표시자 밖에는 자연스러운 연결 표현만 쓰고 숫자, URL, 법률 사실·결론을 추가하지 마세요.
- required_fact_ids에는 사용한 모든 fact_id를 중복 없이 넣으세요.
- 입력에 없는 ID나 필드를 만들지 마세요. 설명 순서와 근거 선택만 동적으로 수행하세요.
"""
GENERATION_INSTRUCTIONS += (
    "\n자리표시자 사이에는 다음 서버 승인 연결구 중 하나만 정확히 복사해 사용하세요: "
    + json.dumps(sorted(APPROVED_NATURAL_CONNECTIVES), ensure_ascii=False)
)

GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "connector_kind": {
                        "type": "string",
                        "enum": [
                            "CONTRACT_CONTEXT",
                            "ADDITIONAL_CONTEXT",
                            "LEGAL_CONTEXT",
                        ],
                    },
                    "claim_kind": {
                        "type": "string",
                        "enum": [
                            "CONFIRMED_FACT",
                            "CONDITION_MET",
                            "CONDITION_UNMET",
                            "NEEDS_CHECK",
                        ],
                    },
                    "fact_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 5,
                        "items": {"type": "string"},
                    },
                    "kb_sentence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "string"},
                    },
                    "source_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "connector_kind",
                    "claim_kind",
                    "fact_ids",
                    "kb_sentence_ids",
                    "source_ids",
                ],
            },
        },
        "source_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"type": "string"},
        },
        "natural_answer_template": {
            "anyOf": [
                {"type": "string", "maxLength": 1600},
                {"type": "null"},
            ]
        },
        "required_fact_ids": {
            "type": "array",
            "maxItems": 12,
            "items": {"type": "string"},
        },
    },
    "required": [
        "steps",
        "source_ids",
        "natural_answer_template",
        "required_fact_ids",
    ],
}

NATURAL_REALIZATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "natural_answer_template": {"type": "string", "maxLength": 1200},
        "required_fact_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string"},
        },
    },
    "required": ["natural_answer_template", "required_fact_ids"],
}

NATURAL_REALIZATION_INSTRUCTIONS = """당신은 FairSign의 자연스러운 한국어 답변 연결기입니다.
입력의 fact_cards는 서버가 확정한 비식별 문장입니다.
- natural_answer_template은 {{FACT-ANSWER}}로 시작하세요.
- 모든 fact_id를 정확히 한 번씩 자리표시자로 넣으세요.
- 자리표시자 문장은 고치거나 요약하지 마세요.
- 자리표시자 밖에는 짧은 연결 표현만 쓰고 숫자, URL, 법률 사실·결론을 추가하지 마세요.
- required_fact_ids에 모든 fact_id를 중복 없이 넣으세요.
"""
NATURAL_REALIZATION_INSTRUCTIONS += (
    "\n자리표시자 사이에는 다음 서버 승인 연결구 중 하나만 정확히 복사해 사용하세요: "
    + json.dumps(sorted(APPROVED_NATURAL_CONNECTIVES), ensure_ascii=False)
)


class OpenAIProviderError(Exception):
    """민감한 요청·응답 내용을 노출하지 않는 안전한 제공자 오류."""


TModel = TypeVar("TModel", bound=BaseModel)


def _extract_output_text(body: object) -> str:
    """Responses output 배열 전체를 탐색해 유일한 완성 텍스트를 꺼낸다."""

    if not isinstance(body, dict) or body.get("status") == "incomplete":
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")
    output = body.get("output")
    if not isinstance(output, list):
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")

    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        if item.get("status") not in (None, "completed"):
            raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if len(texts) != 1:
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")
    return texts[0]


async def _request_structured(
    *,
    instructions: str,
    input_data: object,
    schema_name: str,
    schema: dict[str, Any],
    output_model: type[TModel],
) -> TModel:
    if not settings.openai_api_key:
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")

    payload = {
        "model": settings.openai_model,
        "store": False,
        "instructions": instructions,
        "input": json.dumps(input_data, ensure_ascii=False, separators=(",", ":")),
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError:
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.") from None

    if response.status_code >= 400:
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.")

    try:
        parsed = json.loads(_extract_output_text(response.json()))
        return output_model.model_validate(parsed)
    except (TypeError, ValueError, ValidationError):
        raise OpenAIProviderError("OpenAI 설명 서비스를 사용할 수 없습니다.") from None


async def generate_openai_explanation(
    context: GroundedGenerationInput,
) -> OpenAIGroundedGeneration:
    """비식별 사실·검증 KB만 보내 설명 계획과 선택적 자연어 연결을 생성한다."""

    return await _request_structured(
        instructions=GENERATION_INSTRUCTIONS,
        input_data=context.model_dump(mode="json"),
        schema_name="fairsign_grounded_generation",
        schema=GENERATION_SCHEMA,
        output_model=OpenAIGroundedGeneration,
    )


async def generate_openai_natural_answer(
    context: NaturalRealizationInput,
) -> NaturalAnswerRealization:
    return await _request_structured(
        instructions=NATURAL_REALIZATION_INSTRUCTIONS,
        input_data=context.model_dump(mode="json"),
        schema_name="fairsign_natural_answer",
        schema=NATURAL_REALIZATION_SCHEMA,
        output_model=NaturalAnswerRealization,
    )
