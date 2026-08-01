"""Upstage Solar 질문 분류·근거 제한 설명 제공자.

분류에는 폐쇄형 특징만 전달한다. 설명 선택에는 계약 원문·파생 지표·질문 원문·생년월일·
개인정보를 전달하지 않고, 비식별 선택 키와 검증 KB 후보만 전달한다. Solar는 답변의
법적 판단이나 계산을 만들지 않는다.
"""

import json

import httpx
from pydantic import ValidationError

from app.chat.features import SafeQuestionFeatures
from app.chat.models import (
    Classification,
    GroundedGenerationInput,
    GroundedGenerationOutput,
)
from app.config import settings

UPSTAGE_CHAT_URL = "https://api.upstage.ai/v1/chat/completions"
UPSTAGE_CHAT_MODEL = "solar-pro3"

CLASSIFICATION_INSTRUCTIONS = """당신은 근로계약 질문 분류기입니다.
답변하거나 계산하지 말고 JSON 하나만 반환하세요.
intent는 FIELD_LOOKUP, CALCULATION, MISSING_CLAUSE, LEGAL_STANDARD,
OUT_OF_SCOPE 중 하나입니다.
topic은 WEEKLY_HOLIDAY, SEVERANCE_PAY, SOCIAL_INSURANCE, ANNUAL_LEAVE,
DISMISSAL_NOTICE, PROBATION_MINIMUM_WAGE, MINIMUM_WAGE, BREAK_TIME, WORKING_HOURS, WAGE,
PAYDAY, CONTRACT_PERIOD, WORKPLACE, JOB, MISSING_CLAUSES, UNSUPPORTED 중
하나입니다.
개별 분쟁, 신고, 소송, 부당해고, 대타·개근 등 추가 사실이 필요한 판단,
계약과 무관한 질문은 OUT_OF_SCOPE/UNSUPPORTED로 분류하세요.
형식: {"intent":"...","topic":"..."}
"""

GROUNDED_GENERATION_INSTRUCTIONS = """당신은 FairSign의 설명문 작성기입니다.
입력에는 비식별 분류 키와 검증된 KB 승인 문장만 있습니다.
- 법적 판단, 자격 확정, 계산, 새로운 문장을 만들지 마세요.
- selection_keys와 가장 관련 있는 candidate_sentences의 ID만 고르세요.
- 선택한 문장의 근거인 source_id만 allowed_source_ids에서 고르세요.
- 입력에 없는 ID나 값을 만들지 마세요.
JSON 하나만 반환하세요.
형식: {"sentence_ids":["KB-...-SUMMARY"], "source_ids":["SRC-..."]}
"""


class ChatProviderError(Exception):
    """질문이나 제공자 응답을 노출하지 않는 안전한 제공자 오류."""


def _authorization_header() -> dict[str, str]:
    if not settings.upstage_api_key:
        raise ChatProviderError("챗봇 분류 서비스를 사용할 수 없습니다.")
    return {"Authorization": f"Bearer {settings.upstage_api_key}"}


async def classify_features(features: SafeQuestionFeatures) -> Classification:
    """로컬에서 추출한 폐쇄형 enum 특징만 Solar에 보내 분류한다."""

    payload = {
        "model": UPSTAGE_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": CLASSIFICATION_INSTRUCTIONS},
            {"role": "user", "content": features.model_dump_json()},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                UPSTAGE_CHAT_URL,
                headers={**_authorization_header(), "Content-Type": "application/json"},
                json=payload,
            )
    except ChatProviderError:
        raise
    except httpx.HTTPError:
        raise ChatProviderError("챗봇 분류 서비스를 사용할 수 없습니다.") from None

    if response.status_code >= 400:
        raise ChatProviderError("챗봇 분류 서비스를 사용할 수 없습니다.")

    try:
        body = response.json()
        raw_content = body["choices"][0]["message"]["content"]
        parsed = (
            json.loads(raw_content) if isinstance(raw_content, str) else raw_content
        )
        return Classification.model_validate(parsed)
    except (KeyError, IndexError, TypeError, ValueError, ValidationError):
        raise ChatProviderError("챗봇 분류 서비스를 사용할 수 없습니다.") from None


async def generate_grounded_explanation(
    context: GroundedGenerationInput,
) -> GroundedGenerationOutput:
    """비식별 분류 키와 검증된 KB만 Solar에 보내 승인 문장을 선택한다."""

    payload = {
        "model": UPSTAGE_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": GROUNDED_GENERATION_INSTRUCTIONS},
            {"role": "user", "content": context.model_dump_json()},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                UPSTAGE_CHAT_URL,
                headers={**_authorization_header(), "Content-Type": "application/json"},
                json=payload,
            )
    except ChatProviderError:
        raise
    except httpx.HTTPError:
        raise ChatProviderError("챗봇 설명 서비스를 사용할 수 없습니다.") from None

    if response.status_code >= 400:
        raise ChatProviderError("챗봇 설명 서비스를 사용할 수 없습니다.")

    try:
        body = response.json()
        raw_content = body["choices"][0]["message"]["content"]
        parsed = (
            json.loads(raw_content) if isinstance(raw_content, str) else raw_content
        )
        return GroundedGenerationOutput.model_validate(parsed)
    except (KeyError, IndexError, TypeError, ValueError, ValidationError):
        raise ChatProviderError("챗봇 설명 서비스를 사용할 수 없습니다.") from None
