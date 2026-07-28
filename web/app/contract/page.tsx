import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { MINIMUM_WAGE_2026 } from "@/lib/constants";
import { MOCK_TERMS } from "@/lib/mock";

/**
 * ④ 수정본 생성·미리보기 (기획서 단계 6).
 * POST /contracts/preview 가 PDF를 반환한다.
 * 경로 B(MANUAL)는 백엔드가 "확인 전 초안" 워터마크를 찍는다.
 *
 * 서명 전 문서는 "계약서"가 아니라 "근로조건 확인 요청서"로 부른다.
 * TODO(D): previewPdf() 호출 → blob URL 로 미리보기
 */
const CHANGES = [
  {
    label: "시급",
    before: `${Number(MOCK_TERMS.wage_amount.value).toLocaleString()}원`,
    after: `${MINIMUM_WAGE_2026.toLocaleString()}원`,
  },
  { label: "주휴일 기재", before: "없음", after: "추가됨" },
];

export default function ContractPage() {
  return (
    <ScreenShell
      step={4}
      title="수정본 미리보기"
      description="확정한 조건으로 만든 근로조건 확인 요청서입니다. 아직 서명 전이라 계약 효력은 없어요."
    >
      <DocumentStatusBadge status="TERMS_CONFIRMED" />

      <Card>
        <h2 className="text-sm font-extrabold text-ink">무엇이 바뀌었나요 ✍️</h2>
        <div className="mt-3 flex flex-col gap-2">
          {CHANGES.map((c) => (
            <div
              key={c.label}
              className="flex items-center gap-3 rounded-field bg-brand-tint/70 px-4 py-3 text-sm"
            >
              <span className="w-24 shrink-0 font-bold text-ink">{c.label}</span>
              <span className="text-ink-soft line-through">{c.before}</span>
              <span className="text-brand">→</span>
              <span className="font-bold text-brand-deep">{c.after}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="relative overflow-hidden rounded-card border border-brand-line bg-white p-6 shadow-card">
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="rotate-[-18deg] text-4xl font-extrabold text-slate-100">
            확인 전 초안
          </span>
        </div>
        <div className="relative">
          <div className="text-center text-sm font-extrabold text-ink">
            표준근로계약서 (안)
          </div>
          <dl className="mt-4 flex flex-col gap-2 text-sm">
            {[
              ["근로자", String(MOCK_TERMS.worker_name.value ?? "—")],
              ["근무장소", String(MOCK_TERMS.workplace.value ?? "—")],
              ["계약기간", `${MOCK_TERMS.contract_start.value} ~ ${MOCK_TERMS.contract_end.value}`],
              ["소정근로시간", `${MOCK_TERMS.work_start_time.value} ~ ${MOCK_TERMS.work_end_time.value}`],
              ["휴게시간", `${MOCK_TERMS.break_start_time.value} ~ ${MOCK_TERMS.break_end_time.value}`],
              ["시급", `${MINIMUM_WAGE_2026.toLocaleString()}원`],
              ["임금지급일", String(MOCK_TERMS.payday.value ?? "—")],
            ].map(([k, v]) => (
              <div key={k} className="flex border-b border-slate-100 pb-2">
                <dt className="w-32 shrink-0 text-ink-soft">{k}</dt>
                <dd className="font-medium text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-ink-soft">
            실제 PDF는 POST /contracts/preview 에서 생성됩니다. (연결 예정)
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <ButtonLink href="/sign" className="w-full">
          서명 요청하기 →
        </ButtonLink>
        <ButtonLink href="/review" variant="secondary" className="w-full">
          조건 다시 수정
        </ButtonLink>
        <Button variant="ghost" className="w-full" disabled>
          초안 다운로드 (워터마크 포함)
        </Button>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
