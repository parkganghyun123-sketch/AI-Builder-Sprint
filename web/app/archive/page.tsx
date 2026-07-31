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

/**
 * 보관함 한 줄.
 *
 * ⚠️ 카드 전체를 <Link> 로 감싸지 않는다. 안에 다운로드 <a> 가 들어가는데
 *    링크 안의 링크는 유효하지 않은 HTML 이고, 스크린리더에서도 두 목적지가
 *    한 항목으로 읽힌다. 제목만 링크로 두고 나머지는 정보로 둔다.
 */
function ArchiveRow({ item }: { item: ArchiveItem }) {
  const detailHref = `/complete?id=${encodeURIComponent(item.document_id)}`;
  const others = item.participants;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <Link
          href={detailHref}
          className="font-extrabold text-ink underline-offset-4 hover:text-brand hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {item.title}
        </Link>
        <span className="shrink-0 text-xs text-ink-muted">
          {formatDate(item.created_at)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <DocumentStatusBadge status={item.status} />
        <span className="text-sm text-ink-muted">
          서명 {item.signed}/{item.total}명 완료
        </span>
      </div>

      {/* 누구와 맺은 계약인가.
          ⚠️ 이 이름들은 우리 DB에 없다. 목록을 열 때 모두싸인에서 읽어온다. */}
      {others.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-field bg-brand-tint/30 px-4 py-3">
          {others.map((party) => (
            <li
              key={`${party.order}-${party.name}`}
              className="flex items-center justify-between gap-3 text-sm"
            >
              <span className="text-ink">
                <span className="text-ink-muted">{party.order}번째</span>{" "}
                {party.name}
              </span>
              <span
                className={
                  party.signed
                    ? "shrink-0 font-bold text-brand-deep"
                    : "shrink-0 text-ink-muted"
                }
              >
                {party.signed ? "서명 완료" : "서명 대기"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {item.download_url ? (
          <a
            href={item.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-field bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            <span aria-hidden="true">📄</span>
            체결 문서 내려받기 (PDF)
          </a>
        ) : (
          <Link
            href={detailHref}
            className="inline-flex items-center gap-1.5 rounded-field border border-brand-line px-4 py-2 text-sm font-bold text-ink-muted transition hover:border-brand/50 hover:text-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            진행 상황 보기
          </Link>
        )}
      </div>

      {/* 제공자 조회 실패. 목록에서 감추지 않고 "지금 값이 오래됐다"고 알린다. */}
      {item.stale && (
        <p className="text-xs text-ink-soft">
          현재 상태를 다시 확인하지 못해 마지막으로 저장된 값을 보여드리고
          있어요. 항목을 열면 다시 조회합니다.
        </p>
      )}
    </Card>
  );
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
              : "보관함을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.",
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
            로그인 확인하는 중
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
      description="내가 보낸 서명 요청과 상대방, 체결된 문서입니다. 다운로드 주소는 유효시간이 10분이라 화면을 오래 열어두면 만료돼요 — 그때는 새로고침해 주세요."
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
            보관함 불러오는 중
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
        <div className="flex flex-col gap-3">
          {items.map((item) => (
            <ArchiveRow key={item.document_id} item={item} />
          ))}
        </div>
      )}

      <ButtonLink href="/" variant="secondary" className="w-full">
        새 계약 조건 확인하기
      </ButtonLink>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
