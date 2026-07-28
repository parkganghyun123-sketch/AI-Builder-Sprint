/**
 * 화면 표시용 상수.
 *
 * ⚠️ 여기 있는 법정 기준값은 "화면 문구·라벨"용이다. 판정 계산에 쓰지 않는다.
 *    판정·계산은 backend/app/validation/ 이 하고 프론트는 결과를 표시만 한다.
 */
import type { CheckStatus, Confidence, DocumentStatus } from "./types";

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

/** 판정 상태별 표시 메타 */
export const CHECK_STATUS_META: Record<
  CheckStatus,
  { icon: string; label: string; chip: string; ring: string }
> = {
  OK: {
    icon: "✅",
    label: "정상",
    chip: "bg-emerald-50 text-emerald-700",
    ring: "border-emerald-100",
  },
  VIOLATION: {
    icon: "⚠️",
    label: "위반",
    chip: "bg-amber-50 text-amber-700",
    ring: "border-amber-200",
  },
  MISSING: {
    icon: "❓",
    label: "누락",
    chip: "bg-amber-50 text-amber-700",
    ring: "border-amber-200",
  },
  UNKNOWN: {
    icon: "🔍",
    label: "판정 불가",
    chip: "bg-slate-100 text-ink-muted",
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
    title: "확인 요청됨",
    icon: "📨",
    message: "내가 입력한 내용입니다. 사장님 확인 전이며 계약 효력이 없습니다.",
    className: "bg-amber-50 text-amber-700 border-amber-200",
    watermark: true,
  },
  TERMS_CONFIRMED: {
    title: "조건 확인됨",
    icon: "🤝",
    message: "양쪽이 내용을 확인했습니다. 서명 전입니다.",
    className: "bg-sky-50 text-sky-700 border-sky-200",
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
    message: "양쪽이 서명한 계약서입니다.",
    className: "bg-emerald-50 text-emerald-700 border-emerald-200",
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
    message: "서명 처리에 실패했습니다. 다시 시도해주세요.",
    className: "bg-red-50 text-red-700 border-red-200",
    watermark: false,
  },
};
