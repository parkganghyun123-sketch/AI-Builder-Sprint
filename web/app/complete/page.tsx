"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import { getSignStatus } from "@/lib/api";
import { DOCUMENT_STATUS_META } from "@/lib/constants";
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
  // ⚠️ 보관함에서 들어왔는데 스텝이 "5. 서명"으로 표시되면
  //    사용자는 서명 화면으로 되돌아온 줄 안다. 실제로 그런 신고가 있었다.
  const [fromArchive, setFromArchive] = useState(false);
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
    // 보관함에서 ?id= 로 들어왔는지. 스텝 표시가 달라진다.
    setFromArchive(Boolean(idParam));
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
              : "서명 상태를 확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
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
      <ScreenShell step={fromArchive ? 6 : 5} title="서명 상태 준비 중">
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            문서를 확인하는 중이에요.
          </p>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  if (!documentId) {
    return (
      <ScreenShell
        step={fromArchive ? 6 : 5}
        title="확인할 서명 요청이 없어요"
        description={
          fromArchive
            ? "이 문서를 찾지 못했어요. 보관함에서 다시 선택해 주세요."
            : "서명 요청을 먼저 보내 주세요."
        }
      >
        <ButtonLink href={fromArchive ? "/archive" : "/sign"} className="w-full">
          {fromArchive ? "보관함으로 돌아가기" : "서명 요청으로 돌아가기"}
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
      step={fromArchive ? 6 : 5}
      title={
        isCompleted
          ? "계약 체결이 완료됐어요"
          : isFailed
            ? "서명 요청 상태를 확인해 주세요"
            : "서명 진행 상황"
      }
      description="서명이 끝났는지 자동으로 확인하고 있어요."
    >
      {isCompleted && (
        <Card className="text-center">
          <div aria-hidden="true" className="text-5xl">
            ✅
          </div>
          <p className="mt-4 text-xl font-extrabold tracking-tighter text-ink">
            양쪽 서명이 모두 끝났어요
          </p>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            아래 버튼으로 체결된 문서를 받을 수 있어요.
            보낸 기록과 최신 서명 상황은 페어사인 보관함에서도 다시 확인할 수
            있습니다.
          </p>
        </Card>
      )}

      {status ? (
        <>
          <DocumentStatusBadge status={status.status} />

          {/* 누가 누구와 맺은 계약인가.
              ⚠️ 우리 DB에 저장된 값이 아니다. 문서를 열 때마다 모두싸인에서
                 읽어온다. 이름을 우리가 쌓으면 보관 기간과 삭제 책임이 생긴다. */}
          {status.participants.length > 0 && (
            <Card>
              <h2 className="text-sm font-extrabold text-ink">
                <span aria-hidden="true">✍️ </span>
                {status.title}
              </h2>
              <ul className="mt-3 flex flex-col gap-2">
                {status.participants.map((party) => (
                  <li
                    key={`${party.order}-${party.name}`}
                    className="flex items-center justify-between gap-3 rounded-field border border-brand-line bg-white px-4 py-3"
                  >
                    <span className="text-sm font-bold text-ink">
                      <span className="mr-2 text-xs font-semibold text-ink-muted">
                        {party.order}번째
                      </span>
                      {party.name}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-1 text-xs font-bold ${
                        party.signed
                          ? "bg-emerald-100 text-emerald-900"
                          : "bg-slate-200 text-slate-700"
                      }`}
                    >
                      {party.signed ? "서명 완료" : "서명 대기"}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs leading-relaxed text-ink-muted">
                화면을 열 때마다 최신 서명 상황을 확인하며, 페어사인에 따로
                보관하지 않습니다.
              </p>
            </Card>
          )}

          <Card>
            <h2 className="text-sm font-extrabold text-ink">현재 서명 현황</h2>
            <dl className="mt-3 flex flex-col gap-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-muted">서명 상태</dt>
                <dd className="font-bold text-ink">
                  {DOCUMENT_STATUS_META[status.status].title}
                </dd>
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
              ? "서명 상태 확인하는 중"
              : "아직 상태를 받지 못했어요."}
          </p>
        </Card>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">서명 상태를 확인하지 못했어요</p>
          <p className="mt-1">{error}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => setRetry((value) => value + 1)}
            disabled={loading}
          >
            다시 확인
          </Button>
        </div>
      )}

      {!error && loading && status && !isCompleted && !isFailed && (
        <p aria-live="polite" className="text-center text-sm text-ink-muted">
          진행 상황을 다시 확인하는 중
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
            체결 문서 내려받기
          </a>
        )}

        {/* ⚠️ 체결은 됐는데 링크가 없으면 사용자는 버튼이 왜 없는지 모른다.
               다운로드 주소는 유효시간이 10분이라 만료되면 null 로 온다.
               버튼을 감추기만 하면 "다운로드가 안 되는 서비스"로 보인다. */}
        {isCompleted && !status?.download_url && (
          <p className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
            문서 내려받기 버튼의 사용 시간이 지났어요. 아래 버튼을 눌러 새로
            받아 주세요.
            <Button
              variant="secondary"
              className="mt-3 w-full"
              onClick={() => setRetry((value) => value + 1)}
              disabled={loading}
            >
              내려받기 버튼 새로 받기
            </Button>
          </p>
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
