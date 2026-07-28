"""
extract.py 단위 테스트. 실제 API를 호출하지 않는다 (httpx를 mock).
값은 전부 가상 데이터 (가상 근로자 '김하늘' / 가상 사업주 '박정호').

실제 API 연동 확인(스키마가 Upstage에 실제로 받아들여지는지 등)은
spikes/extract_spike.py + spikes/fixtures/ 로 별도 확인했다.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.extract import (
    FIELD_DESCRIPTIONS,
    ExtractError,
    _confidence_from_upstage,
    _find_source_text,
    build_contract_terms,
    build_extraction_schema,
    call_information_extract,
)
from app.config import settings
from app.schemas import Confidence

VIRTUAL_VALUES = {
    "contract_start": "2026년 8월 1일",
    "contract_end": "2027년 1월 31일",
    "workplace": "부산광역시 금정구 장전동 카페 000",
    "job_description": "음료 제조 및 매장 관리",
    "work_start_time": "09:00",
    "work_end_time": "16:00",
    "break_start_time": "12:00",
    "break_end_time": "12:30",
    "work_days_per_week": "3",
    "weekly_holiday_day": "",  # 계약서에 빈칸 → NOT_FOUND로 정규화되어야 함
    "wage_type": "HOURLY",
    "wage_amount": "10000",
    "has_bonus": "없음",
    "other_allowance": None,
    "payday": "매월 10일",
    "payment_method": "근로자 명의 예금통장에 입금",
    "employer_business_name": "카페 000",
    "employer_phone": "051-000-0000",
    "employer_address": "부산광역시 금정구 장전동 00-0",
    "employer_name": "박정호",
    "worker_address": "부산광역시 금정구 구서동 00-0",
    "worker_contact": "010-0000-0000",
    "worker_name": "김하늘",
}


def make_extract_response(values: dict, confidences: dict | None = None) -> dict:
    message = {"role": "assistant", "content": json.dumps(values, ensure_ascii=False)}
    if confidences:
        message["tool_calls"] = [
            {
                "function": {
                    "name": "additional_values",
                    "arguments": {
                        key: {"_value": val, "confidence": confidences.get(key)}
                        for key, val in values.items()
                    },
                }
            }
        ]
    return {"choices": [{"message": message}]}


class FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


class TestBuildExtractionSchema:
    def test_covers_every_contract_terms_field(self):
        schema = build_extraction_schema()["json_schema"]["schema"]
        assert set(schema["properties"]) == set(FIELD_DESCRIPTIONS)
        assert set(schema["required"]) == set(FIELD_DESCRIPTIONS)
        assert schema["additionalProperties"] is False

    def test_all_properties_are_plain_string_type(self):
        """Upstage는 1단계 속성에 ['string','null'] 같은 유니온 타입을 거부한다."""
        schema = build_extraction_schema()["json_schema"]["schema"]
        for prop in schema["properties"].values():
            assert prop["type"] == "string"


class TestConfidenceMapping:
    def test_high_confidence_with_value(self):
        assert _confidence_from_upstage("high", True) == Confidence.HIGH

    def test_low_or_medium_confidence_with_value(self):
        assert _confidence_from_upstage("low", True) == Confidence.LOW
        assert _confidence_from_upstage("medium", True) == Confidence.LOW

    def test_missing_value_is_not_found_regardless_of_confidence(self):
        assert _confidence_from_upstage("high", False) == Confidence.NOT_FOUND
        assert _confidence_from_upstage(None, False) == Confidence.NOT_FOUND


class TestFindSourceText:
    def test_finds_line_containing_value(self):
        text = "1. 근로계약기간 : 2026년 8월 1일 부터\n2. 근무장소 : 서울"
        assert _find_source_text(text, "2026년 8월 1일") == "1. 근로계약기간 : 2026년 8월 1일 부터"

    def test_returns_none_when_not_found(self):
        assert _find_source_text("아무 내용", "존재하지 않는 값") is None

    def test_returns_none_for_empty_value(self):
        assert _find_source_text("아무 내용", None) is None
        assert _find_source_text("아무 내용", "") is None


class TestBuildContractTerms:
    def test_maps_all_fields_with_confidence_and_source(self):
        response = make_extract_response(
            VIRTUAL_VALUES, confidences={"wage_amount": "low", "worker_name": "high"}
        )
        full_text = "성명 : 김하늘\n임금 : 시간급 금 10,000원"

        terms = build_contract_terms(response, source_text_pool=full_text)

        assert terms.worker_name.value == "김하늘"
        assert terms.worker_name.confidence == Confidence.HIGH
        assert terms.wage_amount.confidence == Confidence.LOW
        assert terms.hourly_wage == 10000  # schemas.py 파생값 (코드 계산) 확인

    def test_empty_string_value_normalized_to_not_found(self):
        response = make_extract_response(VIRTUAL_VALUES)

        terms = build_contract_terms(response, source_text_pool="")

        assert terms.weekly_holiday_day.value is None
        assert terms.weekly_holiday_day.confidence == Confidence.NOT_FOUND

    def test_null_value_is_not_found(self):
        response = make_extract_response(VIRTUAL_VALUES)

        terms = build_contract_terms(response, source_text_pool="")

        assert terms.other_allowance.value is None
        assert terms.other_allowance.confidence == Confidence.NOT_FOUND

    def test_malformed_response_raises_extract_error(self):
        with pytest.raises(ExtractError):
            build_contract_terms({"choices": []}, source_text_pool="")


@pytest.fixture(autouse=True)
def upstage_key(monkeypatch):
    monkeypatch.setattr(settings, "upstage_api_key", "test-key")


class TestCallInformationExtract:
    @pytest.mark.asyncio
    async def test_sends_schema_and_confidence_flag(self):
        fake = FakeResponse(200, make_extract_response(VIRTUAL_VALUES))
        with patch(
            "httpx.AsyncClient.post", new=AsyncMock(return_value=fake)
        ) as mock_post:
            await call_information_extract(b"fake-bytes", "image/png")

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["model"] == "information-extract"
        assert payload["confidence"] is True
        assert payload["response_format"]["json_schema"]["name"] == "contract_terms"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_http_error_raises_extract_error(self):
        fake = FakeResponse(400, text="bad request")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
            with pytest.raises(ExtractError):
                await call_information_extract(b"fake-bytes", "image/png")
