"""
실제 촬영 손글씨 계약서 반복 추출 정확도 측정 (A 담당).

합성 벤치마크(app/evaluation/)는 "우리가 그린 대로 정확히 읽어내는가"만 잰다.
이 스크립트는 실제 손글씨 사진에서 같은 API 호출을 --runs 회 반복해서
1) 정답과 얼마나 맞는지, 2) 같은 사진인데도 호출마다 값이 흔들리는지를 같이 잰다.
"100%"보다 "3회 모두 정확, 흔들림 0"이 더 강한 근거가 된다.

사용법 (준비):
    cd ~/AI-Builder-Sprint
    set -a; source .env; set +a

    # 1. 사진을 spikes/fixtures/ 에 넣는다 (예: handwritten_02.png)
    # 2. 정답 라벨 템플릿을 만든다
    python3 spikes/check_extract.py --init spikes/fixtures/handwritten_02.png
    # 3. spikes/fixtures/handwritten_02.json 을 열어 실제 계약서 내용대로 값을 채운다
    #    (모르는 항목은 null로 둔다 = 계약서에 그 항목이 없다는 뜻)

사용법 (측정):
    python3 spikes/check_extract.py spikes/fixtures/handwritten_02.png --runs 3
    python3 spikes/check_extract.py spikes/fixtures --runs 3   # handwritten_*.png 전체 일괄

라벨이 없는 사진은 건너뛰고 안내만 출력한다 (정답 없는 값을 지어내지 않는다).
각 실행의 원본 추출 결과는 <이름>_runs.json 으로 옆에 저장된다.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ai.extract import extract_contract_terms  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

# app/schemas.py ContractTerms 필드와 동일한 순서/이름
FIELDS = [
    "contract_start",
    "contract_end",
    "workplace",
    "job_description",
    "work_start_time",
    "work_end_time",
    "break_start_time",
    "break_end_time",
    "work_days_per_week",
    "weekly_holiday_day",
    "wage_type",
    "wage_amount",
    "has_bonus",
    "other_allowance",
    "payday",
    "payment_method",
    "employer_business_name",
    "employer_phone",
    "employer_address",
    "employer_name",
    "worker_address",
    "worker_contact",
    "worker_name",
]

_DIGITS = re.compile(r"\d+")
_NUMERIC_FIELDS = {"contract_start", "contract_end", "work_days_per_week", "wage_amount"}


def _digits_only(value) -> str:
    return "".join(_DIGITS.findall(str(value))) if value is not None else ""


def _norm_text(value) -> str:
    return re.sub(r"\s+", "", str(value)) if value is not None else ""


def _matches(field: str, expected, actual) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field in _NUMERIC_FIELDS:
        return _digits_only(expected) == _digits_only(actual)
    return _norm_text(expected) == _norm_text(actual)


# 구두점·공백을 모두 뺀 형태. 실패 원인을 가르는 데만 쓴다.
_SYMBOLS = re.compile(r"[^0-9A-Za-z가-힣]")


def _strip_symbols(value) -> str:
    return _SYMBOLS.sub("", str(value)) if value is not None else ""


def _failure_kind(field: str, expected, actual) -> str:
    """
    실패를 세 가지로 나눈다.

    ⚠️ 점수는 바꾸지 않는다. 채점은 _matches 그대로 엄격하게 두고,
       **무엇을 고쳐야 하는지**만 구분한다. 대응이 완전히 다르기 때문이다.

      · 누락 — 값을 아예 못 읽음.        → 확인 관문에서 사람이 입력
      · 오독 — 글자를 다르게 읽음.        → 확인 관문이 필요한 진짜 이유.
                                          코드로 고칠 수 없다.
      · 형식 — 내용은 맞고 표기만 다름.   → 정규화로 코드가 흡수할 수 있다.
                                          (예: '010 8985 -2595', '50000원')

    이 둘을 한 숫자에 섞으면 "정확도 84%" 가 무엇을 뜻하는지 알 수 없다.
    """
    if actual is None:
        return "누락"
    if _strip_symbols(expected) == _strip_symbols(actual):
        return "형식"
    return "오독"


def labels_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def write_template(image_path: Path) -> Path:
    path = labels_path_for(image_path)
    if path.exists():
        print(f"이미 있음, 덮어쓰지 않음: {path}")
        return path
    template = {
        "_note": "실제 계약서 내용대로 값을 채운다. 모르면 null(계약서에 없다는 뜻).",
        **{field: None for field in FIELDS},
    }
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"라벨 템플릿 생성: {path}")
    return path


def load_labels(image_path: Path) -> dict | None:
    path = labels_path_for(image_path)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {field: raw.get(field) for field in FIELDS}


async def run_once(file_bytes: bytes, filename: str) -> dict[str, object]:
    terms = await extract_contract_terms(file_bytes, filename)
    return {field: getattr(terms, field).value for field in FIELDS}


def score_run(labels: dict, actual: dict) -> dict[str, bool]:
    return {field: _matches(field, labels[field], actual[field]) for field in FIELDS}


def instability(run_results: list[dict[str, object]]) -> list[str]:
    unstable = []
    for field in FIELDS:
        values = {_norm_text(r[field]) for r in run_results}
        if len(values) > 1:
            unstable.append(field)
    return unstable


def check_image(image_path: Path, runs: int) -> dict | None:
    labels = load_labels(image_path)
    if labels is None:
        print(f"\n[건너뜀] {image_path.name}: 라벨 없음 (--init 으로 템플릿 생성 후 채워주세요)")
        return None

    print(f"\n=== {image_path.name} ({runs}회) ===")
    file_bytes = image_path.read_bytes()

    run_results = []
    run_scores = []
    for i in range(1, runs + 1):
        actual = asyncio.run(run_once(file_bytes, image_path.name))
        scores = score_run(labels, actual)
        correct = sum(scores.values())
        print(f"  {i}회차: {correct}/{len(FIELDS)}")
        run_results.append(actual)
        run_scores.append(scores)

    unstable_fields = instability(run_results)
    correct_counts = {sum(s.values()) for s in run_scores}

    if len(correct_counts) == 1 and not unstable_fields:
        n = next(iter(correct_counts))
        print(f"  → {runs}회 모두 정확 {n}/{len(FIELDS)}, 흔들림 0")
    else:
        print(f"  → 흔들림 {len(unstable_fields)}개 필드: {', '.join(unstable_fields) or '없음'}")
        wrong_by_run = []
        for i, scores in enumerate(run_scores, start=1):
            wrong = [f for f, ok in scores.items() if not ok]
            if wrong:
                wrong_by_run.append(f"    {i}회차 오답: {', '.join(wrong)}")
        print("\n".join(wrong_by_run))

    # 실패 원인 분류. 1회차 기준으로 필드마다 한 번씩만 보여준다.
    kinds: dict[str, str] = {}
    for field, ok in run_scores[0].items():
        if not ok:
            kinds[field] = _failure_kind(field, labels[field], run_results[0][field])
    if kinds:
        print("  → 실패 원인:")
        for kind in ("오독", "누락", "형식"):
            fields = [f for f, k in kinds.items() if k == kind]
            if fields:
                print(f"      {kind} {len(fields)}건: {', '.join(fields)}")

    out_path = image_path.with_name(f"{image_path.stem}_runs.json")
    out_path.write_text(
        json.dumps(
            {"labels": labels, "runs": run_results, "failure_kinds": kinds},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "image": image_path.name,
        "run_scores": run_scores,
        "unstable_fields": unstable_fields,
        "failure_kinds": kinds,
    }


def resolve_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def print_overall(all_reports: list[dict]) -> None:
    if len(all_reports) <= 1:
        return
    print(f"\n=== 전체 ({len(all_reports)}장) ===")
    grand_correct = grand_total = 0
    all_kinds: dict[str, list[str]] = {"오독": [], "누락": [], "형식": []}
    for report in all_reports:
        total_correct = sum(sum(s.values()) for s in report["run_scores"])
        total_fields = len(FIELDS) * len(report["run_scores"])
        grand_correct += total_correct
        grand_total += total_fields
        print(
            f"  {report['image']}: {total_correct}/{total_fields}, "
            f"흔들림 {len(report['unstable_fields'])}개 필드"
        )
        for field, kind in report.get("failure_kinds", {}).items():
            all_kinds[kind].append(f"{report['image'].split('.')[0]}:{field}")

    if grand_total:
        print(f"\n  합계 {grand_correct}/{grand_total} = {grand_correct / grand_total * 100:.0f}%")

    # ⚠️ 이 분류가 이 스크립트의 결론이다.
    #    "오독"은 코드로 못 고친다 → 사용자 확인 관문이 필요한 근거.
    #    "형식"은 정규화로 흡수 가능 → 코드가 할 일.
    if any(all_kinds.values()):
        print("\n  실패 원인 (1회차 기준):")
        for kind in ("오독", "누락", "형식"):
            if all_kinds[kind]:
                print(f"    {kind} {len(all_kinds[kind])}건: {', '.join(all_kinds[kind])}")
        misread = len(all_kinds["오독"]) + len(all_kinds["누락"])
        print(
            f"\n  → 사람이 확인해야 하는 실패 {misread}건, "
            f"정규화로 흡수 가능한 실패 {len(all_kinds['형식'])}건"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=str(FIXTURES), help="이미지 파일 또는 디렉터리")
    parser.add_argument("--runs", type=int, default=3, help="반복 호출 횟수 (기본 3)")
    parser.add_argument("--init", action="store_true", help="정답 라벨 템플릿만 생성하고 종료")
    args = parser.parse_args()

    target = Path(args.path)

    if args.init:
        if not target.is_file():
            print("--init 은 이미지 파일 경로가 필요합니다.")
            sys.exit(1)
        write_template(target)
        return

    images = resolve_images(target)
    if not images:
        print(f"이미지 없음: {target}")
        sys.exit(1)

    all_reports = [r for img in images if (r := check_image(img, args.runs)) is not None]
    print_overall(all_reports)


if __name__ == "__main__":
    main()
