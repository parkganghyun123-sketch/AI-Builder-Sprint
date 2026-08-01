"""
최저임금 고시가 바뀌었는지 확인한다.

⚠️ 이 스크립트는 **코드를 고치지 않는다.** 다르면 알려주기만 한다.

--- 왜 자동 반영하지 않는가 ---

최저임금은 판정의 기준값이다. 외부에서 받아 그대로 쓰면

  1. 재현성이 깨진다
     "같은 계약서면 항상 같은 판정" 이 이 제품의 핵심 주장이다.
     외부 값이 바뀌면 어제 통과한 계약이 오늘 위반이 된다.

  2. 외부 장애가 판정 장애가 된다
     API가 죽으면 최저임금 비교를 못 한다.

  3. 잘못된 값을 알아챌 방법이 없다
     AI가 읽은 값은 코드가 상식 검사를 한다(app/ai/extract.py).
     그런데 최저임금은 **기준** 이라서 대조할 대상이 없다.
     API가 1,032원을 주면 그대로 믿게 된다.

  4. 고시 시점과 데이터 반영 시점이 다르다
     1월 1일 적용인데 데이터가 3월에 갱신될 수도 있다.

그래서 값은 constants.py 가 소유하고, 이 스크립트는 **감시자** 역할만 한다.
사람이 고시를 확인하고 손으로 반영한다. 1년에 한 번이면 충분하다.

--- 실행 ---

    cd backend
    python scripts/check_minimum_wage.py

    # 공공데이터포털 API 키가 있으면 자동 조회
    PUBLIC_DATA_API_KEY=... python scripts/check_minimum_wage.py

--- 자동화하려면 ---

GitHub Actions 로 매년 8~9월(다음 해 고시 직후)에 이 스크립트를 돌리고,
차이가 있으면 이슈를 만들게 하면 된다. 코드 수정은 여전히 사람이 한다.

    # .github/workflows/minimum-wage-check.yml
    on:
      schedule:
        - cron: "0 0 1 8,9,10 *"   # 8·9·10월 1일
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.validation.constants import MINIMUM_WAGE_BY_YEAR  # noqa: E402

# 고용노동부_연도별 최저임금 (공공데이터포털)
# https://www.data.go.kr/data/15068774/fileData.do
DATASET_PAGE = "https://www.data.go.kr/data/15068774/fileData.do"
OPEN_API = "https://api.odcloud.kr/api/15068774/v1/uddi:"

MOEL_NOTICE = "https://www.moel.go.kr/policy/policydata/list.do"


def fetch_from_open_api(api_key: str) -> dict[int, int] | None:
    """
    공공데이터포털 오픈 API 조회.

    데이터셋마다 uddi 가 달라 실패할 수 있다. 실패해도 스크립트는 계속 간다 —
    어차피 사람이 고시를 확인하는 게 최종 근거다.
    """
    url = OPEN_API + "?" + urllib.parse.urlencode(
        {"serviceKey": api_key, "page": 1, "perPage": 50}
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  API 조회 실패: {type(e).__name__}")
        return None

    found: dict[int, int] = {}
    for row in data.get("data", []):
        year = wage = None
        for key, value in row.items():
            text = str(value)
            if "연도" in key or "년도" in key:
                digits = "".join(c for c in text if c.isdigit())
                if len(digits) == 4:
                    year = int(digits)
            if "시간" in key or "시급" in key:
                digits = "".join(c for c in text if c.isdigit())
                if digits:
                    wage = int(digits)
        if year and wage:
            found[year] = wage
    return found or None


def main() -> None:
    today = date.today()
    print("최저임금 기준값 확인\n")
    print("코드에 들어 있는 값 (app/validation/constants.py)")
    for year in sorted(MINIMUM_WAGE_BY_YEAR):
        print(f"  {year}년  {MINIMUM_WAGE_BY_YEAR[year]:,}원")

    latest = max(MINIMUM_WAGE_BY_YEAR)
    print()

    api_key = os.environ.get("PUBLIC_DATA_API_KEY", "").strip()
    if api_key:
        print("공공데이터포털 조회 중...")
        remote = fetch_from_open_api(api_key)
        if remote:
            diffs = [
                (y, MINIMUM_WAGE_BY_YEAR.get(y), w)
                for y, w in sorted(remote.items())
                if MINIMUM_WAGE_BY_YEAR.get(y) != w
            ]
            if diffs:
                print("\n⚠️  코드와 다른 값이 있습니다. 고시를 확인하고 손으로 반영하세요.")
                for year, ours, theirs in diffs:
                    ours_text = f"{ours:,}원" if ours else "없음"
                    print(f"  {year}년  코드 {ours_text}  /  공공데이터 {theirs:,}원")
                print(f"\n  고시 확인: {MOEL_NOTICE}")
                sys.exit(1)
            print("  일치합니다.")
    else:
        print("PUBLIC_DATA_API_KEY 가 없어 자동 조회를 건너뜁니다.")
        print(f"  데이터셋: {DATASET_PAGE}")

    # 다음 해 값이 없으면 알려준다.
    # 최저임금은 보통 8월 초에 다음 해 값이 고시된다.
    if today.month >= 8 and (today.year + 1) not in MINIMUM_WAGE_BY_YEAR:
        print(f"\n⚠️  {today.year + 1}년 최저임금이 코드에 없습니다.")
        print("    보통 8월 초에 다음 해 값이 고시됩니다. 확인 후 반영하세요.")
        print(f"    {MOEL_NOTICE}")
        sys.exit(1)

    print(f"\n✅ 최신 반영 연도: {latest}년")


if __name__ == "__main__":
    main()
