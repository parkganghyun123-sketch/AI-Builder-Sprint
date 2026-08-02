"""계약 비서 API.

``/chat``은 폐쇄형 특징 분류와 검증된 KB 검색을 사용하는 근거형 응답을,
``/contracts/chat``은 확인된 계약 조건과 검증 보고서만 조회하는 계약 비서를 제공한다.
두 경로 모두 질문 원문이나 계약 내용을 저장하지 않는다.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.chat.answers import (
    build_response,
    build_small_talk_response,
    is_fail_closed_question,
    out_of_scope_response,
)
from app.chat.features import classification_is_consistent, extract_safe_features
from app.chat.models import ChatRequest, ChatResponse
from app.chat.provider import ChatProviderError, classify_features
from app.chat.rag import enrich_with_grounded_rag
from app.chat.service import answer
from app.schemas import ContractChatRequest, ContractChatResponse
from app.validation.rules import validate

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """질문을 AI로 분류하고 계약·검증 결과만으로 답변을 조립한다."""

    if is_fail_closed_question(body.question):
        return out_of_scope_response()

    small_talk = build_small_talk_response(body.question)
    if small_talk is not None:
        return small_talk

    features = extract_safe_features(body.question)
    if features is None:
        return out_of_scope_response()

    try:
        classification = await classify_features(features)
    except ChatProviderError as error:
        # 질문, 계약 조건, 제공자 본문은 로그와 응답에 남기지 않는다.
        log.warning("챗봇 분류 실패: error_type=%s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="질문 분류 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from None

    if not classification_is_consistent(classification, features):
        return out_of_scope_response()

    deterministic = build_response(
        classification,
        body.terms,
        body.worker_birth_date,
        body.question,
    )
    return await enrich_with_grounded_rag(
        question=body.question,
        features=features,
        response=deterministic,
    )


@router.post("/contracts/chat", response_model=ContractChatResponse)
async def contract_chat(body: ContractChatRequest) -> ContractChatResponse:
    """확인된 계약 조건과 검증 결과를 검색해 근거가 있는 답변만 반환한다."""
    report = validate(body.terms, worker_birth_date=body.worker_birth_date)
    return answer(body.question, body.terms, report)
