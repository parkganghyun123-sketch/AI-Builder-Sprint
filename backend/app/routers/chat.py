"""근거 추적형 계약 비서 API."""

import logging

from fastapi import APIRouter, HTTPException

from app.chat.answers import (
    build_response,
    is_fail_closed_question,
    out_of_scope_response,
)
from app.chat.features import classification_is_consistent, extract_safe_features
from app.chat.models import ChatRequest, ChatResponse
from app.chat.provider import ChatProviderError, classify_features
from app.chat.rag import enrich_with_grounded_rag

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """질문을 AI로 분류하고 계약·검증 결과만으로 답변을 조립한다."""

    if is_fail_closed_question(body.question):
        return out_of_scope_response()

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
    )
    return await enrich_with_grounded_rag(
        question=body.question,
        features=features,
        response=deterministic,
    )
