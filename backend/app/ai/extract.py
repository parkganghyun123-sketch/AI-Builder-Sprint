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
    "wage_amount": (
        "임금 금액. 숫자만, 쉼표(,)와 '원' 없이 (예: '시간급 금 10,000원'이면 '10000'). "
        "⚠️ 손글씨는 자릿수를 띄어 쓰는 경우가 많다. '10 000' 은 '10000' 이고 "
        "'1 900 000' 은 '1900000' 이다. 공백으로 끊어 읽지 말고 한 금액으로 합칠 것. "
        "앞자리를 빠뜨리지 말 것."
    ),
    "has_bonus": "상여금 지급 여부. 계약서에 표기된 대로 '있음' 또는 '없음'.",
    "other_allowance": "기타급여(제수당) 내용. 없으면 null.",
    "payday": (
        "임금 지급일 (예: '매월 10일'). "
        "⚠️ 양식의 인쇄 문구('매월(매주 또는 매일) ___일')를 값으로 쓰지 말 것. "
        "빈칸에 손으로 적힌 날짜가 없으면 null."
    ),
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


_PUNCTUATION_ONLY = re.compile(r"^[\W_]+$")
_LEADING_PUNCTUATION = re.compile(r"^[\W_]+")
_NULL_TOKENS = {"null", "none", "n/a", "na"}


def _normalize_extracted_value(value):
    """
    모델이 '못 찾음'을 JSON null 대신 텍스트로 흘리는 경우가 실제로 관측된다
    (예: 빈 칸 옆 라벨의 ':' 만 값으로 뽑거나, ': null' 처럼 문자열로 반환).
    구두점뿐이거나 'null' 류 플레이스홀더면 NOT_FOUND로 취급한다.
    '없음'처럼 실제 의미가 있는 값은 건드리지 않는다.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or _PUNCTUATION_ONLY.match(stripped):
        return None
    core = _LEADING_PUNCTUATION.sub("", stripped).strip()
    if core.lower() in _NULL_TOKENS:
        return None

    # 체크 표시가 값에 섞여 들어온다: '없음 [✓]' → '없음'
    cleaned = _CHECKMARK.sub("", stripped).strip()

    # 라벨이 값 앞에 붙어 오는 경우: '사업체명 : 편의점' → '편의점'
    #
    # ⚠️ 라벨이 보인다고 통째로 버리면 안 된다.
    #    실제로 그렇게 만들었다가 '사업체명 : 편의점' 의 '편의점' 까지
    #    잃었다. 라벨만 떼고 남는 게 있으면 그것이 값이다.
    cleaned = _strip_label_prefix(cleaned)

    # 라벨을 떼고도 값이 없으면 빈칸이다.
    #   payday 칸이 비어 있는데 '매월(매주 또는 매일) 일' 을 반환한 사례.
    if _looks_like_form_label(cleaned):
        return None

    return cleaned or None


def _strip_label_prefix(text: str) -> str:
    """
    '사업체명 : 편의점' → '편의점'
    라벨만 있으면 빈 문자열이 되어 _looks_like_form_label 이 잡는다.
    """
    if ":" not in text or _TIME_LIKE.search(text):
        return text

    head, _, tail = text.rpartition(":")
    head_compact = re.sub(r"[\s_()\[\]]", "", head)

    # 콜론 앞이 라벨로 보이고 뒤에 내용이 있으면 뒤만 취한다
    if tail.strip() and any(w in head_compact for w in _FIELD_LABEL_WORDS):
        return tail.strip()
    return text


# 체크박스·괄호 표시. 값 뒤에 붙어 오는 경우가 있다.
_CHECKMARK = re.compile(r"[\[\(]\s*[✓✔vVoO×xX√]?\s*[\]\)]")

# 인쇄된 양식 문구의 흔적. 값이 아니라 라벨이다.
_FORM_LABEL_HINTS = (
    "매주 또는 매일",
    "휴일의 경우",
    "약정수당",
    "대체공휴일",
    "필요시",
    "이하",
)

# 표준근로계약서의 항목 이름들.
# 빈칸을 만나면 모델이 이 라벨을 값으로 집어온다.
#   worker_address  → '소 :'
#   worker_contact  → '주연성 락 처 :'
# 양식에 자간이 들어가 있어('주  소', '연 락 처') 조각으로 잘려 나온다.
_FIELD_LABEL_WORDS = (
    "주소", "연락처", "성명", "사업체명", "대표자", "전화",
    "근무장소", "업무의내용", "소정근로시간", "근무일", "휴일",
    "임금", "상여금", "지급일", "지급방법", "서명", "근로계약기간",
)


def _looks_like_form_label(text: str) -> bool:
    """
    추출된 값이 사실은 인쇄된 양식 문구인지 판단.

    빈칸을 만나면 모델이 옆의 인쇄 문구를 값으로 집어오는 일이 있다.
    이것은 '지어낸 값'과 같은 효과를 낸다 — 비어 있는 항목이
    채워진 것처럼 보여 누락 판정이 무력화된다.

    ⚠️ 시각(work_start_time 등)은 'HH:MM' 이라 콜론을 쓴다.
       그 필드는 _normalize_extracted_value 에서 이 함수를 거치기 전에
       형식 검사로 걸러지므로 여기서는 콜론을 라벨 신호로 봐도 된다.
    """
    if any(hint in text for hint in _FORM_LABEL_HINTS):
        return True

    compact = re.sub(r"[\s_()\[\]:]", "", text)

    # 괄호 안내문만 남고 실제 값이 없는 경우: '( ) 요일', '____일'
    if compact in {"일", "요일", "원", "시분", ""}:
        return True

    # 라벨 단어가 통째로 남은 경우: '주소', '연락처', '성명'
    if compact in _FIELD_LABEL_WORDS:
        return True

    # 라벨 조각 + 콜론. 값에는 콜론이 없다(시각은 위 주석 참고).
    #   '소 :'  '주연성 락 처 :'
    if ":" in text and not _TIME_LIKE.search(text):
        return True

    # 라벨 단어를 품고 있으면서 그 외 내용이 거의 없는 경우
    for word in _FIELD_LABEL_WORDS:
        if word in compact and len(compact) <= len(word) + 3:
            return True

    return False


# 'HH:MM' 형태가 들어있는지. 시각 값은 라벨로 오인하면 안 된다.
_TIME_LIKE = re.compile(r"\d{1,2}:\d{2}")


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


# 값이 상식적인 범위인지 코드가 검사한다.
#
# ⚠️ 실측에서 드러난 위험:
#    손글씨 '10 000'(띄어쓰기)을 '0000'으로 읽고 confidence를 HIGH로 냈다.
#    시급 0원은 있을 수 없는데 AI는 자신 있다고 했다.
#    판정에 가장 중요한 필드라 그대로 두면 없는 위반을 만들어낼 수 있다.
#
# AI의 확신을 코드가 검증한다. 말이 안 되면 HIGH여도 LOW로 내려
# 사용자가 반드시 확인하게 만든다. 값 자체는 지우지 않는다 —
# 사용자가 무엇을 고쳐야 하는지 보이려면 남겨야 한다.
_HOURLY_WAGE_RANGE = (1_000, 200_000)
_DAILY_WAGE_RANGE = (10_000, 1_000_000)
_MONTHLY_WAGE_RANGE = (100_000, 20_000_000)

_WAGE_RANGES = {
    "HOURLY": _HOURLY_WAGE_RANGE,
    "DAILY": _DAILY_WAGE_RANGE,
    "MONTHLY": _MONTHLY_WAGE_RANGE,
}

_TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _is_implausible(name: str, value, wage_type: str | None) -> bool:
    """이 값이 코드가 보기에 말이 되는가. 되면 False."""
    if value is None:
        return False
    text = str(value).strip()

    if name == "wage_amount":
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            return True  # 금액인데 숫자가 없다
        amount = int(digits)
        low, high = _WAGE_RANGES.get(wage_type or "", (1_000, 20_000_000))
        return not (low <= amount <= high)

    if name.endswith("_time"):
        return not _TIME_PATTERN.match(text)

    if name == "work_days_per_week":
        digits = re.sub(r"[^\d]", "", text)
        return not digits or not (1 <= int(digits) <= 7)

    return False


def apply_sanity_check(fields: dict[str, ExtractedField]) -> dict[str, ExtractedField]:
    """
    코드가 보기에 이상한 값은 HIGH → LOW 로 내린다.

    화면에서 확인을 요구하게 되고, 검증 단계에서도
    LOW 값으로는 '문제 없음' 판정을 내리지 않는다.
    """
    wage_type = fields["wage_type"].value if "wage_type" in fields else None

    for name, field in fields.items():
        if field.confidence != Confidence.HIGH:
            continue
        if _is_implausible(name, field.value, wage_type):
            fields[name] = field.model_copy(update={"confidence": Confidence.LOW})

    return fields


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


def _squeeze(s: str) -> str:
    """공백 전부 제거. '2026년 8월 1 일' → '2026년8월1일'"""
    return "".join(s.split())


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

    # 공백만 다른 경우. 모델이 '2026년 8월 1 일' 을 '2026년 8월 1일' 로
    # 정규화해 돌려주는 일이 있다(같은 사진에서도 실행마다 달라진다).
    # 공백을 지우고 비교하면 잡힌다.
    if _squeeze(needle) in _squeeze(line):
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
        value = _normalize_extracted_value(values.get(name))
        fields[name] = ExtractedField(
            value=value,
            confidence=_confidence_from_upstage(
                confidences.get(name),
                value is not None,
                scores.get(name),
            ),
            source_text=_find_source_text(source_text_pool, value, name),
        )

    # AI가 자신 있다고 한 값도 코드가 한 번 더 본다.
    return ContractTerms(**apply_sanity_check(fields))


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
