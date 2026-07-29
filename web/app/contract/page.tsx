"use client";

import { useEffect, useState } from "react";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { previewPdf } from "@/lib/api";
import { readSession } from "@/lib/session";
import type { ContractTerms, EntryPath } from "@/lib/types";

export default function ContractPage() {
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setEntryPath(session.entryPath);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!terms) return;

    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    setPdfUrl(null);

    previewPdf({
      terms,
      entry_path: entryPath,
      include_verification: true,
    })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          objectUrl = null;
          return;
        }
        setPdfUrl(objectUrl);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "PDF 미리보기를 만들지 못했습니다.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [entryPath, retry, terms]);

  function downloadDraft() {
    if (!pdfUrl) return;
    const anchor = document.createElement("a");
    anchor.href = pdfUrl;
    anchor.download = "fairsign_work_conditions_draft.pdf";
    anchor.click();
  }

  if (!ready) {
    return (
      <ScreenShell step={4} title="요청서 준비 중">
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            확인한 조건을 불러오고 있어요.
          </p>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  if (!terms) {
    return (
      <ScreenShell
        step={4}
        title="요청서를 만들 조건이 없어요"
        description="현재 브라우저 탭에서 계약 조건을 다시 확인해 주세요."
      >
        <ButtonLink href="/review" className="w-full">
          조건 확인으로 돌아가기
        </ButtonLink>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  return (
    <ScreenShell
      step={4}
      title="근로조건 확인 요청서 미리보기 · 확인 전 초안"
      description="사용자가 확인한 조건을 그대로 백엔드 PDF 생성기에 전달했습니다. 임금이나 다른 조건을 자동으로 바꾸지 않으며, 체결 완료 상태가 확인되기 전 문서입니다."
    >
      <DocumentStatusBadge status="DRAFTING" />

      <p className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
        이 PDF는 어느 입력 경로에서 시작했든 “확인 전 초안” 워터마크가 있는
        근로조건 확인 요청서입니다. 미리보기나 한쪽의 발송만으로 양쪽이
        조건을 확인했다고 표시하지 않습니다.
      </p>

      <Card>
        <h2 className="text-sm font-extrabold text-ink">문서 생성 기준</h2>
        <ul className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-ink-muted">
          <li>· 입력 경로: {entryPath === "PHOTO" ? "사진 추출 후 확인" : "직접 입력"}</li>
          <li>· 내용: 사용자가 확인한 현재 세션의 계약 조건</li>
          <li>· 검증 메모: 백엔드 검증 결과 포함</li>
          <li>· 문서 상태: “확인 전 초안” 워터마크가 있는 요청서</li>
        </ul>
      </Card>

      {loading && (
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            백엔드에서 PDF 초안을 만들고 있어요…
          </p>
        </Card>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">PDF 미리보기를 만들지 못했어요</p>
          <p className="mt-1">{error}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => setRetry((value) => value + 1)}
          >
            다시 시도
          </Button>
        </div>
      )}

      {pdfUrl && (
        <div className="overflow-hidden rounded-card border border-brand-line bg-white shadow-card">
          <iframe
            title="근로조건 확인 요청서 PDF 미리보기"
            src={pdfUrl}
            className="h-[70vh] min-h-[480px] w-full"
          />
        </div>
      )}

      <div className="flex flex-col gap-2">
        {pdfUrl ? (
          <ButtonLink href="/sign" className="w-full">
            요청서 발송 정보 입력으로 →
          </ButtonLink>
        ) : (
          <Button className="w-full" disabled>
            PDF 미리보기 후 발송 정보 입력으로
          </Button>
        )}
        <Button
          variant="secondary"
          className="w-full"
          onClick={downloadDraft}
          disabled={!pdfUrl}
        >
          초안 PDF 다운로드
        </Button>
        <ButtonLink href="/review" variant="ghost" className="w-full">
          조건 다시 수정
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
