import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { MOCK_TERMS } from "@/lib/mock";
import type { DocumentStatus } from "@/lib/types";

/**
 * ⑥ 보관함 (기획서 단계 8).
 * 체결 문서 + 판정 이력을 보관한다. 목록 저장소는 C 담당(Supabase, Day 4).
 *
 * TODO(D): 목록 API 연결, 문서 상세/다운로드
 */
const MOCK_ARCHIVE: {
  id: string;
  title: string;
  place: string;
  status: DocumentStatus;
  signedAt: string;
}[] = [
  {
    id: "demo-1",
    title: `${MOCK_TERMS.worker_name.value} 근로계약서`,
    place: String(MOCK_TERMS.workplace.value ?? ""),
    status: "COMPLETED",
    signedAt: "2026-08-01",
  },
];

export default function ArchivePage() {
  return (
    <ScreenShell
      step={6}
      title="보관함"
      description="체결된 계약서와 판정 이력이 보관돼요. 나중에 문제가 생기면 꺼내 쓸 수 있는 증빙입니다."
    >
      {MOCK_ARCHIVE.length === 0 ? (
        <Card className="py-14 text-center">
          <div className="text-4xl">📭</div>
          <p className="mt-3 font-bold text-ink">아직 보관된 계약서가 없어요</p>
          <p className="mt-1 text-sm text-ink-muted">
            계약서를 확인하고 서명하면 여기에 저장됩니다.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          {MOCK_ARCHIVE.map((doc) => (
            <Card key={doc.id} className="flex flex-col gap-4">
              <div className="flex items-start gap-3">
                <span className="text-2xl">📄</span>
                <div>
                  <div className="font-extrabold text-ink">{doc.title}</div>
                  <div className="mt-0.5 text-sm text-ink-muted">
                    {doc.place} · 체결일 {doc.signedAt}
                  </div>
                </div>
              </div>

              <DocumentStatusBadge status={doc.status} />

              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" className="px-4 py-2 text-xs" disabled>
                  문서 열기
                </Button>
                <Button variant="secondary" className="px-4 py-2 text-xs" disabled>
                  다운로드
                </Button>
                <ButtonLink
                  href="/result"
                  variant="secondary"
                  className="px-4 py-2 text-xs"
                >
                  판정 이력 보기
                </ButtonLink>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ButtonLink href="/" className="w-full">
        새 계약서 확인하기
      </ButtonLink>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
