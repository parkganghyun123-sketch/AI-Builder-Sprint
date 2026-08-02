"""검증 KB 검색과 근거 제한 생성의 안전 오케스트레이션."""

from app.chat.features import SafeQuestionFeatures
from app.chat.knowledge import KnowledgeEntry, retrieve_knowledge
from app.chat.models import (
    FACT_PLACEHOLDER_RE,
    AnswerMode,
    ChatIntent,
    ChatResponse,
    ChatTopic,
    GenerationFactCard,
    GenerationFactKind,
    GroundedGenerationInput,
    GroundedGenerationOutput,
    NaturalSentenceConnector,
    OpenAIClaimKind,
    OpenAIConnectorKind,
    OpenAIGroundedGeneration,
    natural_template_uses_approved_connectives,
)
from app.chat.openai_provider import OpenAIProviderError, generate_openai_explanation
from app.chat.provider import ChatProviderError, generate_grounded_explanation
from app.config import settings

_OPENAI_ALLOWED_INTENTS = {
    ChatIntent.CALCULATION,
    ChatIntent.LEGAL_STANDARD,
    ChatIntent.MISSING_CLAUSE,
}
_OPENAI_ALLOWED_TOPICS = {
    ChatTopic.WEEKLY_HOLIDAY,
    ChatTopic.MINIMUM_WAGE,
    ChatTopic.BREAK_TIME,
    ChatTopic.WORKING_HOURS,
    ChatTopic.MISSING_CLAUSES,
    ChatTopic.SEVERANCE_PAY,
    ChatTopic.SOCIAL_INSURANCE,
    ChatTopic.ANNUAL_LEAVE,
    ChatTopic.DISMISSAL_NOTICE,
    ChatTopic.PROBATION_MINIMUM_WAGE,
}


def _fact_cards(response: ChatResponse) -> list[GenerationFactCard]:
    """자연어 설명에 꼭 필요한 비식별 결정론적 사실만 만든다."""

    cards = [
        GenerationFactCard(
            fact_id="FACT-CONCLUSION",
            kind=GenerationFactKind.DETERMINISTIC_CONCLUSION,
            text=response.answer,
        )
    ]
    if response.limitation:
        cards.append(
            GenerationFactCard(
                fact_id="FACT-LIMITATION",
                kind=GenerationFactKind.LIMITATION,
                text=response.limitation,
            )
        )
    if response.condition_groups is None:
        return cards

    groups = (
        ("MET", GenerationFactKind.MET, response.condition_groups.met),
        ("UNMET", GenerationFactKind.UNMET, response.condition_groups.unmet),
        (
            "NEEDS-CHECK",
            GenerationFactKind.NEEDS_CHECK,
            response.condition_groups.needs_check,
        ),
    )
    for prefix, kind, items in groups:
        for index, item in enumerate(items, start=1):
            cards.append(
                GenerationFactCard(
                    fact_id=f"FACT-{prefix}-{index}",
                    kind=kind,
                    text=item,
                )
            )
            if len(cards) == 12:
                return cards
    return cards


def render_grounded_natural_answer(
    template: str | None,
    required_fact_ids: list[str],
    context: GroundedGenerationInput,
) -> str | None:
    """사실 자리표시자 외의 새 주장·숫자를 거절하고 자연어 연결만 허용한다."""

    if not template or not template.strip().startswith("{{FACT-CONCLUSION}}"):
        return None
    expected = [card.fact_id for card in context.fact_cards]
    if len(required_fact_ids) != len(set(required_fact_ids)) or set(
        required_fact_ids
    ) != set(expected):
        return None
    placeholders = FACT_PLACEHOLDER_RE.findall(template)
    if len(placeholders) != len(set(placeholders)) or set(placeholders) != set(
        expected
    ):
        return None
    if not natural_template_uses_approved_connectives(template):
        return None
    rendered = template
    facts = {card.fact_id: card.text for card in context.fact_cards}
    for fact_id in placeholders:
        rendered = rendered.replace(f"{{{{{fact_id}}}}}", facts[fact_id])
    return " ".join(rendered.split())


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
        fact_cards=_fact_cards(response),
    )


def generation_is_grounded(
    generated: GroundedGenerationOutput,
    context: GroundedGenerationInput,
) -> bool:
    """모델이 승인된 문장·출처 ID만 선택했는지 fail-closed로 확인한다.

    승인 문장 선택 경로를 검사한다. 선택적 자연어 템플릿은 별도 검사에서 숫자·URL·
    확정 결론과 필수 사실 누락을 차단한다.
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


def natural_generation_is_grounded(
    generated: GroundedGenerationOutput,
    context: GroundedGenerationInput,
) -> bool:
    """조립 계획이 허용 사실·KB·출처 경계를 벗어나면 전부 폐기한다.

    이 기존 문장 조립 계획은 ID 관계만 검사한다. 선택적 자연어 템플릿은
    ``render_grounded_natural_answer``가 별도로 fail-closed 검증한다.
    """

    if not generated.natural_sentences:
        return False

    allowed_facts = {card.fact_id for card in context.fact_cards}
    selected_sentences = set(generated.sentence_ids)

    for sentence in generated.natural_sentences:
        if len(sentence.fact_ids) != len(set(sentence.fact_ids)):
            return False
        if len(sentence.source_ids) != len(set(sentence.source_ids)):
            return False
        if not set(sentence.fact_ids).issubset(allowed_facts):
            return False
        if sentence.kb_sentence_id not in selected_sentences:
            return False
        expected_sources = set(context.sentence_source_ids[sentence.kb_sentence_id])
        if set(sentence.source_ids) != expected_sources:
            return False
    return True


def _render_natural_explanation(
    generated: GroundedGenerationOutput,
    context: GroundedGenerationInput,
) -> str:
    facts = {card.fact_id: card.text for card in context.fact_cards}
    introductions = {
        NaturalSentenceConnector.CONTRACT_SUMMARY: "계약 내용을 기준으로 정리하면, ",
        NaturalSentenceConnector.ADDITIONAL_CHECK: "추가로 확인할 항목은 ",
        NaturalSentenceConnector.LEGAL_CONTEXT: "관련 법정 기준과 함께 보면, ",
    }
    rendered: list[str] = []
    for sentence in generated.natural_sentences:
        exact_facts = "; ".join(facts[fact_id] for fact_id in sentence.fact_ids)
        ending = "" if exact_facts.endswith((".", "?", "!")) else "."
        rendered.append(f"{introductions[sentence.connector]}{exact_facts}{ending}")

    # 법령 출처가 계약별 사실을 직접 뒷받침하는 것처럼 보이지 않도록, 출처 표시는
    # 실제로 그 출처에 매핑된 KB 문장 바로 뒤에만 붙인다.
    for sentence_id in generated.sentence_ids:
        citations = " ".join(
            f"[{item}]" for item in context.sentence_source_ids[sentence_id]
        )
        rendered.append(
            f"공식 근거: {context.candidate_sentences[sentence_id]} {citations}"
        )
    return " ".join(rendered)


def openai_generation_is_grounded(
    generated: OpenAIGroundedGeneration,
    context: GroundedGenerationInput,
) -> bool:
    """자유 텍스트 없는 GPT 계획의 enum·사실·KB·출처 관계를 검사한다."""

    facts = {card.fact_id: card for card in context.fact_cards}
    allowed_kb = context.candidate_sentences
    expected_all_sources: set[str] = set()
    allowed_fact_kinds = {
        OpenAIClaimKind.CONFIRMED_FACT: {GenerationFactKind.DETERMINISTIC_CONCLUSION},
        OpenAIClaimKind.CONDITION_MET: {GenerationFactKind.MET},
        OpenAIClaimKind.CONDITION_UNMET: {GenerationFactKind.UNMET},
        OpenAIClaimKind.NEEDS_CHECK: {GenerationFactKind.NEEDS_CHECK},
    }

    if len(generated.source_ids) != len(set(generated.source_ids)):
        return False

    for step in generated.steps:
        if len(step.fact_ids) != len(set(step.fact_ids)):
            return False
        if len(step.kb_sentence_ids) != len(set(step.kb_sentence_ids)):
            return False
        if len(step.source_ids) != len(set(step.source_ids)):
            return False
        if not set(step.fact_ids).issubset(facts):
            return False
        if not set(step.kb_sentence_ids).issubset(allowed_kb):
            return False
        if any(
            facts[fact_id].kind not in allowed_fact_kinds[step.claim_kind]
            for fact_id in step.fact_ids
        ):
            return False
        step_sources = {
            source_id
            for kb_id in step.kb_sentence_ids
            for source_id in context.sentence_source_ids[kb_id]
        }
        if set(step.source_ids) != step_sources:
            return False
        expected_all_sources.update(step_sources)

    return set(generated.source_ids) == expected_all_sources


def _render_openai_explanation(
    generated: OpenAIGroundedGeneration,
    context: GroundedGenerationInput,
) -> str:
    """GPT 계획을 승인 템플릿·정확한 사실 원문·KB 원문으로만 렌더링한다."""

    facts = {card.fact_id: card.text for card in context.fact_cards}
    connectors = {
        OpenAIConnectorKind.CONTRACT_CONTEXT: "계약 내용을 기준으로 살펴보면,",
        OpenAIConnectorKind.ADDITIONAL_CONTEXT: "함께 확인할 내용을 정리하면,",
        OpenAIConnectorKind.LEGAL_CONTEXT: "관련 기준과 함께 살펴보면,",
    }
    claim_labels = {
        OpenAIClaimKind.CONFIRMED_FACT: "확인된 내용은",
        OpenAIClaimKind.CONDITION_MET: "계약에서 확인된 조건은",
        OpenAIClaimKind.CONDITION_UNMET: "기준과 다른 조건은",
        OpenAIClaimKind.NEEDS_CHECK: "추가 확인할 내용은",
    }
    rendered_steps: list[str] = []
    for step in generated.steps:
        exact_facts = "; ".join(facts[fact_id] for fact_id in step.fact_ids)
        ending = "" if exact_facts.endswith((".", "?", "!")) else "."
        rendered_steps.append(
            f"{connectors[step.connector_kind]} "
            f"{claim_labels[step.claim_kind]} {exact_facts}{ending}"
        )
    kb_ids = list(
        dict.fromkeys(
            kb_id for step in generated.steps for kb_id in step.kb_sentence_ids
        )
    )
    grounded = rendered_steps
    for kb_id in kb_ids:
        citations = " ".join(
            f"[{source_id}]" for source_id in context.sentence_source_ids[kb_id]
        )
        grounded.append(f"공식 근거: {context.candidate_sentences[kb_id]} {citations}")
    return " ".join(grounded)


async def _try_openai_generation(
    response: ChatResponse,
    context: GroundedGenerationInput,
) -> tuple[str, bool] | None:
    """GPT 계획과 ID 관계가 모두 유효할 때만 서버 렌더링 설명을 반환한다."""

    if (
        not settings.openai_api_key
        or response.intent not in _OPENAI_ALLOWED_INTENTS
        or response.topic not in _OPENAI_ALLOWED_TOPICS
    ):
        return None
    try:
        generated = await generate_openai_explanation(context)
        if not openai_generation_is_grounded(generated, context):
            return None
    except (OpenAIProviderError, KeyError):
        return None
    if generated.natural_answer_template is not None:
        natural = render_grounded_natural_answer(
            generated.natural_answer_template,
            generated.required_fact_ids,
            context,
        )
        return (natural, True) if natural is not None else None
    return _render_openai_explanation(generated, context), False


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

    openai_result = await _try_openai_generation(response, context)
    if openai_result is not None:
        openai_text, is_natural = openai_result
        return response.model_copy(
            update={
                "answer": (
                    openai_text if is_natural else f"{response.answer}\n\n{openai_text}"
                ),
                "retrieved_knowledge": trace,
                "answer_mode": (
                    AnswerMode.OPENAI_NATURAL_REALIZATION
                    if is_natural
                    else AnswerMode.OPENAI_GROUNDED_GENERATION
                ),
            }
        )

    try:
        generated = await generate_grounded_explanation(context)
    except ChatProviderError:
        return fallback
    if not generation_is_grounded(generated, context):
        return fallback

    if generated.natural_answer_template is not None:
        natural = render_grounded_natural_answer(
            generated.natural_answer_template,
            generated.required_fact_ids,
            context,
        )
        if natural is None:
            return fallback
        return response.model_copy(
            update={
                "answer": natural,
                "retrieved_knowledge": trace,
                "answer_mode": AnswerMode.UPSTAGE_NATURAL_REALIZATION,
            }
        )

    if generated.natural_sentences:
        if not natural_generation_is_grounded(generated, context):
            return fallback
        explanation = _render_natural_explanation(generated, context)
        answer_mode = AnswerMode.NATURAL_GROUNDED_GENERATION
    else:
        # 기존 승인 문장 선택 경로를 유지해 목 제공자와 안전 폴백을 지원한다.
        explanation = _render_selected_explanation(generated, context)
        answer_mode = AnswerMode.GROUNDED_GENERATION

    return response.model_copy(
        update={
            "answer": f"{response.answer}\n\n{explanation}",
            "retrieved_knowledge": trace,
            "answer_mode": answer_mode,
        }
    )
