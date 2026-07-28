import { CHECK_STATUS_META } from "@/lib/constants";
import type { CheckResult, ContractTerms } from "@/lib/types";

/**
 * 판정 결과 카드 — 결론 + 근거 3종(📄/⚖️/🧮) + 한계.
 *
 * 값은 전부 백엔드 ValidationReport 반환값이다. 프론트는 계산하지 않는다.
 * 📄 계약서 근거는 CheckResult가 아니라 해당 항목의 ExtractedField.source_text 에서 온다.
 */
export function CheckResultCard({
  check,
  sourceText,
}: {
  check: CheckResult;
  /** 관련 조건의 ExtractedField.source_text (있으면 📄 근거로 표시) */
  sourceText?: string | null;
}) {
  const meta = CHECK_STATUS_META[check.status];

  return (
    <div className={`rounded-card border bg-white p-6 shadow-card ${meta.ring}`}>
      <div className="flex items-center gap-2">
        <span className="text-lg">{meta.icon}</span>
        <span className="font-extrabold text-ink">{check.label}</span>
        <span
          className={`ml-auto rounded-full px-3 py-1 text-xs font-bold ${meta.chip}`}
        >
          {meta.label}
        </span>
      </div>

      <dl className="mt-4 flex flex-col gap-2 rounded-field bg-brand-tint/70 p-4 text-sm">
        {sourceText && (
          <div className="flex gap-2">
            <dt className="w-28 shrink-0 font-bold text-brand-deep">
              📄 계약서 근거
            </dt>
            <dd className="text-ink-muted">“{sourceText}”</dd>
          </div>
        )}
        <div className="flex gap-2">
          <dt className="w-28 shrink-0 font-bold text-brand-deep">⚖️ 법령 근거</dt>
          <dd className="text-ink-muted">
            {check.legal_basis}{" "}
            <span className="text-ink-soft">({check.standard_year}년 기준)</span>
          </dd>
        </div>
        {check.calculation && (
          <div className="flex gap-2">
            <dt className="w-28 shrink-0 font-bold text-brand-deep">🧮 계산</dt>
            <dd className="text-ink-muted">{check.calculation}</dd>
          </div>
        )}
      </dl>

      {check.detail && (
        <p className="mt-3 rounded-field border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-ink-muted">
          ⚠️ {check.detail}
        </p>
      )}
    </div>
  );
}

/** 판정 코드 → 근거로 쓸 조건 필드 매핑 */
export const CHECK_SOURCE_FIELD: Record<string, keyof ContractTerms> = {
  MINIMUM_WAGE: "wage_amount",
  WEEKLY_HOLIDAY: "work_days_per_week",
  BREAK_TIME: "break_start_time",
  WEEKLY_HOLIDAY_DAY: "weekly_holiday_day",
};
