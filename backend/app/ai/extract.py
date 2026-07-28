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
import re
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


# confidence_score(0~1)가 이 값 이상이면 HIGH.
#
# 응답에는 등급 문자열('high'/'low')과 숫자 점수가 함께 오는데 둘이 어긋난다.
# 실측(spikes/fixtures/contract_01_extract.json):
#   wage_amount        등급 low  / 점수 0.9661  ← 등급만 쓰면 임금이 늘 LOW로 뜬다
#   weekly_holiday_day 등급 low  / 점수 0.5745  ← 실제로 빈칸 (정상 판정)
# 숫자 점수가 두 경우를 제대로 갈라주므로 점수를 우선한다.
CONFIDENCE_THRESHOLD = 0.90


def _confidence_from_upstage(
    raw: str | None,
    has_value: bool,
    score: float | None = None,
) -> Confidence:
    """Upstage 신뢰도 → 우리 3단계. 숫자 점수가 있으면 그쪽을 우선한다."""
    if not has_value:
        return Confidence.NOT_FOUND
    if score is not None:
        return Confidence.HIGH if score >= CONFIDENCE_THRESHOLD else Confidence.LOW
    # 점수가 없으면 등급 문자열로 대체
    return Confidence.HIGH if raw == "high" else Confidence.LOW


# 값이 짧으면 아무 줄에나 걸린다. 실측에서 work_days_per_week='3' 이
# '2027년 1월 31 일' 의 '3' 에 매칭돼 계약기간 문장이 근거로 붙었다.
# 틀린 근거를 보여주느니 근거 없음이 낫다.
_MIN_NEEDLE_LEN = 3

# 필드별 우선 키워드. 같은 값이 여러 줄에 나올 때 올바른 줄을 고른다.
# (has_bonus / other_allowance 가 둘 다 '없음' 이라 첫 줄이 이기던 문제)
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "has_bonus": ("상여금",),
    "other_allowance": ("제수당", "기타급여"),
    "payday": ("지급일",),
    "payment_method": ("지급방법", "지급 방법"),
    "weekly_holiday_day": ("주휴일",),
    "work_days_per_week": ("근무일", "소정근로시간"),
    "wage_amount": ("임금", "시간급", "월급", "일급"),
    "wage_type": ("임금", "시간급", "월급", "일급"),
    "break_start_time": ("휴게",),
    "break_end_time": ("휴게",),
    "work_start_time": ("근로시간", "시업"),
    "work_end_time": ("근로시간", "종업"),
    "employer_name": ("대표자",),
    "worker_name": ("성명", "근로자"),
    "employer_address": ("주소",),
    "worker_address": ("주소",),
    "employer_phone": ("전화",),
    "worker_contact": ("연락처",),
    "contract_start": ("근로계약기간",),
    "contract_end": ("근로계약기간",),
}


_HANGUL = re.compile(r"[가-힣]")

# 코드로 정규화돼 원문에 그대로 없는 값. 근거를 찾을 때 한글 표기로 바꿔 본다.
_VALUE_ALIASES: dict[str, str] = {
    "HOURLY": "시간급",
    "DAILY": "일급",
    "MONTHLY": "월급",
}


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _line_matches(line: str, needle: str) -> bool:
    """
    한 줄이 값을 담고 있는지 판단.

    모델이 값을 정규화해서 돌려주기 때문에 원문과 글자가 다르다.
      '10,000원'  → '10000'
      '12시 30분' → '12:30'
    그래서 그대로 비교하면 임금·시각의 근거를 못 찾는다(실측 확인).
    숫자만 남겨 비교하면 두 경우 모두 잡힌다.
    """
    if needle in line:
        return True

    # 숫자 대조는 값이 순수 숫자·기호일 때만 쓴다.
    # 한글이 섞인 값에 쓰면 '부산광역시 ... 00-0'(숫자 000)이
    # '카페 000'(숫자 000)에 걸리는 오탐이 난다(실측 확인).
    if _HANGUL.search(needle):
        return False

    nd = _digits(needle)
    # 숫자가 너무 짧으면(1~2자리) 우연히 걸리므로 제외
    return bool(nd) and len(nd) >= 3 and nd in _digits(line)


def _find_source_text(
    full_text: str,
    value: str | None,
    field_name: str | None = None,
) -> str | None:
    """
    Document Parse 원문에서 값의 근거가 된 줄을 찾는다.
    못 찾으면 None — 지어내지 않는다.

    라벨 키워드가 있는 줄을 우선하고, 없으면 값만으로 찾는다.
    """
    if not value or not full_text:
        return None

    needle = str(value).strip()
    if not needle:
        return None
    needle = _VALUE_ALIASES.get(needle, needle)

    candidates = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    keywords = _FIELD_KEYWORDS.get(field_name or "", ())

    # 1) 라벨 키워드가 있는 줄 중에서 값을 담은 줄.
    #    키워드가 범위를 좁혀주므로 '없음' 처럼 짧은 값도 안전하다.
    for kw in keywords:
        for line in candidates:
            if kw in line and _line_matches(line, needle):
                return line

    # 2) 키워드로 못 찾았다면, 짧은 값은 포기한다.
    #    '3' 같은 값은 아무 줄에나 걸려 엉뚱한 근거를 만든다.
    if len(needle) < _MIN_NEEDLE_LEN and len(_digits(needle)) < 3:
        return None

    for line in candidates:
        if _line_matches(line, needle):
            return line

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


def _parse_confidence_scores(extract_response: dict) -> dict[str, float]:
    """
    choices[0].confidence_score 에서 필드별 숫자 점수를 뽑는다.

    JSON 문자열로 들어온다:
      "confidence_score": "{\\"wage_amount\\": 0.9661, ...}"
    없거나 형식이 다르면 빈 dict — 등급 문자열로 대체된다.
    """
    try:
        raw = extract_response["choices"][0].get("confidence_score")
    except (KeyError, IndexError):
        return {}

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}

    if not isinstance(raw, dict):
        return {}

    return {
        k: float(v)
        for k, v in raw.items()
        if isinstance(v, (int, float))
    }


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
    scores = _parse_confidence_scores(extract_response)

    fields: dict[str, ExtractedField] = {}
    for name in FIELD_DESCRIPTIONS:
        value = values.get(name)
        if isinstance(value, str) and not value.strip():
            value = None  # 모델이 빈 문자열로 "없음"을 표현하는 경우가 있다
        fields[name] = ExtractedField(
            value=value,
            confidence=_confidence_from_upstage(
                confidences.get(name),
                value is not None,
                scores.get(name),
            ),
            source_text=_find_source_text(source_text_pool, value, name),
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
