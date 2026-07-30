"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { LoginGate } from "@/components/LoginGate";
import { ButtonLink, Card } from "@/components/ui";
import { getMe, listMyDocuments, LoginRequiredError } from "@/lib/api";
import type { ArchiveItem } from "@/lib/types";

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export default function ArchivePage() {
  // 보관함은 로그인한 계정에 연결된 문서만 보여준다. 다른 계정의 목록은
  // 백엔드가 소유자 기준으로 걸러 보내므로(GET /contracts), 여기서는
  // 로그인 여부만 확인한다.
  const [authState, setAuthState] = useState<
    "checking" | "authed" | "guest" | "session-invalid"
  >("checking");
  const [items, setItems] = useState<ArchiveItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then(() => {
        if (!cancelled) setAuthState("authed");
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof LoginRequiredError) {
          setAuthState(
            caught.reason === "SESSION_INVALID" ? "session-invalid" : "guest",
          );
        } else {
          setAuthState("authed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (authState !== "authed") return;
    let cancelled = false;
    listMyDocuments()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof LoginRequiredError) {
          setAuthState(
            caught.reason === "SESSION_INVALID" ? "session-invalid" : "guest",
          );
        } else {
          setError(
            caught instanceof Error
              ? caught.message
              : "보관함 목록을 불러오지 못했습니다.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authState]);

  if (authState === "checking") {
    return (
      <ScreenShell step={6} title="보관함 불러오는 중">
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            로그인 상태를 확인하고 있어요.
          </p>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  if (authState === "guest" || authState === "session-invalid") {
    return (
      <ScreenShell step={6} title="보관함">
        <LoginGate
          title={
            authState === "session-invalid"
              ? "세션이 만료됐어요"
              : "보관함을 보려면 로그인이 필요해요"
          }
          description={
            authState === "session-invalid"
              ? "다시 로그인해 주세요."
              : "내가 보낸 서명 요청 목록은 로그인한 계정에만 연결돼요."
          }
        />
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  return (
    <ScreenShell
      step={6}
      title="보관함"
      description="내가 보낸 서명 요청과 문서 상태입니다. 다운로드 주소는 유효시간이 있어 목록에는 싣지 않습니다 — 항목을 눌러 최신 상태를 다시 조회하세요."
    >
      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">목록을 불러오지 못했어요</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {!error && items === null && (
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            목록을 불러오고 있어요…
          </p>
        </Card>
      )}

      {!error && items !== null && items.length === 0 && (
        <Card className="py-12 text-center">
          <div aria-hidden="true" className="text-5xl">
            📭
          </div>
          <h2 className="mt-4 text-xl font-extrabold text-ink">
            아직 보낸 계약서가 없어요
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-ink-muted">
            조건을 확인하고 서명 요청을 보내면 여기에서 진행 상태를 볼 수
            있어요.
          </p>
        </Card>
      )}

      {!error && items !== null && items.length > 0 && (
        <Card className="flex flex-col divide-y divide-brand-line/60 p-0">
          {items.map((item) => (
            <Link
              key={item.document_id}
              href={`/complete?id=${encodeURIComponent(item.document_id)}`}
              className="flex flex-col gap-2 px-6 py-5 transition first:rounded-t-card last:rounded-b-card hover:bg-brand-tint/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-extrabold text-ink">{item.title}</span>
                <span className="text-xs text-ink-muted">
                  {formatDate(item.created_at)}
                </span>
              </div>
              <DocumentStatusBadge status={item.status} />
              <span className="text-sm text-ink-muted">
                서명 {item.signed}/{item.total}명 완료
              </span>
            </Link>
          ))}
        </Card>
      )}

      <ButtonLink href="/" variant="secondary" className="w-full">
        새 계약 조건 확인하기
      </ButtonLink>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
