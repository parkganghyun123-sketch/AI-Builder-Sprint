"""
Upstage Information Extract 연동 (A 담당)

계약서 이미지/PDF → ContractTerms.

⚠️ 여기서 하는 일은 "계약서에 뭐라고 적혀 있는지 읽어내는 것"까지다.
   최저임금 위반 여부, 주휴수당 대상 여부 같은 법정 판정은 절대 하지 않는다.
   판정은 app/validation/rules.py(B 담당)가 코드로 한다.

참고: https://console.upstage.ai/docs/capabilities/information-extraction
"""

import asyncio
import base64
import json
import mimetypes
from pathlib import Path

import httpx

from app.ai.document_parse import parse_document
from app.config import settings
from app.schemas import Confidence, ContractTerms, ExtractedField

BASE_URL = "https://api.upstage.ai/v1/information-extraction"

# ContractTerms 필드명 = 스키마 키. 순서는 표준근로계약서 항목 순서를 따른다.
FIELD_DESCRIPTIONS: dict[str, str] = {
    "contract_start": "근로계약기간 시작일. 계약서 원문 표기 그대로 (예: '2026년 8월 1일'). 없으면 null.",
    "contract_end": "근로계약기간 종료일. 원문 표기 그대로. 기간의 정함이 없으면 null.",
    "workplace": "근무 장소(주소).",
    "job_description": "업무의 내용.",
    "work_start_time": (
        "소정근로시간 시업(시작) 시각. 반드시 '09:00'처럼 시:분(HH:MM) 형식으로 변환할 것. "
        "'1일 6시간' 같은 근로시간 총량이 아니라 시각 자체를 찾을 것."
    ),
    "work_end_time": "소정근로시간 종업(종료) 시각. '16:00'처럼 시:분(HH:MM) 형식으로 변환.",
    "break_start_time": "휴게시간 시작 시각. 시:분(HH:MM) 형식. 계약서에 없으면 null.",
    "break_end_time": "휴게시간 종료 시각. 시:분(HH:MM) 형식. 계약서에 없으면 null.",
    "work_days_per_week": "주당 근무일수. 숫자만 (예: '주 5일 근무'면 '5').",
    "weekly_holiday_day": (
        "주휴일 요일. 표준근로계약서 5번 항목 '주휴일 매주 ○요일'에서 찾을 것 (예: '수요일'). "
        "빈칸이거나 기재가 없으면 null."
    ),
    "wage_type": (
        "임금 형태 코드. 계약서에 '시간급'으로 표기되어 있으면 'HOURLY', "
        "'일급'이면 'DAILY', '월급'이면 'MONTHLY'."
    ),
    "wage_amount": "임금 금액. 숫자만, 쉼표(,)와 '원' 없이 (예: '시간급 금 10,000원'이면 '10000').",
    "has_bonus": "상여금 지급 여부. 계약서에 표기된 대로 '있음' 또는 '없음'.",
    "other_allowance": "기타급여(제수당) 내용. 없으면 null.",
    "payday": "임금 지급일 (예: '매월 10일').",
    "payment_method": "임금 지급 방법 (예: '근로자에게 직접지급', '근로자 명의 예금통장에 입금').",
    "employer_business_name": "사업체명.",
    "employer_phone": "사업주(사업체) 전화번호.",
    "employer_address": "사업체 주소.",
    "employer_name": "사업주 성명(대표자).",
    "worker_address": "근로자 주소.",
    "worker_contact": "근로자 연락처(전화번호).",
    "worker_name": "근로자 성명.",
}

# 표준근로계약서에는 없지만 스키마에 있는 필드. 못 채워도 무방.
_OPTIONAL_FIELDS = {"employer_phone", "other_allowance", "has_bonus"}


class ExtractError(Exception):
    pass


def _auth_header() -> dict[str, str]:
    if not settings.upstage_api_key:
        raise ExtractError("UPSTAGE_API_KEY 미설정")
    return {"Authorization": f"Bearer {settings.upstage_api_key}"}


def build_extraction_schema() -> dict:
    """
    Information Extract용 JSON 스키마.

    Upstage 제약: 1단계 속성 type은 string/number/integer/boolean/array 중
    하나만 가능하다(object 불가, ["string","null"] 같은 유니온도 거부됨).
    모든 속성이 required에 있어야 하고 additionalProperties는 false여야 한다.
    "없으면 null"은 타입으로 표현할 수 없어 description에 명시하고,
    실제로 못 찾으면 모델이 null을 반환하도록 유도한다.
    """
    properties = {
        name: {
            "type": "string",
            "description": desc + " 계약서에서 찾을 수 없으면 null.",
        }
        for name, desc in FIELD_DESCRIPTIONS.items()
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_terms",
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(FIELD_DESCRIPTIONS.keys()),
                "additionalProperties": False,
            },
        },
    }


def _confidence_from_upstage(raw: str | None, has_value: bool) -> Confidence:
    """Upstage confidence 문자열('high'/'medium'/'low') → 우리 3단계."""
    if not has_value:
        return Confidence.NOT_FOUND
    if raw == "high":
        return Confidence.HIGH
    return Confidence.LOW


def _find_source_text(full_text: str, value: str | None) -> str | None:
    """
    Document Parse 전체 텍스트에서 값이 포함된 줄을 찾아 근거 문장으로 쓴다.
    못 찾으면 None (지어내지 않는다).
    """
    if not value or not full_text:
        return None
    needle = str(value).strip()
    if not needle:
        return None
    for line in full_text.splitlines():
        if needle in line:
            stripped = line.strip()
            if stripped:
                return stripped
    return None


async def call_information_extract(
    file_bytes: bytes,
    mime_type: str,
) -> dict:
    """Information Extract API 호출. 응답(dict) 그대로 반환."""
    encoded = base64.b64encode(file_bytes).decode("ascii")
    payload = {
        "model": "information-extract",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    }
                ],
            }
        ],
        "response_format": build_extraction_schema(),
        "confidence": True,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(
            BASE_URL,
            headers={**_auth_header(), "Content-Type": "application/json"},
            json=payload,
        )

    if res.status_code >= 400:
        raise ExtractError(f"HTTP {res.status_code}: {res.text}")

    return res.json()


def _parse_confidence_tool_call(message: dict) -> dict[str, str]:
    """tool_calls의 additional_values에서 필드별 confidence만 뽑는다. 없으면 빈 dict."""
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        if fn.get("name") != "additional_values":
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if not isinstance(args, dict):
            continue
        return {
            key: entry.get("confidence")
            for key, entry in args.items()
            if isinstance(entry, dict)
        }
    return {}


def build_contract_terms(
    extract_response: dict,
    *,
    source_text_pool: str = "",
) -> ContractTerms:
    """Information Extract 응답 → ContractTerms."""
    try:
        message = extract_response["choices"][0]["message"]
        values = json.loads(message["content"])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ExtractError(f"응답 파싱 실패: {e}") from e

    confidences = _parse_confidence_tool_call(message)

    fields: dict[str, ExtractedField] = {}
    for name in FIELD_DESCRIPTIONS:
        value = values.get(name)
        if isinstance(value, str) and not value.strip():
            value = None  # 모델이 빈 문자열로 "없음"을 표현하는 경우가 있다
        fields[name] = ExtractedField(
            value=value,
            confidence=_confidence_from_upstage(confidences.get(name), value is not None),
            source_text=_find_source_text(source_text_pool, value),
        )

    return ContractTerms(**fields)


async def extract_contract_terms(file_bytes: bytes, filename: str) -> ContractTerms:
    """
    사진/PDF 바이트 → ContractTerms.

    Document Parse로 원문 텍스트를 먼저 얻어 근거 문장(source_text) 매칭에 쓰고,
    실제 필드 추출은 Information Extract가 담당한다.
    """
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parse_result = await parse_document(file_bytes, filename)
    full_text = parse_result.get("content", {}).get("text", "")

    extract_response = await call_information_extract(file_bytes, mime_type)

    return build_contract_terms(extract_response, source_text_pool=full_text)


def extract(path: str) -> ContractTerms:
    """
    동기 CLI 진입점.

        python -c "from app.ai.extract import extract; print(extract('샘플.jpg'))"
    """
    file_bytes = Path(path).read_bytes()
    return asyncio.run(extract_contract_terms(file_bytes, Path(path).name))
