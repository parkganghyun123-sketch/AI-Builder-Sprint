import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";

/**
 * 체결 완료 — 양쪽 서명이 끝난 계약서.
 * 서명 완료 신호는 백엔드 webhook(/webhooks/modusign)이 수신하고,
 * 프론트는 GET /contracts/{id}/status 로 확인한다.
 */
export default function CompletePage() {
  return (
    <ScreenShell step={6} title="서명이 완료됐어요">
      <Card className="text-center">
        <div className="text-5xl">🎉</div>
        <p className="mt-4 text-xl font-extrabold tracking-tighter text-ink">
          양쪽이 서명한 계약서가 만들어졌어요
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          이제 문제가 생겼을 때 근거로 쓸 수 있는 문서를 갖게 됐어요.
        </p>
      </Card>

      <DocumentStatusBadge status="COMPLETED" />

      <div className="flex flex-col gap-2">
        <Button className="w-full" disabled>
          계약서 다운로드 (구현 예정)
        </Button>
        <ButtonLink href="/archive" variant="secondary" className="w-full">
          보관함으로 →
        </ButtonLink>
        <ButtonLink href="/" variant="ghost" className="w-full">
          처음으로
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
