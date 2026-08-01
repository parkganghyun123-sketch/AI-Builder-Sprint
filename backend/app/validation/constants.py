"""검증 엔진에서 사용하는 시점 고정 법정 기준.

값을 변경할 때는 KB.md의 공식 출처와 적용 기간을 먼저 갱신한다.
"""

STANDARD_YEAR = 2026

# KB.md: KB-MW-2026 / SRC-MINWAGE-2026
# 최저임금위원회: https://www.minimumwage.go.kr/minWage/policy/decisionMain.do
MINIMUM_WAGE_2026 = 10_320
MINIMUM_WAGE_SOURCE_ID = "SRC-MINWAGE-2026"

# 연도별 최저임금 (시간급, 원)
#
# ⚠️ 이 값을 외부 API에서 실시간으로 가져오지 않는다.
#
#    판정에 쓰는 기준값이라 외부에 맡기면
#      · 같은 계약서에 다른 판정이 나올 수 있다 (재현성이 이 제품의 핵심 주장이다)
#      · API가 죽으면 판정도 멈춘다
#      · 잘못된 값이 와도 대조할 대상이 없어 알아챌 방법이 없다
#
#    대신 여기에 상수로 두고, 새 고시가 나면
#    scripts/check_minimum_wage.py 가 알려준다. 반영은 사람이 한다.
#
# 출처: 고용노동부 고시
#   2026 https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=18144
#   2025 https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=16902
MINIMUM_WAGE_BY_YEAR: dict[int, int] = {
    2024: 9_860,
    2025: 10_030,
    2026: 10_320,
}


def minimum_wage_for(year: int) -> tuple[int, int]:
    """
    해당 연도의 최저임금과 실제 적용된 기준 연도.

    표에 없는 연도(아직 고시 안 된 미래, 너무 오래된 과거)는
    가장 가까운 연도 값을 쓰고 그 사실을 함께 돌려준다.
    화면과 계약서에 "○○년 기준" 으로 표시해 오해를 막기 위해서다.
    """
    if year in MINIMUM_WAGE_BY_YEAR:
        return MINIMUM_WAGE_BY_YEAR[year], year

    known = sorted(MINIMUM_WAGE_BY_YEAR)
    nearest = known[0] if year < known[0] else known[-1]
    return MINIMUM_WAGE_BY_YEAR[nearest], nearest


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

# KB.md: KB-MINOR-WORKING-TIME / SRC-LSA-69, SRC-LSA-70
# 근로기준법 제69조·제70조 (2026-07-29 확인)
MINOR_AGE_LIMIT = 18
MINOR_DAILY_HOURS = 7.0
MINOR_WEEKLY_HOURS = 35.0
MINOR_EXT_DAILY_HOURS = 1.0
MINOR_EXT_WEEKLY_HOURS = 5.0
MINOR_NIGHT_START = "22:00"
MINOR_NIGHT_END = "06:00"
MINOR_SOURCE_ID = "SRC-LSA-69"
MINOR_NIGHT_SOURCE_ID = "SRC-LSA-70"

# KB.md: KB-SEVERANCE-ELIGIBILITY / SRC-ERBA-4, SRC-ERBA-8,
# SRC-MOEL-SEVERANCE-2025 (2026-07-30 확인)
# 금액은 계산하지 않고 계약상 예정 기간·주 소정근로시간 두 조건만 확인한다.
SEVERANCE_MIN_WEEKLY_HOURS = 15.0
SEVERANCE_CONTINUOUS_YEARS = 1
SEVERANCE_SOURCE_IDS = (
    "SRC-ERBA-4",
    "SRC-ERBA-8",
    "SRC-MOEL-SEVERANCE-2025",
)

# KB.md: KB-ANNUAL-LEAVE / SRC-LSA-60, SRC-LSA-11, SRC-LSA-18
ANNUAL_LEAVE_SOURCE_IDS = ("SRC-LSA-60", "SRC-LSA-11", "SRC-LSA-18")

# KB.md: KB-DISMISSAL-NOTICE / SRC-LSA-26
DISMISSAL_NOTICE_MIN_MONTHS = 3
DISMISSAL_NOTICE_SOURCE_ID = "SRC-LSA-26"

# KB.md: KB-PROBATION-MINIMUM-WAGE / SRC-MWA-5, SRC-MINWAGE-2026
PROBATION_DISCOUNT_RATE = 0.10
PROBATION_MIN_CONTRACT_YEARS = 1
PROBATION_MAX_MONTHS = 3
PROBATION_MINIMUM_WAGE_2026 = int(MINIMUM_WAGE_2026 * (1 - PROBATION_DISCOUNT_RATE))
PROBATION_SOURCE_IDS = (
    "SRC-MWA-5",
    "SRC-MWA-DECREE-3",
    "SRC-MINWAGE-2026",
)

# KB.md: KB-SOCIAL-INSURANCE
SOCIAL_INSURANCE_WEEKLY_HOURS = 15.0
SOCIAL_INSURANCE_MONTHLY_HOURS = 60.0
SOCIAL_INSURANCE_SOURCE_IDS = (
    "SRC-EASYLAW-EMPLOYMENT-INSURANCE",
    "SRC-NHIS-DECREE-9",
    "SRC-NPS-COVERAGE",
    "SRC-IACI-COVERAGE",
)

# KB.md: KB-PREGNANT-WORKER / SRC-LSA-74, SRC-LSA-70
# 근로기준법 제74조제5항·제7항·제8항, 제70조제2항 (2026-07-31 확인)
STATUTORY_DAILY_HOURS = 8.0  # 법정근로시간(1일) — 시간외근로 판단 기준
PREGNANT_STATUTORY_WEEKLY_HOURS = 40.0  # 법정근로시간(1주) — 시간외근로 판단 기준
PREGNANT_SHORTENED_EARLY_WEEK_MAX = 12  # 임신 12주 이내
PREGNANT_SHORTENED_LATE_WEEK_MIN = 32  # 임신 32주 이후 (2025-02-23 시행 확대)
PREGNANT_SHORTENED_DAILY_HOURS = 2
PREGNANT_NIGHT_START = MINOR_NIGHT_START
PREGNANT_NIGHT_END = MINOR_NIGHT_END
PREGNANT_OVERTIME_SOURCE_IDS = ("SRC-LSA-50", "SRC-LSA-74")
PREGNANT_SHORTENED_SOURCE_ID = "SRC-LSA-74"
PREGNANT_NIGHT_SOURCE_ID = "SRC-LSA-70"

# KB.md: KB-POSTPARTUM-WORKER / SRC-LSA-71
# 근로기준법 제71조 (2026-07-31 확인)
# ⚠️ 임신 중과는 다른 규정이다. 임신 중은 시간외근로 "전면 금지"(제74조제5항),
#    산후 1년 이내는 단체협약이 있어도 넘을 수 없는 "상한"(1일 2시간·1주 6시간·
#    1년 150시간)이다. 같은 취급으로 합치지 않는다.
POSTPARTUM_DAILY_OVERTIME_LIMIT = 2.0
POSTPARTUM_WEEKLY_OVERTIME_LIMIT = 6.0
POSTPARTUM_YEARLY_OVERTIME_LIMIT = 150.0  # 계약 조건만으로는 판정하지 않음
POSTPARTUM_OVERTIME_SOURCE_ID = "SRC-LSA-71"
