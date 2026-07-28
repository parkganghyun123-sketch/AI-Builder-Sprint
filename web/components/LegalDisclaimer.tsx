import { LEGAL_DISCLAIMER } from "@/lib/constants";

/**
 * 상시 노출 문구. 모든 결과·서명·보관 화면에 고정한다. (CLAUDE.md 절대 규칙 4)
 */
export function LegalDisclaimer() {
  return (
    <p className="rounded-field border border-brand-line bg-brand-tint/60 px-4 py-3 text-xs leading-relaxed text-ink-muted">
      {LEGAL_DISCLAIMER}
    </p>
  );
}
