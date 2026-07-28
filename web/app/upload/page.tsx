import { ScreenShell } from "@/components/ScreenShell";
import { Button, ButtonLink, Card } from "@/components/ui";

/**
 * ① 업로드 (경로 A) — 계약서 사진 업로드 + 자동 추출 (단계 2·3).
 * 실제 업로드/추출 연동은 Part A·C API 확정 후.
 *
 * TODO(Part D):
 * - 파일 선택 / 카메라 촬영 입력, 미리보기, "읽는 중…" 상태
 * - 추출 3회 실패 시 "직접 입력할게요"(경로 B) 노출
 */
const TIPS = [
  "계약서 전체가 프레임 안에 들어오게 찍어주세요",
  "그림자나 빛 반사가 없는 곳에서 찍으면 더 잘 읽혀요",
  "글씨가 흐리면 다시 찍어주세요",
];

export default function UploadPage() {
  return (
    <ScreenShell
      step={1}
      title="계약서 사진 올리기"
      description="시급·근로시간 같은 조건을 자동으로 읽어드려요. 잘못 읽힌 항목은 다음 화면에서 직접 고칠 수 있어요."
    >
      <Card className="flex flex-col items-center gap-4 border-2 border-dashed border-brand-line py-14 text-center">
        <div className="text-4xl">📷</div>
        <div>
          <p className="font-bold text-ink">계약서 사진을 올려주세요</p>
          <p className="mt-1 text-sm text-ink-muted">JPG · PNG · 1장</p>
        </div>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <Button variant="secondary" disabled>
            사진 선택 / 촬영
          </Button>
          <ButtonLink href="/review">업로드</ButtonLink>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-extrabold text-ink">잘 읽히게 찍는 법 💡</h2>
        <ul className="mt-3 flex flex-col gap-2">
          {TIPS.map((t) => (
            <li key={t} className="flex gap-2 text-sm text-ink-muted">
              <span className="text-brand">·</span>
              {t}
            </li>
          ))}
        </ul>
      </Card>

      <div className="flex items-center justify-between">
        <ButtonLink href="/" variant="ghost">
          ← 뒤로
        </ButtonLink>
        <ButtonLink href="/review?path=B" variant="ghost">
          사진이 안 읽히나요? 직접 입력할게요
        </ButtonLink>
      </div>
    </ScreenShell>
  );
}
