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
    _normalize_extracted_value,
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


class TestNormalizeExtractedValue:
    """
    평가셋(app/evaluation/)을 실제 API로 돌려서 발견한 실제 결함 재현.
    빈 칸 옆 라벨의 콜론만 값으로 뽑거나(':'), 못 찾음을 텍스트 'null'로
    흘리는 경우(': null')가 실제로 관측되어 정규화가 필요했다.
    """

    def test_colon_only_becomes_none(self):
        assert _normalize_extracted_value(":") is None

    def test_null_token_with_leading_punctuation_becomes_none(self):
        assert _normalize_extracted_value(": null") is None

    def test_blank_string_becomes_none(self):
        assert _normalize_extracted_value("   ") is None

    def test_meaningful_negative_value_is_kept(self):
        """'없음'은 실제 의미 있는 값이다 (플레이스홀더가 아님)."""
        assert _normalize_extracted_value("없음") == "없음"

    def test_non_string_value_passes_through(self):
        assert _normalize_extracted_value(None) is None


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


# ============================================================
# 근거 문장(source_text) 매칭 — 실측에서 드러난 오류들
#
# 아래 4가지는 spikes/fixtures/contract_01_*.json 으로 확인된 실제 실패다.
# 근거 문장은 화면에서 "왜 이렇게 읽었는지" 사용자에게 보여주는 값이라
# 틀린 줄을 붙이면 없느니만 못하다.
# ============================================================

CONTRACT_TEXT = """1. 근로계약기간 : 2026년 8월 1 일 부터 2027년 1월 31 일 까지
2. 근 무 장 소 : 부산광역시 금정구 장전동 카페 000
4. 소정근로시간 : 09시 00분부터 16시 00분까지 (휴게시간 : 12시 00분 ~ 12시 30분)
5. 근무일/휴일 : 매주 3일 근무, 주휴일 매주 ( ) 요일
- 시간(일, 월)급 : 시간급 금 10,000원
- 상여금 : 없음
- 기타급여(제수당 등) : 없음
- 임금지급일 : 매월 10일 (휴일의 경우는 전일 지급)
(사업주) 사업체명 : 카페 000 전화 : 051-000-0000
주 소 : 부산광역시 금정구 장전동 00-0
(근로자) 주 소 : 부산광역시 금정구 구서동 00-0"""


class TestSourceTextMatching:
    def test_short_number_does_not_match_wrong_line(self):
        """'3'이 '2027년 1월 31 일'의 3에 걸려 계약기간이 근거로 붙던 문제."""
        assert (
            _find_source_text(CONTRACT_TEXT, "3", "work_days_per_week")
            == "5. 근무일/휴일 : 매주 3일 근무, 주휴일 매주 ( ) 요일"
        )

    def test_short_value_without_keyword_gives_up(self):
        """키워드로 못 좁히면 틀린 줄을 주느니 근거 없음을 택한다."""
        assert _find_source_text(CONTRACT_TEXT, "3", None) is None

    def test_normalized_amount_matches_original_notation(self):
        """모델이 '10,000원'을 '10000'으로 정규화해 매칭이 깨지던 문제."""
        assert (
            _find_source_text(CONTRACT_TEXT, "10000", "wage_amount")
            == "- 시간(일, 월)급 : 시간급 금 10,000원"
        )

    def test_normalized_time_matches_original_notation(self):
        """'12시 30분' → '12:30' 정규화."""
        assert "휴게시간" in _find_source_text(
            CONTRACT_TEXT, "12:30", "break_end_time"
        )

    def test_same_value_in_two_fields_picks_right_line(self):
        """'없음'이 상여금·제수당 양쪽에 있어 첫 줄이 이기던 문제."""
        assert _find_source_text(CONTRACT_TEXT, "없음", "has_bonus") == "- 상여금 : 없음"
        assert (
            _find_source_text(CONTRACT_TEXT, "없음", "other_allowance")
            == "- 기타급여(제수당 등) : 없음"
        )

    def test_hangul_value_does_not_match_by_digits_alone(self):
        """주소('...00-0', 숫자 000)가 '카페 000'에 걸리던 오탐."""
        assert (
            _find_source_text(
                CONTRACT_TEXT, "부산광역시 금정구 구서동 00-0", "worker_address"
            )
            == "(근로자) 주 소 : 부산광역시 금정구 구서동 00-0"
        )

    def test_code_value_matches_korean_notation(self):
        """wage_type은 'HOURLY' 코드라 원문에 그대로 없다."""
        assert (
            _find_source_text(CONTRACT_TEXT, "HOURLY", "wage_type")
            == "- 시간(일, 월)급 : 시간급 금 10,000원"
        )


class TestConfidenceScore:
    def test_numeric_score_beats_categorical_grade(self):
        """등급 low / 점수 0.9661 인 wage_amount 가 LOW로 뜨던 문제."""
        assert _confidence_from_upstage("low", True, 0.9661) == Confidence.HIGH

    def test_low_numeric_score_is_low(self):
        assert _confidence_from_upstage("high", True, 0.5745) == Confidence.LOW

    def test_falls_back_to_grade_without_score(self):
        assert _confidence_from_upstage("high", True, None) == Confidence.HIGH
        assert _confidence_from_upstage("low", True, None) == Confidence.LOW

    def test_missing_value_is_not_found_even_with_high_score(self):
        assert _confidence_from_upstage("high", False, 0.99) == Confidence.NOT_FOUND


class TestWhitespaceNormalization:
    """
    같은 사진을 두 번 넣어도 모델이 공백을 다르게 돌려준다(실행마다 변동).
      1차: '2026년 8월 1 일'  → 근거 찾음
      2차: '2026년 8월 1일'   → 근거 못 찾음
    공백을 무시하고 비교해 두 경우 모두 잡는다.
    """

    def test_squeezed_date_still_matches(self):
        assert (
            _find_source_text(CONTRACT_TEXT, "2026년 8월 1일", "contract_start")
            == "1. 근로계약기간 : 2026년 8월 1 일 부터 2027년 1월 31 일 까지"
        )

    def test_original_spacing_still_matches(self):
        assert (
            _find_source_text(CONTRACT_TEXT, "2026년 8월 1 일", "contract_start")
            == "1. 근로계약기간 : 2026년 8월 1 일 부터 2027년 1월 31 일 까지"
        )

    def test_whitespace_rule_does_not_break_address_disambiguation(self):
        """공백 무시가 주소 오탐을 되살리지 않는지 확인."""
        assert (
            _find_source_text(
                CONTRACT_TEXT, "부산광역시 금정구 구서동 00-0", "worker_address"
            )
            == "(근로자) 주 소 : 부산광역시 금정구 구서동 00-0"
        )
