"""검증 KB 검색과 근거 제한 생성의 안전 오케스트레이션."""

from app.chat.features import SafeQuestionFeatures
from app.chat.knowledge import KnowledgeEntry, retrieve_knowledge
from app.chat.models import (
    AnswerMode,
    ChatIntent,
    ChatResponse,
    GroundedGenerationInput,
    GroundedGenerationOutput,
)
from app.chat.provider import ChatProviderError, generate_grounded_explanation


def _generation_context(
    response: ChatResponse,
    entries: list[KnowledgeEntry],
    features: SafeQuestionFeatures,
) -> GroundedGenerationInput:
    source_ids = sorted(
        {source_id for entry in entries for source_id in entry.source_ids}
    )
    return GroundedGenerationInput(
        selection_keys=[
            response.intent.value,
            response.topic.value,
            *(signal.value for signal in features.signals),
        ],
        candidate_sentences={f"{entry.kb_id}-SUMMARY": entry.text for entry in entries},
        sentence_source_ids={
            f"{entry.kb_id}-SUMMARY": list(entry.source_ids) for entry in entries
        },
        allowed_source_ids=source_ids,
    )


def generation_is_grounded(
    generated: GroundedGenerationOutput,
    context: GroundedGenerationInput,
) -> bool:
    """모델이 승인된 문장·출처 ID만 선택했는지 fail-closed로 확인한다.

    자유 텍스트를 모델 출력으로 받지 않기 때문에 비숫자 법률 사실을 포함한 새 사실이
    사용자에게 도달할 경로가 없다.
    """

    selected_sentences = set(generated.sentence_ids)
    if len(selected_sentences) != len(generated.sentence_ids):
        return False
    if not selected_sentences.issubset(context.candidate_sentences):
        return False

    used_sources = set(generated.source_ids)
    expected_sources = {
        source_id
        for sentence_id in generated.sentence_ids
        for source_id in context.sentence_source_ids[sentence_id]
    }
    return (
        len(used_sources) == len(generated.source_ids)
        and bool(used_sources)
        and used_sources == expected_sources
    )


def _render_selected_explanation(
    generated: GroundedGenerationOutput,
    context: GroundedGenerationInput,
) -> str:
    sentences = [context.candidate_sentences[item] for item in generated.sentence_ids]
    citations = ", ".join(f"[{item}]" for item in generated.source_ids)
    return f"{' '.join(sentences)} {citations}"


async def enrich_with_grounded_rag(
    *,
    question: str,
    features: SafeQuestionFeatures,
    response: ChatResponse,
) -> ChatResponse:
    """관련 KB가 있을 때만 생성하고 모든 실패를 기존 템플릿으로 폴백한다."""

    if response.intent == ChatIntent.OUT_OF_SCOPE:
        return response

    matches = retrieve_knowledge(
        question,
        topic=response.topic,
        signals=features.signals,
    )
    if not matches:
        return response

    entries = [entry for entry, _ in matches]
    trace = [item for _, item in matches]
    fallback = response.model_copy(update={"retrieved_knowledge": trace})
    context = _generation_context(response, entries, features)

    try:
        generated = await generate_grounded_explanation(context)
    except ChatProviderError:
        return fallback
    if not generation_is_grounded(generated, context):
        return fallback

    explanation = _render_selected_explanation(generated, context)

    return response.model_copy(
        update={
            "answer": f"{response.answer}\n\n{explanation}",
            "retrieved_knowledge": trace,
            "answer_mode": AnswerMode.GROUNDED_GENERATION,
        }
    )
