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
  const hasSource =
    sourceOrigin === "USER" ||
    (sourceOrigin === "CONTRACT" && Boolean(sourceText || sourceValue));

  return (
    <div className={`rounded-card border bg-white p-6 shadow-card ${meta.ring}`}>
      {/* 법령 근거를 제목 위 눈썹으로 올린다.
          이 카드가 주장하는 것의 출처가 결론보다 먼저 보여야 한다. */}
      <p className="text-xs font-bold tracking-tighter text-brand">
        {check.legal_basis}
        <span className="ml-1.5 font-normal text-ink-soft tabular-nums">
          {check.standard_year}년 기준
        </span>
      </p>

      <div className="mt-1.5 flex flex-wrap items-center gap-2">
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

      {/* 계산식을 카드의 주인공으로 올린다.
          이 서비스가 다른 곳과 다른 지점은 "위반입니다"가 아니라
          **어떻게 그 결론이 나왔는지 숫자로 보여준다**는 것이다.
          그런데 예전에는 이 줄이 근거 목록 맨 아래 작은 글씨로 묻혀 있었다.

          ⚠️ 여기서 계산하지 않는다. 백엔드가 만든 문자열을 그대로 보여준다. */}
      {check.calculation && (
        <p className="tnum mt-4 rounded-field border border-brand-line bg-brand-tint/60 px-4 py-3 text-base font-bold leading-relaxed text-ink">
          {check.calculation}
        </p>
      )}

      {/* ⚠️ 출처가 하나도 없으면 회색 상자만 남는다. 빈 상자는 정보가 아니라
             "뭔가 안 불러와졌나" 하는 인상만 준다. 아예 그리지 않는다. */}
      {hasSource && (
      <dl className="mt-3 flex flex-col gap-3 rounded-field bg-slate-50 p-4 text-sm">
        {sourceOrigin === "USER" && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              ✍️ 확인한 값
            </dt>
            <dd className="break-words text-ink-muted">
              {sourceValue
                ? `직접 입력하거나 고친 값: ${sourceValue}`
                : "비워 둔 항목입니다."}
            </dd>
          </div>
        )}
        {sourceOrigin === "CONTRACT" && sourceText && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              📄 계약서 내용
            </dt>
            <dd className="break-words text-ink-muted">“{sourceText}”</dd>
          </div>
        )}
        {sourceOrigin === "CONTRACT" && !sourceText && sourceValue && (
          <div className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            <dt className="shrink-0 font-bold text-brand-deep sm:w-28">
              📄 계약서에서 읽은 값
            </dt>
            <dd className="break-words text-ink-muted">
              {sourceValue}. 계약서에서 해당 문장을 찾지 못했으니 원본을 직접
              확인해 주세요.
            </dd>
          </div>
        )}
      </dl>
      )}

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
  // 법정근로시간은 "주 며칠"이 초과 여부를 가르는 값이라 근무일 수를 근거로 쓴다.
  STATUTORY_WORKING_HOURS: "work_days_per_week",
  // 야간근로는 시업 시각이 겹침 판단의 출발점이다.
  NIGHT_WORK_ALLOWANCE: "work_start_time",
};
