import { CHECK_STATUS_META } from "@/lib/constants";
import type { CheckResult, ContractTerms } from "@/lib/types";

/**
 * 판정 결과 카드 — 결론 + 근거 3종(📄/⚖️/🧮) + 한계.
 *
 * 값은 전부 백엔드 ValidationReport 반환값이다. 프론트는 계산하지 않는다.
 * 📄 계약서 근거는 CheckResult가 아니라 해당 항목의 ExtractedField.source_text 에서 온다.
 * 사용자가 수정한 값은 계약서 근거와 섞지 않고 별도 출처로 표시한다.
 */
export function CheckResultCard({
  check,
  sourceText,
  sourceOrigin,
  sourceValue,
}: {
  check: CheckResult;
  /** 관련 조건의 ExtractedField.source_text (있으면 📄 근거로 표시) */
  sourceText?: string | null;
  /** 현재 검증 입력이 계약서 추출값인지 사용자 입력·수정값인지 구분한다. */
  sourceOrigin?: "CONTRACT" | "USER";
  sourceValue?: string | null;
}) {
  const meta = CHECK_STATUS_META[check.status];

  return (
    <div className={`rounded-card border bg-white p-6 shadow-card ${meta.ring}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span aria-hidden="true" className="text-lg">
          {meta.icon}
        </span>
        <span className="font-extrabold text-ink">{check.label}</span>
        <span
          className={`ml-auto rounded-full px-3 py-1 text-xs font-bold ${meta.chip}`}
        >
          {meta.label}
        </span>
      </div>

      <dl className="mt-4 flex flex-col gap-3 rounded-field bg-brand-tint/70 p-4 text-sm">
        {sourceOrigin === "USER" && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              ✍️ 입력 출처
            </dt>
            <dd className="break-words text-ink-muted">
              {sourceValue
                ? `사용자가 직접 입력하거나 수정한 값: ${sourceValue}`
                : "사용자가 비워 둔 항목입니다."}
              {" "}계약서 원문 근거로 표시하지 않습니다.
            </dd>
          </div>
        )}
        {sourceOrigin === "CONTRACT" && sourceText && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              📄 계약서 근거
            </dt>
            <dd className="break-words text-ink-muted">“{sourceText}”</dd>
          </div>
        )}
        {sourceOrigin === "CONTRACT" && !sourceText && sourceValue && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              📄 입력 출처
            </dt>
            <dd className="break-words text-ink-muted">
              계약서 추출값: {sourceValue}. 연결된 원문 근거 문장은 확인되지
              않았습니다.
            </dd>
          </div>
        )}
        <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
          <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
            ⚖️ 법령 근거
          </dt>
          <dd className="text-ink-muted">
            {check.legal_basis}{" "}
            <span className="text-ink-soft">({check.standard_year}년 기준)</span>
          </dd>
        </div>
        {check.calculation && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              🧮 계산
            </dt>
            <dd className="text-ink-muted">{check.calculation}</dd>
          </div>
        )}
      </dl>

      {check.detail && (
        <p
          className={`mt-3 rounded-field border px-4 py-2.5 text-sm ${
            check.status === "VIOLATION" || check.status === "MISSING"
              ? "border-amber-300 bg-amber-50 text-amber-950"
              : "border-slate-200 bg-slate-50 text-ink-muted"
          }`}
        >
          <span className="font-bold">
            {check.status === "VIOLATION" || check.status === "MISSING"
              ? "주의"
              : "안내"}
            :{" "}
          </span>
          {check.detail}
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
