/**
 * ⚠️ MOCK — 화면 개발용 예시 데이터. 실제 계약서·판정 결과가 아니다.
 *
 * 기획서 4장의 가상 예시(시급 10,000원 / 주 3일 6시간)를 schemas.py 형식으로 옮긴 것.
 * API 연결(Day 3) 시 lib/api.ts 호출로 교체한다.
 */
import type { ContractTerms, ValidationReport } from "./types";

const f = (
  value: string | number | null,
  confidence: ContractTerms["wage_amount"]["confidence"] = "HIGH",
  source_text: string | null = null,
) => ({ value, confidence, source_text });

/** 예시 조건 — 시각으로 담는다. 근로시간 계산은 백엔드 property가 한다 */
export const MOCK_TERMS: ContractTerms = {
  contract_start: f("2026-08-01", "HIGH", "2026년 8월 1일부터"),
  contract_end: f("2027-01-31", "HIGH", "2027년 1월 31일까지"),
  workplace: f("○○카페 부산대점", "HIGH", "근무장소: ○○카페 부산대점"),
  job_description: f("음료 제조 및 매장 관리", "HIGH", "업무내용: 음료 제조"),

  work_start_time: f("09:00", "HIGH", "09시 00분부터"),
  work_end_time: f("16:00", "HIGH", "16시 00분까지"),
  break_start_time: f("12:00", "LOW", "휴게시간 12시~"),
  break_end_time: f("12:30", "LOW", "~12시 30분"),

  work_days_per_week: f(3, "HIGH", "주 3일 근무"),
  weekly_holiday_day: f(null, "NOT_FOUND", null),

  wage_type: f("HOURLY", "HIGH", "시간급"),
  wage_amount: f(10_000, "HIGH", "시간급 금 10,000원"),
  has_bonus: f("없음", "HIGH", null),
  other_allowance: f(null, "NOT_FOUND", null),
  payday: f("매월 10일", "HIGH", "임금지급일: 매월 10일"),
  payment_method: f("계좌입금", "HIGH", null),

  employer_business_name: f("○○카페", "HIGH", null),
  employer_phone: f("051-000-0000", "LOW", null),
  employer_address: f("부산광역시 금정구 ○○로", "HIGH", null),
  employer_name: f("김사장", "HIGH", null),
  worker_address: f(null, "NOT_FOUND", null),
  worker_contact: f("010-0000-0000", "HIGH", null),
  worker_name: f("김하늘", "HIGH", null),
};

/** 예시 판정 결과 — 실제로는 POST /contracts/validate 가 반환한다 */
export const MOCK_REPORT: ValidationReport = {
  checks: [
    {
      code: "MINIMUM_WAGE",
      label: "최저임금",
      status: "VIOLATION",
      legal_basis: "최저임금법 · 2026년 적용 최저임금 고시 (SRC-MINWAGE-2026)",
      standard_year: 2026,
      calculation: "시급 10,000원 < 10,320원 (차액 320원)",
      detail: "실제 지급액은 임금 구성·포함항목에 따라 달라질 수 있습니다.",
    },
    {
      code: "WEEKLY_HOLIDAY",
      label: "주휴수당 시간요건",
      status: "OK",
      legal_basis: "근로기준법 제18조제3항·제55조 (SRC-LSA-18)",
      standard_year: 2026,
      calculation: "3일 × 6.5시간 = 주 19.5시간 ≥ 15시간",
      detail:
        "시간 요건만 충족했습니다. 실제 지급은 소정근로일 개근 여부에 따라 결정됩니다.",
    },
    {
      code: "BREAK_TIME",
      label: "휴게시간",
      status: "OK",
      legal_basis: "근로기준법 제54조 (SRC-LSA-54-CURRENT)",
      standard_year: 2026,
      calculation: "1일 6.5시간 근무 → 최소 30분, 확인된 휴게 30분",
      detail: null,
    },
    {
      code: "WEEKLY_HOLIDAY_DAY",
      label: "주휴일 기재",
      status: "MISSING",
      legal_basis: "근로기준법 제17조 (SRC-LSA-17)",
      standard_year: 2026,
      calculation: null,
      detail:
        "확인된 계약 내용에서 주휴일 항목을 찾지 못했습니다. 원본 문서를 함께 확인해 주세요.",
    },
  ],
  estimated_monthly_pay: 845_000,
  wage_shortfall: 27_040,
};
