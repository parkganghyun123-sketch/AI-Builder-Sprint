import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { MOCK_REPORT } from "@/lib/mock";

/**
 * ⑤ 전자서명 (기획서 단계 7).
 * POST /contracts/analyze-sign → 검증 → PDF → 모두싸인 서명 요청.
 *
 * ⚠️ 모두싸인은 이메일로 서명 요청을 보낸다 (전화번호 아님).
 * ⚠️ 위반·누락이 남아 있으면 백엔드가 409로 막는다.
 *    사용자가 알고도 진행하려면 proceed_with_violations=true 로 재요청해야 한다.
 *
 * TODO(D): analyzeAndSign() 연결 + ViolationBlockedError 처리 + 상태 폴링
 */
export default function SignPage() {
  const problems = MOCK_REPORT.checks.filter(
    (c) => c.status === "VIOLATION" || c.status === "MISSING",
  );

  return (
    <ScreenShell
      step={5}
      title="전자서명 요청"
      description="양쪽 이메일로 서명 요청을 보내요. 근로자부터 서명합니다."
    >
      <DocumentStatusBadge status="TERMS_CONFIRMED" />

      {problems.length > 0 && (
        <div className="rounded-field border border-amber-200 bg-amber-50 px-4 py-3.5 text-sm text-amber-700">
          <p className="font-bold">
            ⚠️ 아직 확인이 필요한 항목이 {problems.length}건 있어요
          </p>
          <ul className="mt-1.5 list-inside list-disc">
            {problems.map((p) => (
              <li key={p.code}>{p.label}</li>
            ))}
          </ul>
          <p className="mt-2">
            조건을 고치거나, 알고도 진행하려면 아래에서 확인해주세요.
          </p>
        </div>
      )}

      <Card className="flex flex-col gap-4">
        <h2 className="text-sm font-extrabold text-ink">서명 당사자</h2>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-bold text-ink">내 이메일 (근로자)</span>
          <input
            type="email"
            placeholder="name@example.com"
            className="w-full rounded-field border border-brand-line bg-white px-4 py-2.5 text-ink outline-none transition placeholder:text-ink-soft focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-bold text-ink">사장님 이메일</span>
          <input
            type="email"
            placeholder="boss@example.com"
            className="w-full rounded-field border border-brand-line bg-white px-4 py-2.5 text-ink outline-none transition placeholder:text-ink-soft focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>

        <p className="text-xs text-ink-soft">
          서명 요청 발송에만 사용하고, 발송 후 마스킹됩니다.
        </p>
      </Card>

      {problems.length > 0 && (
        <label className="flex items-start gap-2.5 rounded-field border border-brand-line bg-white px-4 py-3 text-sm text-ink-muted">
          <input type="checkbox" className="mt-0.5" />
          <span>
            위 항목을 확인했고, 이대로 서명을 진행할게요.
          </span>
        </label>
      )}

      <div className="flex flex-col gap-2">
        <Button className="w-full" disabled>
          서명 요청 발송 (구현 예정)
        </Button>
        <ButtonLink href="/result" variant="secondary" className="w-full">
          조건 다시 확인
        </ButtonLink>
        <ButtonLink href="/complete" variant="ghost" className="w-full">
          (데모) 양쪽 서명 완료 →
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
