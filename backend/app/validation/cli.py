"""ContractTerms JSON을 ValidationReport JSON으로 변환하는 CLI."""

import argparse
import sys
from pathlib import Path

from app.schemas import ContractTerms
from app.validation.rules import validate


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ContractTerms JSON을 결정론적 규칙으로 검증합니다."
    )
    parser.add_argument(
        "input",
        help="ContractTerms JSON 파일 경로. 표준 입력은 '-'",
    )
    args = parser.parse_args(argv)

    terms = ContractTerms.model_validate_json(_read_input(args.input))
    report = validate(terms)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
