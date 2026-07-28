"""검증 엔진에서 사용하는 시점 고정 법정 기준.

값을 변경할 때는 KB.md의 공식 출처와 적용 기간을 먼저 갱신한다.
"""

STANDARD_YEAR = 2026

# KB.md: KB-MW-2026 / SRC-MINWAGE-2026
# 최저임금위원회: https://www.minimumwage.go.kr/minWage/policy/decisionMain.do
MINIMUM_WAGE_2026 = 10_320
MINIMUM_WAGE_SOURCE_ID = "SRC-MINWAGE-2026"

# KB.md: KB-WEEKLY-HOLIDAY-TIME / SRC-LSA-18
# 근로기준법 제18조제3항
WEEKLY_HOLIDAY_MIN_HOURS = 15.0
WEEKLY_HOLIDAY_SOURCE_ID = "SRC-LSA-18"

# KB.md: KB-BREAK-2026-07 / SRC-LSA-54-CURRENT
# 근로기준법 제54조. 큰 경계값부터 검사한다.
BREAK_RULES: tuple[tuple[float, int], ...] = (
    (8.0, 60),
    (4.0, 30),
)
BREAK_SOURCE_ID = "SRC-LSA-54-CURRENT"
