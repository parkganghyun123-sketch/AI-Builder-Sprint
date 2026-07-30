/**
 * 화면 표시용 상수.
 *
 * ⚠️ 여기 있는 법정 기준값은 "화면 문구·라벨"용이다. 판정 계산에 쓰지 않는다.
 *    판정·계산은 backend/app/validation/ 이 하고 프론트는 결과를 표시만 한다.
 */
import type {
  CheckStatus,
  Confidence,
  DocumentStatus,
  EntryPath,
} from "./types";

/** 적용 기준 연도 — backend/app/validation/constants.py STANDARD_YEAR */
export const REFERENCE_YEAR = 2026;

/** 2026년 최저임금 (표시용). KB.md KB-MW-2026 / SRC-MINWAGE-2026 */
export const MINIMUM_WAGE_2026 = 10_320;

/** 고용노동부 고객상담센터 */
export const MOEL_HOTLINE = "1350";

/** 모든 결과·서명·보관 화면에 상시 노출하는 고정 문구 */
export const LEGAL_DISCLAIMER =
  "이 서비스는 법정 기준을 자동으로 계산해 알려드립니다. 법률 자문이 아니며, " +
  "개별 상황은 고용노동부 고객상담센터(1350) 또는 전문가와 상담하시기 바랍니다.";

/** 계약서에 없는 항목 고정 문구 */
export const FIELD_NOT_FOUND = "계약서에서 확인되지 않습니다.";

/**
 * 진입 경로별 문서 제목.
 *
 * ⚠️ backend/app/routers/contracts.py DOCUMENT_TITLES 와 반드시 일치시킬 것.
 *    화면이 "근로조건 확인 요청서"라고 안내하는데 실제로 발송된 문서 제목이
 *    "근로계약서"이면 사용자가 받은 메일과 화면이 어긋난다.
 *
 * 사업주가 작성한 것은 계약서지만, 근로자가 만든 것은 "이 조건이 맞나요"를
 * 묻는 확인 요청서다. 근로자가 만든 문서를 '근로계약서'로 보내면
 * 사업주가 이미 합의된 계약으로 오해할 수 있다.
 */
export function documentTitle(entryPath: EntryPath): string {
  return entryPath === "EMPLOYER" ? "근로계약서" : "근로조건 확인 요청서";
}

/** 누가 먼저 서명하는가. 문서를 만든 쪽이 먼저 서명한다. */
export function firstSignerLabel(entryPath: EntryPath): string {
  return entryPath === "EMPLOYER" ? "사장님" : "근로자";
}

/** 판정 상태별 표시 메타 */
export const CHECK_STATUS_META: Record<
  CheckStatus,
  { icon: string; label: string; chip: string; ring: string }
> = {
  OK: {
    icon: "✅",
    label: "기준 충족",
    chip: "bg-emerald-100 text-emerald-900",
    ring: "border-emerald-300",
  },
  VIOLATION: {
    icon: "⚠️",
    label: "기준 벗어남",
    chip: "bg-red-100 text-red-900",
    ring: "border-red-300",
  },
  MISSING: {
    icon: "❓",
    label: "계약서에서 찾지 못함",
    chip: "bg-amber-100 text-amber-900",
    ring: "border-amber-300",
  },
  UNKNOWN: {
    icon: "🔍",
    label: "정보 부족",
    chip: "bg-slate-200 text-slate-900",
    ring: "border-slate-200",
  },
};

/** 신뢰도별 입력칸 표시 — LOW는 노란색으로 사용자 확인을 유도한다 */
export const CONFIDENCE_META: Record<
  Confidence,
  { hint: string | null; inputClass: string }
> = {
  HIGH: { hint: null, inputClass: "border-brand-line" },
  LOW: {
    hint: "잘못 읽었을 수 있어요. 확인해주세요.",
    inputClass: "border-amber-300 bg-amber-50/60",
  },
  NOT_FOUND: {
    hint: FIELD_NOT_FOUND,
    inputClass: "border-slate-200 bg-slate-50",
  },
};

/**
 * 문서 상태 표시 메타 (8종).
 * 서명 전 문서는 "계약서"가 아니라 "근로조건 확인 요청서"로 부른다.
 */
export const DOCUMENT_STATUS_META: Record<
  DocumentStatus,
  {
    title: string;
    icon: string;
    message: string;
    className: string;
    watermark: boolean;
  }
> = {
  DRAFTING: {
    title: "작성 중",
    icon: "📝",
    message: "아직 상대방에게 보내지 않았습니다.",
    className: "bg-slate-50 text-ink-muted border-slate-200",
    watermark: false,
  },
  REVIEW_REQUESTED: {
    title: "근로조건 확인 요청서",
    icon: "📨",
    message:
      "내가 입력한 내용입니다. 사장님 확인 전이며, 체결 완료 상태가 확인되지 않았습니다.",
    className: "bg-amber-50 text-amber-900 border-amber-300",
    watermark: true,
  },
  TERMS_CONFIRMED: {
    title: "조건 확인됨 · 서명 전",
    icon: "🤝",
    message: "확인한 조건으로 서명을 요청하기 전 단계입니다.",
    className: "bg-sky-50 text-sky-900 border-sky-300",
    watermark: false,
  },
  ON_PROCESSING: {
    title: "처리 중",
    icon: "⏳",
    message: "서명 요청을 처리하고 있습니다.",
    className: "bg-sky-50 text-sky-700 border-sky-200",
    watermark: false,
  },
  ON_GOING: {
    title: "서명 진행 중",
    icon: "✍️",
    message: "서명이 진행 중입니다. 아직 체결 전입니다.",
    className: "bg-sky-50 text-sky-700 border-sky-200",
    watermark: false,
  },
  COMPLETED: {
    title: "체결 완료",
    icon: "✅",
    message: "서명 제공자의 체결 완료 상태가 확인되었습니다.",
    className: "bg-emerald-50 text-emerald-900 border-emerald-300",
    watermark: false,
  },
  ABORTED: {
    title: "중단됨",
    icon: "🚫",
    message: "서명이 중단되었습니다.",
    className: "bg-slate-50 text-ink-muted border-slate-200",
    watermark: false,
  },
  PROCESSING_FAILED: {
    title: "처리 실패",
    icon: "⚠️",
    message: "서명 처리에 실패했습니다. 다시 시도해 주세요.",
    className: "bg-red-50 text-red-900 border-red-300",
    watermark: false,
  },
};
