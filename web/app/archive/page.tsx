import { ScreenShell } from "@/components/ScreenShell";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { ButtonLink, Card, Pill } from "@/components/ui";

export default function ArchivePage() {
  return (
    <ScreenShell
      step={6}
      title="보관함은 준비 중이에요"
      description="현재 버전에는 문서 목록을 저장하거나 다시 불러오는 보관 API가 연결되어 있지 않습니다."
    >
      <Card className="py-12 text-center">
        <Pill>준비 중</Pill>
        <div aria-hidden="true" className="mt-5 text-5xl">
          🧰
        </div>
        <h2 className="mt-4 text-xl font-extrabold text-ink">
          이 화면에는 문서를 저장하지 않습니다
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-ink-muted">
          체결 문서는 서명 상태 화면에서 모두싸인이 실제 다운로드 주소를
          제공할 때 바로 내려받아 주세요. 브라우저 세션이나 목 목록을 보관
          기능처럼 표시하지 않습니다.
        </p>
      </Card>

      <ButtonLink href="/" className="w-full">
        새 계약 조건 확인하기
      </ButtonLink>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
