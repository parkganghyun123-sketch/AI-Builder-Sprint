"use client";

import { type DragEvent, useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { Button, ButtonLink, Card } from "@/components/ui";
import { extractTerms } from "@/lib/api";
import { startSession } from "@/lib/session";

const TIPS = [
  "계약서 전체가 프레임 안에 들어오게 찍어 주세요.",
  "그림자나 빛 반사가 없는 곳에서 찍으면 더 잘 읽혀요.",
  "글씨가 흐리면 다시 찍어 주세요.",
];

export default function UploadPage() {
  const inputId = useId();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 파일을 영역 위로 끌어온 동안만 true. 시각적 강조에만 쓴다.
  const [dragging, setDragging] = useState(false);

  // ⚠️ 파일은 onDrop 에서만 처리한다. onDragOver(끌어와 올려놓기)에서 업로드하면
  //    의도치 않은 업로드가 생긴다. onDragOver 는 강조 표시만 담당한다.
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (loading) return;
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreviewUrl(null);
      return;
    }

    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(selected: File | null) {
    setError(null);
    if (!selected) {
      setFile(null);
      return;
    }

    const allowed = [
      "image/jpeg",
      "image/png",
      "application/pdf",
    ].includes(selected.type);
    if (!allowed) {
      setFile(null);
      setError("JPG, PNG 또는 PDF 파일 한 개를 선택해 주세요.");
      return;
    }
    setFile(selected);
  }

  async function upload() {
    if (!file || loading) return;
    setLoading(true);
    setError(null);

    try {
      const terms = await extractTerms(file);
      startSession(terms, "PHOTO");
      router.push("/review");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "계약서를 읽지 못했어요. 사진이 흐릿하면 다시 찍어 올려 주세요.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScreenShell
      step={1}
      title="계약서 사진 올리기"
      description="시급·근로시간 같은 조건을 AI가 읽어 드려요. 다음 화면에서 사람이 모든 항목을 확인하고 수정합니다."
    >
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!loading) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center gap-4 rounded-card border-2 border-dashed p-6 py-10 text-center shadow-card transition ${
          dragging
            ? "border-brand bg-brand-tint/50"
            : "border-brand-line bg-white"
        }`}
      >
        {previewUrl ? (
          // 브라우저 메모리에만 만든 미리보기 URL이다.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt="선택한 계약서 미리보기"
            className="max-h-72 w-auto rounded-field border border-brand-line object-contain"
          />
        ) : (
          <div aria-hidden="true" className="text-4xl">
            {file?.type === "application/pdf" ? "📄" : "📷"}
          </div>
        )}

        <div>
          <p className="font-bold text-ink">
            {dragging
              ? "여기에 놓으면 파일이 선택돼요"
              : file
                ? file.name
                : "파일을 이 영역으로 끌어다 놓으세요"}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            또는 아래 버튼으로 선택 · JPG · PNG · PDF · 파일 한 개
          </p>
        </div>

        <input
          id={inputId}
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          capture="environment"
          className="sr-only"
          disabled={loading}
          onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
        />
        <label
          htmlFor={inputId}
          className="inline-flex min-h-12 cursor-pointer items-center justify-center rounded-full border border-slate-400 bg-white px-6 py-3 text-sm font-bold text-ink transition hover:border-brand focus-within:outline focus-within:outline-2 focus-within:outline-brand"
        >
          {file ? "다시 선택" : "사진 선택 / 촬영"}
        </label>

        <Button
          onClick={upload}
          disabled={!file || loading}
          className="w-full sm:w-auto"
          aria-describedby={error ? "upload-error" : undefined}
        >
          {loading ? "계약서를 읽고 있어요…" : "업로드하고 조건 읽기"}
        </Button>

        <p aria-live="polite" className="text-sm text-ink-muted">
          {loading
            ? "처리가 끝날 때까지 중복 제출을 막고 있어요."
            : "파일 원본은 브라우저 저장소에 넣지 않지만, 추출된 계약 조건은 현재 탭의 sessionStorage에 저장됩니다."}
        </p>
      </div>

      {error && (
        <div
          id="upload-error"
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">계약서를 읽지 못했어요</p>
          <p className="mt-1">{error}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={upload}
            disabled={!file || loading}
          >
            다시 시도
          </Button>
        </div>
      )}

      <Card>
        <h2 className="text-sm font-extrabold text-ink">파일 처리 안내</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          선택한 파일은 계약 조건을 읽기 위해 서버로 보냅니다. 서버의 보관
          기간과 삭제 동작은 아직 검증되지 않았습니다. 추출된 텍스트와 이름·
          사업체 정보 등 개인정보가 포함될 수 있는 계약 조건은 현재 브라우저
          탭의 <code>sessionStorage</code>에 저장되며, 탭을 닫을 때까지 남을 수
          있습니다. 검증에 필요하지 않은 사업주 전화·주소와 근로자 주소·
          연락처는 저장 전에 제거합니다.
        </p>
      </Card>

      <Card>
        <h2 className="text-sm font-extrabold text-ink">
          잘 읽히게 찍는 법 <span aria-hidden="true">💡</span>
        </h2>
        <ul className="mt-3 flex flex-col gap-2">
          {TIPS.map((tip) => (
            <li key={tip} className="flex gap-2 text-sm text-ink-muted">
              <span aria-hidden="true" className="text-brand">
                ·
              </span>
              {tip}
            </li>
          ))}
        </ul>
      </Card>

      <div className="flex justify-end">
        <ButtonLink href="/review?path=B" variant="ghost">
          직접 입력할게요
        </ButtonLink>
      </div>
    </ScreenShell>
  );
}
