"""
Upstage Document Parse / Information Extract 스파이크 테스트 (A 담당)

가상 계약서 사진(spikes/fixtures/contract_01.png) → ContractTerms 까지
실제 API로 확인하고, 응답을 spikes/fixtures/에 저장한다.
이 fixture가 예선 제출물 "AI 활용 증빙"이 된다.

실행:
    cd ~/AI-Builder-Sprint
    set -a; source .env; set +a

    python3 spikes/extract_spike.py fixtures        # 1. 실제 API 호출 + fixture 저장
    python3 spikes/extract_spike.py from-fixtures    # 2. 저장된 fixture로 매핑만 재확인 (API 호출 없음)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ai.document_parse import parse_document  # noqa: E402
from app.ai.extract import build_contract_terms, call_information_extract  # noqa: E402
from app.validation.rules import validate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
IMG = FIXTURES / "contract_01.png"


def _print_pipeline_result(parse_result: dict, extract_response: dict) -> None:
    full_text = parse_result.get("content", {}).get("text", "")
    terms = build_contract_terms(extract_response, source_text_pool=full_text)
    print("\n--- ContractTerms ---")
    print(terms.model_dump_json(indent=2))

    print("\n--- 파생값 (코드 계산) ---")
    print(f"  1일 소정근로시간 : {terms.hours_per_day}")
    print(f"  휴게시간(분)      : {terms.break_minutes}")
    print(f"  주 소정근로시간   : {terms.weekly_hours}")
    print(f"  시간급           : {terms.hourly_wage}")

    print("\n--- ValidationReport (B 엔진) ---")
    print(validate(terms).model_dump_json(indent=2))


async def fetch_fixtures() -> None:
    file_bytes = IMG.read_bytes()

    parse_result = await parse_document(file_bytes, IMG.name)
    (FIXTURES / "contract_01_parse.json").write_text(
        json.dumps(parse_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    extract_response = await call_information_extract(file_bytes, "image/png")
    (FIXTURES / "contract_01_extract.json").write_text(
        json.dumps(extract_response, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _print_pipeline_result(parse_result, extract_response)


def from_fixtures() -> None:
    parse_result = json.loads((FIXTURES / "contract_01_parse.json").read_text(encoding="utf-8"))
    extract_response = json.loads(
        (FIXTURES / "contract_01_extract.json").read_text(encoding="utf-8")
    )
    _print_pipeline_result(parse_result, extract_response)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "from-fixtures"
    if cmd == "fixtures":
        asyncio.run(fetch_fixtures())
    elif cmd == "from-fixtures":
        from_fixtures()
    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
