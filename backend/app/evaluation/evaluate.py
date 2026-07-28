"""
필드별 추출 정확도 측정 (A-5).

⚠️ 이 평가셋은 실제 계약서 사진이 아니라, specs.py의 정답값을 그대로
   그려서 만든 합성(synthetic) 벤치마크다. 손글씨·조명·기울어짐 같은
   실제 촬영 조건은 반영되지 않는다. "Upstage 추출 파이프라인이 정해진
   형식을 얼마나 정확히 복원하는가"를 재는 것이며, "실제 계약서 사진
   정확도"라고 과장하지 않는다. (평가 방법의 한계를 숨기지 않는다)

실행:
    cd backend
    python -m app.evaluation.generate_contracts   # 최초 1회
    python -m app.evaluation.evaluate              # 실제 API 호출, 비용 발생

결과는 app/evaluation/results.json 에 저장된다.
"""

import asyncio
import json
import re
from pathlib import Path

from app.ai.extract import extract_contract_terms
from app.evaluation.specs import CONTRACT_SPECS
from app.schemas import ContractTerms

CONTRACTS_DIR = Path(__file__).parent / "contracts"
RESULTS_PATH = Path(__file__).parent / "results.json"

# 핵심 4필드 — 팀 작업지시서의 Day 2 완료 기준
CORE_FIELDS = ["wage_amount", "work_start_time", "break_start_time", "contract_start"]

_DIGITS = re.compile(r"\d+")


def _digits_only(value) -> str:
    return "".join(_DIGITS.findall(str(value))) if value is not None else ""


def _norm_text(value) -> str:
    return re.sub(r"\s+", "", str(value)) if value is not None else ""


# 필드별 비교 방식. 기본은 공백 제거 후 문자열 비교.
_NUMERIC_FIELDS = {"contract_start", "contract_end", "work_days_per_week", "wage_amount"}


def _matches(field: str, expected, actual) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field in _NUMERIC_FIELDS:
        return _digits_only(expected) == _digits_only(actual)
    return _norm_text(expected) == _norm_text(actual)


def score_contract(spec: dict, terms: ContractTerms) -> dict:
    per_field = {}
    for field in CONTRACT_SPECS[0]:
        if field in ("id", "note"):
            continue
        expected = spec[field]
        actual = getattr(terms, field).value
        per_field[field] = {
            "expected": expected,
            "actual": actual,
            "correct": _matches(field, expected, actual),
        }
    return per_field


async def run() -> dict:
    all_results = {}
    for spec in CONTRACT_SPECS:
        img_path = CONTRACTS_DIR / f"{spec['id']}.png"
        file_bytes = img_path.read_bytes()
        terms = await extract_contract_terms(file_bytes, img_path.name)
        all_results[spec["id"]] = {
            "note": spec["note"],
            "fields": score_contract(spec, terms),
        }
    return all_results


def summarize(all_results: dict) -> dict:
    fields = [f for f in CONTRACT_SPECS[0] if f not in ("id", "note")]
    per_field_accuracy = {}
    for field in fields:
        total = len(all_results)
        correct = sum(1 for r in all_results.values() if r["fields"][field]["correct"])
        per_field_accuracy[field] = {"correct": correct, "total": total}

    overall_correct = sum(a["correct"] for a in per_field_accuracy.values())
    overall_total = sum(a["total"] for a in per_field_accuracy.values())

    core_correct = sum(per_field_accuracy[f]["correct"] for f in CORE_FIELDS)
    core_total = sum(per_field_accuracy[f]["total"] for f in CORE_FIELDS)

    return {
        "per_field": per_field_accuracy,
        "overall": {"correct": overall_correct, "total": overall_total},
        "core_fields": {"correct": core_correct, "total": core_total, "fields": CORE_FIELDS},
    }


def print_report(all_results: dict, summary: dict) -> None:
    print(f"\n{'필드':<24}{'정확도':>10}")
    print("-" * 34)
    for field, acc in summary["per_field"].items():
        pct = 100 * acc["correct"] / acc["total"]
        print(f"{field:<24}{acc['correct']}/{acc['total']} ({pct:5.1f}%)")

    print("-" * 34)
    overall = summary["overall"]
    print(
        f"{'전체':<24}{overall['correct']}/{overall['total']} "
        f"({100 * overall['correct'] / overall['total']:.1f}%)"
    )
    core = summary["core_fields"]
    print(
        f"{'핵심 4필드(시급·근로시간':<10}...) {core['correct']}/{core['total']} "
        f"({100 * core['correct'] / core['total']:.1f}%)"
    )

    print("\n틀린 항목:")
    for contract_id, result in all_results.items():
        wrong = [f for f, r in result["fields"].items() if not r["correct"]]
        if wrong:
            print(f"  {contract_id} ({result['note']}):")
            for f in wrong:
                r = result["fields"][f]
                print(f"    - {f}: 정답={r['expected']!r} 추출={r['actual']!r}")


def main() -> None:
    all_results = asyncio.run(run())
    summary = summarize(all_results)
    RESULTS_PATH.write_text(
        json.dumps({"results": all_results, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_report(all_results, summary)
    print(f"\n저장: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
