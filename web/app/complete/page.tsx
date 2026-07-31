"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { getSignStatus } from "@/lib/api";
import { readSession, updateSession } from "@/lib/session";
import type { SignStatusResponse } from "@/lib/types";

const TERMINAL_STATUSES = new Set([
  "COMPLETED",
  "ABORTED",
  "PROCESSING_FAILED",
]);

function CompleteContent() {
  const searchParams = useSearchParams();
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [status, setStatus] = useState<SignStatusResponse | null>(null);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    // 보관함에서 들어오면 ?id= 로 문서를 지정한다. 없으면 방금 서명 발송한
    // 이 탭의 세션 값을 쓴다(기존 동작 유지).
    const idParam = searchParams.get("id");
    const session = readSession();
    setDocumentId(idParam || session.sign?.documentId || null);
    setReady(true);
  }, [searchParams]);

  useEffect(() => {
    if (!documentId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const next = await getSignStatus(documentId as string);
        if (cancelled) return;
        setStatus(next);
        updateSession({
          sign: {
            documentId: next.document_id,
            status: next.status,
          },
        });

        if (!TERMINAL_STATUSES.has(next.status)) {
          timer = setTimeout(poll, 5_000);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "서명 상태를 확인하지 못했습니다.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [documentId, retry]);

  if (!ready) {
    return (
      <ScreenShell step={5} title="서명 상태 준비 중">
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            문서 식별자를 확인하고 있어요.
          </p>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  if (!documentId) {
    return (
      <ScreenShell
        step={5}
        title="확인할 서명 요청이 없어요"
        description="현재 브라우저 탭에서 서명 요청을 먼저 보내 주세요."
      >
        <ButtonLink href="/sign" className="w-full">
          서명 요청으로 돌아가기
        </ButtonLink>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  const isCompleted = status?.status === "COMPLETED";
  const isFailed =
    status?.status === "ABORTED" ||
    status?.status === "PROCESSING_FAILED";

  return (
    <ScreenShell
      step={5}
      title={
        isCompleted
          ? "서명 상태가 체결 완료로 확인됐어요"
          : isFailed
            ? "서명 요청 상태를 확인해 주세요"
            : "서명 진행 상태"
      }
      description="백엔드가 모두싸인에서 조회한 실제 상태를 5초 간격으로 확인합니다."
    >
      {isCompleted && (
        <Card className="text-center">
          <div aria-hidden="true" className="text-5xl">
            ✅
          </div>
          <p className="mt-4 text-xl font-extrabold tracking-tighter text-ink">
            제공자 상태가 COMPLETED입니다
          </p>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            다운로드 주소가 제공된 경우 아래 버튼으로 문서를 받을 수 있습니다.
            FairSign 보관함에는 자동 저장되지 않습니다.
          </p>
        </Card>
      )}

      {status ? (
        <>
          <DocumentStatusBadge status={status.status} />
          <Card>
            <h2 className="text-sm font-extrabold text-ink">실제 조회 결과</h2>
            <dl className="mt-3 flex flex-col gap-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-muted">제공자 상태</dt>
                <dd className="font-bold text-ink">{status.status}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-muted">서명 인원</dt>
                <dd className="font-bold text-ink">
                  {status.signed}/{status.total}
                </dd>
              </div>
            </dl>
          </Card>
        </>
      ) : (
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            {loading
              ? "모두싸인 상태를 확인하고 있어요…"
              : "아직 상태 응답을 받지 못했습니다."}
          </p>
        </Card>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">상태 조회에 실패했어요</p>
          <p className="mt-1">{error}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => setRetry((value) => value + 1)}
            disabled={loading}
          >
            다시 조회
          </Button>
        </div>
      )}

      {!error && loading && status && !isCompleted && !isFailed && (
        <p aria-live="polite" className="text-center text-sm text-ink-muted">
          다음 상태를 확인하고 있어요…
        </p>
      )}

      <div className="flex flex-col gap-2">
        {isCompleted && status?.download_url && (
          <a
            href={status.download_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-12 items-center justify-center rounded-full bg-brand px-6 py-3 text-sm font-bold text-white shadow-cta transition hover:bg-brand-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            체결 문서 다운로드
          </a>
        )}
        <ButtonLink href="/archive" variant="secondary" className="w-full">
          보관함으로
        </ButtonLink>
        <ButtonLink href="/" variant="ghost" className="w-full">
          처음으로
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}

export default function CompletePage() {
  return (
    <Suspense>
      <CompleteContent />
    </Suspense>
  );
}
