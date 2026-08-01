"""근거 추적형 챗봇 API 테스트. 실제 Upstage API는 호출하지 않는다."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat.features import QuerySignal, SafeQuestionFeatures, extract_safe_features
from app.chat.knowledge import VERIFIED_KNOWLEDGE, retrieve_knowledge
from app.chat.models import (
    ChatIntent,
    ChatTopic,
    Classification,
    GroundedGenerationInput,
    GroundedGenerationOutput,
)
from app.chat.provider import (
    ChatProviderError,
    classify_features,
    generate_grounded_explanation,
)
from app.routers import chat as chat_router
from app.schemas import Confidence, ContractTerms, ExtractedField, WageType


def field(value: str | int | None) -> ExtractedField:
    return ExtractedField(
        value=value,
        confidence=Confidence.NOT_FOUND if value is None else Confidence.HIGH,
        source_text=None,
    )


def terms(**overrides: ExtractedField) -> ContractTerms:
    values = {
        "contract_start": field("2026-08-01"),
        "contract_end": field("2026-12-31"),
        "workplace": field("부산시 가상매장"),
        "job_description": field("매장 보조"),
        "work_start_time": field("09:00"),
        "work_end_time": field("15:30"),
        "break_start_time": field("12:00"),
        "break_end_time": field("12:30"),
        "work_days_per_week": field(3),
        "weekly_holiday_day": field("일요일"),
        "wage_type": field(WageType.HOURLY.value),
        "wage_amount": field(10_320),
        "has_bonus": field("없음"),
        "other_allowance": field("없음"),
        "payday": field("매월 10일"),
        "payment_method": field("계좌이체"),
        "employer_business_name": field("가상상점"),
        "employer_phone": field(None),
        "employer_address": field(None),
        "employer_name": field("가상사업주"),
        "worker_address": field(None),
        "worker_contact": field(None),
        "worker_name": field("가상근로자"),
    }
    values.update(overrides)
    return ContractTerms(**values)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


def payload(contract: ContractTerms | None = None, *, question: str = "질문") -> dict:
    return {
        "question": question,
        "terms": (contract or terms()).model_dump(mode="json"),
        "worker_birth_date": None,
    }


def mock_classification(
    monkeypatch,
    intent: ChatIntent,
    topic: ChatTopic,
) -> None:
    async def fake_classify(features: SafeQuestionFeatures) -> Classification:
        return Classification(intent=intent, topic=topic)

    monkeypatch.setattr(chat_router, "classify_features", fake_classify)


def test_weekly_holiday_time_requirement_met(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.WEEKLY_HOLIDAY,
    )

    response = client.post("/chat", json=payload(question="나 지금 주휴받을 수 있나?"))

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "CALCULATION"
    assert body["topic"] == "WEEKLY_HOLIDAY"
    assert "시간 요건을 충족합니다" in body["answer"]
    assert body["limitation"] is None
    assert body["condition_groups"]["met"] == [
        "계약상 주 소정근로시간 18시간은 15시간 이상"
    ]
    assert "소정근로일 개근 여부" in body["condition_groups"]["needs_check"]
    assert (
        "계약과 실제 근무 내용의 일치 여부" in body["condition_groups"]["needs_check"]
    )
    assert "실제 주휴수당 지급 내역" in body["condition_groups"]["needs_check"]
    assert {item["kind"] for item in body["evidence"]} == {
        "CONTRACT",
        "LEGAL",
        "CALCULATION",
    }
    assert any("18시간 ≥ 15시간" in item["detail"] for item in body["evidence"])


def test_weekly_holiday_below_time_requirement(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.WEEKLY_HOLIDAY,
    )
    contract = terms(
        work_start_time=field("09:00"),
        work_end_time=field("13:00"),
        break_start_time=field(None),
        break_end_time=field(None),
        work_days_per_week=field(3),
    )

    response = client.post("/chat", json=payload(contract, question="주휴 요건 알려줘"))

    assert response.status_code == 200
    body = response.json()
    assert "시간 요건을 충족하지 않습니다" in body["answer"]
    assert body["condition_groups"]["unmet"] == [
        "계약상 주 소정근로시간 12시간은 15시간 미만"
    ]
    assert any(
        "12시간 < 15시간" in item["detail"] for item in response.json()["evidence"]
    )


def test_weekly_holiday_unknown_when_contract_time_missing(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.WEEKLY_HOLIDAY,
    )

    response = client.post(
        "/chat",
        json=payload(
            terms(work_days_per_week=field(None)),
            question="주휴 요건 알려줘",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert "계산할 수 없습니다" in body["answer"]
    assert body["limitation"] is None
    assert "계약서의 근무시간과 주 근무일 수" in body["condition_groups"]["needs_check"]


def test_severance_pay_contract_conditions_are_structured(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.SEVERANCE_PAY,
    )
    contract = terms(contract_end=field("2027-07-31"))

    response = client.post(
        "/chat",
        json=payload(contract, question="퇴직금 받을 수 있어?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "SEVERANCE_PAY"
    assert body["answer"] == "계약 조건상 퇴직급여 관련 두 기준을 충족합니다."
    assert body["limitation"] is None
    assert body["condition_groups"]["met"] == [
        "계약상 예정 근로기간이 1년 이상",
        "4주 평균 기준(현재 계약상 주간 일정으로 비교): 주 소정근로시간이 15시간 이상",
    ]
    assert body["condition_groups"]["unmet"] == []
    assert (
        "실제 입사일·퇴사일과 계속근로 여부" in body["condition_groups"]["needs_check"]
    )
    assert (
        "계속근로기간 중 주 소정근로시간 변경 여부"
        in body["condition_groups"]["needs_check"]
    )
    assert "실제 퇴직 여부" in body["condition_groups"]["needs_check"]
    assert "퇴직금 금액" not in str(body)


def test_severance_pay_unmet_contract_conditions_are_not_eligibility_conclusion(
    client,
    monkeypatch,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.SEVERANCE_PAY,
    )
    contract = terms(
        contract_end=field("2026-12-31"),
        work_start_time=field("09:00"),
        work_end_time=field("13:00"),
        break_start_time=field(None),
        break_end_time=field(None),
        work_days_per_week=field(3),
    )

    response = client.post(
        "/chat",
        json=payload(contract, question="퇴직금 받을 수 있어?"),
    )

    body = response.json()
    assert response.status_code == 200
    assert "받을 수 없습니다" not in body["answer"]
    assert body["condition_groups"]["unmet"] == [
        "계약상 예정 근로기간이 1년 미만",
        "4주 평균 기준(현재 계약상 주간 일정으로 비교): 주 소정근로시간이 15시간 미만",
    ]


def test_severance_pay_missing_contract_facts_are_needs_check(
    client,
    monkeypatch,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.SEVERANCE_PAY,
    )
    contract = terms(contract_end=field(None), work_days_per_week=field(None))

    response = client.post(
        "/chat",
        json=payload(contract, question="퇴직금 받을 수 있어?"),
    )

    body = response.json()
    assert response.status_code == 200
    assert "정보가 부족" in body["answer"]
    assert body["condition_groups"]["met"] == []
    assert body["condition_groups"]["unmet"] == []
    assert (
        "계약 시작일·종료일과 계약상 예정 근로기간"
        in body["condition_groups"]["needs_check"]
    )
    assert "계약상 주 소정근로시간" in body["condition_groups"]["needs_check"]


@pytest.mark.parametrize(
    ("topic", "question", "expected_text", "needs_text"),
    [
        (
            ChatTopic.SOCIAL_INSURANCE,
            "4대보험 가입 대상이야?",
            "보험별 확인사항",
            "산재보험",
        ),
        (
            ChatTopic.ANNUAL_LEAVE,
            "연차 받을 수 있어?",
            "기간·시간 지표",
            "상시 5명",
        ),
        (
            ChatTopic.DISMISSAL_NOTICE,
            "해고예고수당 받을 수 있어?",
            "확정할 수 없습니다",
            "실제 해고인지",
        ),
        (
            ChatTopic.PROBATION_MINIMUM_WAGE,
            "수습시급 최저임금 기준은?",
            "수습 최저임금",
            "단순노무",
        ),
    ],
)
def test_new_policy_topics_return_structured_non_definitive_cards(
    client,
    monkeypatch,
    topic,
    question,
    expected_text,
    needs_text,
) -> None:
    mock_classification(monkeypatch, ChatIntent.CALCULATION, topic)
    contract = terms(contract_end=field("2027-07-31"))

    response = client.post("/chat", json=payload(contract, question=question))

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == topic.value
    assert expected_text in body["answer"]
    assert any(needs_text in item for item in body["condition_groups"]["needs_check"])
    assert body["evidence"]
    assert "가입 대상입니다" not in body["answer"]
    assert "받을 수 있습니다" not in body["answer"]


def test_probation_discount_floor_is_code_calculated(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.PROBATION_MINIMUM_WAGE,
    )
    contract = terms(contract_end=field("2027-07-31"), wage_amount=field(9_288))

    response = client.post(
        "/chat",
        json=payload(contract, question="수습시급 최저임금 기준은?"),
    )

    body = response.json()
    assert response.status_code == 200
    assert any("9,288원 이상" in item for item in body["condition_groups"]["met"])
    assert any("10,320원" in item["detail"] for item in body["evidence"])
    assert (
        "수습 감액의 모든 법정 전제 충족 여부"
        in body["condition_groups"]["needs_check"]
    )


@pytest.mark.parametrize(
    "question",
    ["수습기간에도 최저임금을 받을 수 있나요?", "수습최저임금"],
)
def test_probation_frontend_phrases_extract_only_probation_topic(
    client,
    monkeypatch,
    question,
) -> None:
    features = extract_safe_features(question)

    assert features is not None
    assert features.topics == [ChatTopic.PROBATION_MINIMUM_WAGE]

    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.PROBATION_MINIMUM_WAGE,
    )
    response = client.post("/chat", json=payload(question=question))

    assert response.status_code == 200
    assert response.json()["topic"] == "PROBATION_MINIMUM_WAGE"


def test_unrelated_probation_question_is_not_supported() -> None:
    assert extract_safe_features("수습기간은 보통 얼마나 하나요?") is None


@pytest.mark.parametrize(
    ("topic", "question"),
    [
        (ChatTopic.SOCIAL_INSURANCE, "4대보험 대상이야?"),
        (ChatTopic.ANNUAL_LEAVE, "연차 받을 수 있어?"),
        (ChatTopic.DISMISSAL_NOTICE, "해고예고수당 대상이야?"),
        (ChatTopic.PROBATION_MINIMUM_WAGE, "수습시급 기준은?"),
    ],
)
def test_new_policy_topics_keep_missing_contract_values_in_needs_check(
    client,
    monkeypatch,
    topic,
    question,
) -> None:
    mock_classification(monkeypatch, ChatIntent.CALCULATION, topic)
    contract = terms(
        contract_start=field(None),
        contract_end=field(None),
        work_days_per_week=field(None),
        wage_amount=field(None),
    )

    response = client.post("/chat", json=payload(contract, question=question))

    groups = response.json()["condition_groups"]
    assert response.status_code == 200
    assert groups["needs_check"]
    assert not groups["met"]
    assert not groups["unmet"]


def test_social_insurance_below_fifteen_is_not_four_insurance_unmet(
    client,
    monkeypatch,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.SOCIAL_INSURANCE,
    )
    contract = terms(
        work_start_time=field("09:00"),
        work_end_time=field("13:00"),
        break_start_time=field(None),
        break_end_time=field(None),
        work_days_per_week=field(3),
    )

    body = client.post(
        "/chat", json=payload(contract, question="4대보험 대상이야?")
    ).json()

    assert body["condition_groups"]["unmet"] == []
    assert any(
        "주 15시간 미만" in item and "월시간·기간·소득 예외" in item
        for item in body["condition_groups"]["needs_check"]
    )


def test_annual_and_dismissal_cards_scope_contract_indicators(
    client,
    monkeypatch,
) -> None:
    contract = terms(contract_end=field("2027-07-31"))
    mock_classification(monkeypatch, ChatIntent.CALCULATION, ChatTopic.ANNUAL_LEAVE)
    annual = client.post(
        "/chat", json=payload(contract, question="연차 받을 수 있어?")
    ).json()
    assert any(
        "현재 계약상 주간 일정으로 비교한 4주 평균" in item
        for item in annual["condition_groups"]["met"]
    )

    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.DISMISSAL_NOTICE,
    )
    dismissal = client.post(
        "/chat", json=payload(contract, question="해고예고수당 대상이야?")
    ).json()
    assert "현재 계약의 예정기간" in dismissal["condition_groups"]["met"][0]
    assert (
        "30일분 통상임금 산정에 필요한 임금자료"
        in dismissal["condition_groups"]["needs_check"]
    )


def test_field_lookup_uses_only_contract_value(client, monkeypatch) -> None:
    mock_classification(monkeypatch, ChatIntent.FIELD_LOOKUP, ChatTopic.PAYDAY)

    response = client.post("/chat", json=payload(question="급여일은 언제야?"))

    assert response.status_code == 200
    assert response.json()["answer"] == "계약서에 적힌 임금 지급일은 매월 10일입니다."
    assert response.json()["evidence"][0]["detail"] == "매월 10일"


def test_missing_clause_lists_validation_missing_results(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.MISSING_CLAUSE,
        ChatTopic.MISSING_CLAUSES,
    )

    response = client.post(
        "/chat",
        json=payload(terms(job_description=field(None)), question="빠진 조항 있어?"),
    )

    assert response.status_code == 200
    assert "업무의 내용" in response.json()["answer"]
    assert any(item["kind"] == "LEGAL" for item in response.json()["evidence"])


def test_legal_standard_comes_from_fixed_constant(client, monkeypatch) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.LEGAL_STANDARD,
        ChatTopic.MINIMUM_WAGE,
    )

    response = client.post("/chat", json=payload(question="최저임금 얼마야?"))

    assert response.status_code == 200
    assert "10,320원" in response.json()["answer"]
    assert "SRC-MINWAGE-2026" in response.json()["evidence"][0]["detail"]


@pytest.mark.parametrize(
    "question",
    [
        "사장님 신고할 수 있나요?",
        "이거 부당해고인가요?",
        "대타를 썼는데 주휴수당 받나요?",
        "임금 체불로 소송하면 이길 수 있나요?",
        "친구가 대신 일했는데 주휴 받을 수 있나요?",
        "동료 대신 근무하고 교대했는데 주휴는요?",
        "근무일을 교환했는데 주휴수당 받아요?",
        "실제 근무한 이번주 출근 기록으로 계산해줘",
        "지난주 결근했는데 주휴 받을 수 있나요?",
        "추가근무와 야근도 임금에 포함되나요?",
        "퇴사하려고 하는데 그만두기 전에 뭘 해야 하나요?",
        "월급을 못 받았어요",
        "아파서 하루 빠졌는데 주휴수당 받아?",
        "하루 안 나갔는데 주휴수당 받을 수 있어?",
        "스케줄을 서로 바꿔 일했는데 주휴수당 돼?",
        "내 근무를 다른 사람이 해줬는데 주휴수당 받아?",
    ],
)
def test_fail_closed_prefilter_refuses_without_provider(
    client,
    monkeypatch,
    question,
) -> None:
    async def fail_if_called(features: SafeQuestionFeatures):
        raise AssertionError("차단 질문을 제공자에 보내면 안 됩니다.")

    monkeypatch.setattr(chat_router, "classify_features", fail_if_called)

    response = client.post("/chat", json=payload(question=question))

    assert response.status_code == 200
    assert response.json()["intent"] == "OUT_OF_SCOPE"
    assert "1350" in response.json()["answer"]
    assert response.json()["evidence"] == []


def test_provider_rejects_malformed_closed_enum_response(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent":"LEGAL_ADVICE","topic":"WEEKLY_HOLIDAY"}'
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "app.chat.provider.settings.upstage_api_key",
        "synthetic-test-key",
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=FakeResponse())):
        with pytest.raises(ChatProviderError) as caught:
            asyncio.run(
                classify_features(
                    SafeQuestionFeatures(
                        topics=[ChatTopic.WEEKLY_HOLIDAY],
                        signals=[QuerySignal.ELIGIBILITY],
                    )
                )
            )

    assert "가상 질문" not in str(caught.value)
    assert "LEGAL_ADVICE" not in str(caught.value)


def test_provider_sends_only_closed_safe_features(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent":"FIELD_LOOKUP","topic":"PAYDAY"}'
                        }
                    }
                ]
            }

    async def fake_post(self, url, *, headers, json):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(
        "app.chat.provider.settings.upstage_api_key",
        "synthetic-test-key",
    )
    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    result = asyncio.run(
        classify_features(
            SafeQuestionFeatures(
                topics=[ChatTopic.PAYDAY],
                signals=[QuerySignal.DATE],
            )
        )
    )

    serialized = str(captured["payload"])
    assert result.topic == ChatTopic.PAYDAY
    assert captured["url"] == "https://api.upstage.ai/v1/chat/completions"
    assert captured["payload"]["model"] == "solar-pro3"
    assert "PAYDAY" in serialized
    assert "DATE" in serialized
    assert "급여일은 언제야?" not in serialized
    assert "가상근로자" not in serialized
    assert "부산시 가상매장" not in serialized


def test_private_raw_question_is_reduced_to_safe_features_before_upstage(
    client,
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent":"FIELD_LOOKUP","topic":"PAYDAY"}'
                        }
                    }
                ]
            }

    async def fake_post(self, url, *, headers, json):
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(
        "app.chat.provider.settings.upstage_api_key",
        "synthetic-test-key",
    )
    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    private_question = (
        "김하늘 private-person@example.com 010-1234-5678의 급여일은 언제인가요?"
    )

    response = client.post("/chat", json=payload(question=private_question))

    assert response.status_code == 200
    serialized = str(captured["payload"])
    assert "PAYDAY" in serialized
    assert "DATE" in serialized
    assert "김하늘" not in serialized
    assert "private-person@example.com" not in serialized
    assert "010-1234-5678" not in serialized
    assert private_question not in serialized


@pytest.mark.parametrize(
    ("question", "topic"),
    [
        (
            "김하늘 private@example.com 010-1234-5678 4대보험 대상이야?",
            "SOCIAL_INSURANCE",
        ),
        ("김하늘 private@example.com 010-1234-5678 연차 받을 수 있어?", "ANNUAL_LEAVE"),
        ("김하늘 private@example.com 010-1234-5678 해고예고수당?", "DISMISSAL_NOTICE"),
        (
            "김하늘 private@example.com 010-1234-5678 수습시급 기준?",
            "PROBATION_MINIMUM_WAGE",
        ),
    ],
)
def test_new_policy_safe_features_remove_raw_pii(question, topic) -> None:
    features = extract_safe_features(question)

    assert features is not None
    serialized = features.model_dump_json()
    assert topic in serialized
    assert "김하늘" not in serialized
    assert "private@example.com" not in serialized
    assert "010-1234-5678" not in serialized


@pytest.mark.parametrize(
    "question", ["안녕하세요", "도와주세요", "김하늘 010-1234-5678"]
)
def test_no_safe_supported_feature_fails_closed_without_provider(
    client,
    monkeypatch,
    question,
) -> None:
    async def fail_if_called(features: SafeQuestionFeatures):
        raise AssertionError("안전한 지원 특징이 없으면 제공자를 호출하면 안 됩니다.")

    monkeypatch.setattr(chat_router, "classify_features", fail_if_called)

    response = client.post("/chat", json=payload(question=question))

    assert response.status_code == 200
    assert response.json()["intent"] == "OUT_OF_SCOPE"
    assert "1350" in response.json()["answer"]


def test_inconsistent_provider_topic_fails_closed(client, monkeypatch) -> None:
    async def inconsistent_classification(
        features: SafeQuestionFeatures,
    ) -> Classification:
        assert features.topics == [ChatTopic.WEEKLY_HOLIDAY]
        return Classification(
            intent=ChatIntent.LEGAL_STANDARD,
            topic=ChatTopic.MINIMUM_WAGE,
        )

    monkeypatch.setattr(
        chat_router,
        "classify_features",
        inconsistent_classification,
    )

    response = client.post(
        "/chat",
        json=payload(question="주휴수당 시간 요건이 뭐예요?"),
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "OUT_OF_SCOPE"
    assert response.json()["topic"] == "UNSUPPORTED"


def test_provider_failure_returns_safe_503_without_private_data(
    client,
    monkeypatch,
    caplog,
) -> None:
    private_question = "가상근로자 김하늘 private@example.com 급여일 알려줘"

    async def fail_classification(features: SafeQuestionFeatures):
        raise ChatProviderError(f"provider failed for: {features}")

    monkeypatch.setattr(chat_router, "classify_features", fail_classification)

    with caplog.at_level(logging.WARNING, logger=chat_router.__name__):
        response = client.post("/chat", json=payload(question=private_question))

    assert response.status_code == 503
    assert response.json() == {
        "detail": "질문 분류 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
    }
    assert private_question not in response.text
    assert private_question not in caplog.text
    assert "private@example.com" not in caplog.text
    assert "ChatProviderError" in caplog.text


@pytest.mark.parametrize(
    ("question", "expected_status"),
    [
        ("", 422),
        ("   ", 422),
        ("가" * 501, 422),
    ],
)
def test_chat_question_validation(client, question, expected_status) -> None:
    response = client.post("/chat", json=payload(question=question))

    assert response.status_code == expected_status


def test_chat_requires_contract_terms(client) -> None:
    response = client.post("/chat", json={"question": "급여일은 언제야?"})

    assert response.status_code == 422


def test_rag_corpus_is_closed_over_verified_kb_sources() -> None:
    allowed = {
        "SRC-MINWAGE-2026",
        "SRC-LSA-17",
        "SRC-MOEL-CONTRACT-FORMS",
        "SRC-LSA-54-CURRENT",
        "SRC-LSA-69",
        "SRC-LSA-70",
        "SRC-LSA-18",
        "SRC-MOEL-WEEKLY-HOLIDAY",
        "SRC-ERBA-4",
        "SRC-ERBA-8",
        "SRC-MOEL-SEVERANCE-2025",
        "SRC-LSA-60",
        "SRC-LSA-11",
        "SRC-LSA-26",
        "SRC-MWA-5",
        "SRC-MWA-DECREE-3",
        "SRC-IACI-COVERAGE",
        "SRC-EASYLAW-EMPLOYMENT-INSURANCE",
        "SRC-NHIS-DECREE-9",
        "SRC-NPS-COVERAGE",
    }

    assert VERIFIED_KNOWLEDGE
    assert all(entry.kb_id.startswith("KB-") for entry in VERIFIED_KNOWLEDGE)
    assert {
        source_id for entry in VERIFIED_KNOWLEDGE for source_id in entry.source_ids
    }.issubset(allowed)


def test_rag_retrieval_returns_topic_specific_top_evidence() -> None:
    matches = retrieve_knowledge(
        "퇴직금 기준과 요건이 궁금해요",
        topic=ChatTopic.SEVERANCE_PAY,
        signals=[QuerySignal.REQUIREMENT],
    )

    assert [trace.kb_id for _, trace in matches] == ["KB-SEVERANCE-ELIGIBILITY"]
    assert set(matches[0][1].source_ids) == {
        "SRC-ERBA-4",
        "SRC-ERBA-8",
        "SRC-MOEL-SEVERANCE-2025",
    }


def test_grounded_rag_generation_uses_minimal_context_and_traces_sources(
    client,
    monkeypatch,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.WEEKLY_HOLIDAY,
    )
    captured = {}

    async def fake_generate(context):
        captured["context"] = context
        return GroundedGenerationOutput(
            sentence_ids=["KB-WEEKLY-HOLIDAY-TIME-SUMMARY"],
            source_ids=["SRC-LSA-18", "SRC-MOEL-WEEKLY-HOLIDAY"],
        )

    monkeypatch.setattr("app.chat.rag.generate_grounded_explanation", fake_generate)
    private_contract = terms(
        worker_name=field("가상비밀근로자"),
        worker_contact=field("010-9876-5432"),
        workplace=field("비공개 가상매장"),
    )
    private_question = "김하늘 private@example.com의 주휴수당 요건은?"

    response = client.post(
        "/chat",
        json=payload(private_contract, question=private_question),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer_mode"] == "GROUNDED_GENERATION"
    assert body["retrieved_knowledge"][0]["kb_id"] == "KB-WEEKLY-HOLIDAY-TIME"
    assert "SRC-LSA-18" in body["answer"]
    serialized = captured["context"].model_dump_json()
    assert private_question not in serialized
    assert "김하늘" not in serialized
    assert "private@example.com" not in serialized
    assert "가상비밀근로자" not in serialized
    assert "010-9876-5432" not in serialized
    assert "비공개 가상매장" not in serialized
    assert "계약상 주 소정근로시간 18시간" not in serialized


@pytest.mark.parametrize(
    "generated",
    [
        GroundedGenerationOutput(
            sentence_ids=["KB-WEEKLY-HOLIDAY-TIME-99"],
            source_ids=["SRC-LSA-18", "SRC-MOEL-WEEKLY-HOLIDAY"],
        ),
        GroundedGenerationOutput(
            sentence_ids=["KB-WEEKLY-HOLIDAY-TIME-SUMMARY"],
            source_ids=["SRC-LSA-18"],
        ),
        GroundedGenerationOutput(
            sentence_ids=["KB-WEEKLY-HOLIDAY-TIME-SUMMARY"],
            source_ids=["SRC-FAKE-999"],
        ),
    ],
)
def test_ungrounded_generation_falls_back_to_deterministic_answer(
    client,
    monkeypatch,
    generated,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.CALCULATION,
        ChatTopic.WEEKLY_HOLIDAY,
    )

    async def fake_generate(context):
        return generated

    monkeypatch.setattr("app.chat.rag.generate_grounded_explanation", fake_generate)

    body = client.post(
        "/chat",
        json=payload(question="주휴수당 요건 알려줘"),
    ).json()

    assert body["answer_mode"] == "DETERMINISTIC_TEMPLATE"
    assert body["answer"] == (
        "계약상 주 소정근로시간을 기준으로 보면 주휴수당 지급 조건 중 "
        "시간 요건을 충족합니다."
    )
    assert body["retrieved_knowledge"][0]["kb_id"] == "KB-WEEKLY-HOLIDAY-TIME"


def test_grounded_generation_provider_failure_is_safe_template_fallback(
    client,
    monkeypatch,
) -> None:
    mock_classification(
        monkeypatch,
        ChatIntent.LEGAL_STANDARD,
        ChatTopic.MINIMUM_WAGE,
    )

    async def fail_generate(context):
        raise ChatProviderError("synthetic generation failure")

    monkeypatch.setattr("app.chat.rag.generate_grounded_explanation", fail_generate)

    response = client.post("/chat", json=payload(question="최저임금 얼마야?"))

    assert response.status_code == 200
    body = response.json()
    assert body["answer_mode"] == "DETERMINISTIC_TEMPLATE"
    assert "10,320원" in body["answer"]
    assert body["retrieved_knowledge"][0]["kb_id"] == "KB-MW-2026"


def test_field_lookup_without_legal_kb_skips_generation(client, monkeypatch) -> None:
    mock_classification(monkeypatch, ChatIntent.FIELD_LOOKUP, ChatTopic.PAYDAY)

    async def fail_if_called(context):
        raise AssertionError("근거 없는 생성은 호출하면 안 됩니다.")

    monkeypatch.setattr("app.chat.rag.generate_grounded_explanation", fail_if_called)

    body = client.post(
        "/chat",
        json=payload(question="급여일은 언제야?"),
    ).json()

    assert body["answer_mode"] == "DETERMINISTIC_TEMPLATE"
    assert body["retrieved_knowledge"] == []


def test_generation_provider_rejects_free_text_instead_of_approved_ids(
    monkeypatch,
) -> None:
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"explanation":"검증되지 않은 새 법률 사실",'
                                '"source_ids":["SRC-LSA-18"]}'
                            )
                        }
                    }
                ]
            }

    context = GroundedGenerationInput(
        selection_keys=["LEGAL_STANDARD", "WEEKLY_HOLIDAY", "REQUIREMENT"],
        candidate_sentences={"KB-TEST-SUMMARY": "승인된 설명 문장"},
        sentence_source_ids={"KB-TEST-SUMMARY": ["SRC-LSA-18"]},
        allowed_source_ids=["SRC-LSA-18"],
    )
    monkeypatch.setattr(
        "app.chat.provider.settings.upstage_api_key",
        "synthetic-test-key",
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=FakeResponse())):
        with pytest.raises(ChatProviderError):
            asyncio.run(generate_grounded_explanation(context))
