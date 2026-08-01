"use client";

import { useEffect, useState } from "react";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card, SkeletonCard } from "@/components/ui";
import { getValidationState, previewPdf } from "@/lib/api";
import { documentTitle, firstSignerLabel } from "@/lib/constants";
import { readSession } from "@/lib/session";
import type {
  ContractTerms,
  EntryPath,
  ValidationIssue,
} from "@/lib/types";

export default function ContractPage() {
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [workerBirthDate, setWorkerBirthDate] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 필수 항목 누락·값 오류. 하나라도 있으면 PDF를 만들지 않는다.
  // null = 아직 확인 전.
  const [blockingIssues, setBlockingIssues] = useState<
    ValidationIssue[] | null
  >(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setEntryPath(session.entryPath);
    setWorkerBirthDate(session.workerBirthDate);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!terms) return;

    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    setPdfUrl(null);
    setBlockingIssues(null);

    void (async () => {
      // 1) PDF를 만들기 전에 필수 항목·값 오류를 먼저 본다.
      //    비어 있거나 잘못된 값이 있으면 여기서 멈춘다 (0원짜리 계약서 방지).
      let blocking: ValidationIssue[] = [];
      try {
        const state = await getValidationState({
          terms,
          worker_birth_date: workerBirthDate,
        });
        blocking = state.issues.filter((issue) => issue.blocks);
      } catch {
        // 판정을 못 받으면 서버 재검증(422)에 맡기고 미리보기를 시도한다.
        blocking = [];
      }
      if (cancelled) return;
      setBlockingIssues(blocking);
      if (blocking.length > 0) {
        setLoading(false);
        return; // 차단 항목이 있으면 PDF 생성 안 함
      }

      // 2) 통과했을 때만 PDF 미리보기를 만든다.
      try {
        const blob = await previewPdf({
          terms,
          entry_path: entryPath,
          include_verification: true,
        });
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          objectUrl = null;
          return;
        }
        setPdfUrl(objectUrl);
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "계약서 미리보기를 만들지 못했어요. 다시 시도해 주세요.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [entryPath, retry, terms, workerBirthDate]);

  const hasBlocking = (blockingIssues?.length ?? 0) > 0;

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
            조건을 불러오는 중
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

  // 경로에 따라 문서의 성격이 다르다.
  // ⚠️ 백엔드 DOCUMENT_TITLES 와 같은 값을 써야 한다. 화면 안내와 실제
  //    발송 메일 제목이 어긋나면 사용자가 무엇을 받았는지 알 수 없다.
  const title = documentTitle(entryPath);
  const authorLabel =
    entryPath === "EMPLOYER" ? "사업주(사장님)" : "근로자";

  return (
    <ScreenShell
      step={4}
      title={`${title} 미리보기 · 확인 전 초안`}
      description="확인한 조건을 그대로 계약서로 옮겼어요. 임금이나 다른 조건을 임의로 바꾸지 않습니다. 아직 체결 전 문서예요."
    >
      <DocumentStatusBadge status="DRAFTING" />

      <p className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
        이 미리보기에는 “확인 전 초안” 표시가 있어요. 미리보기나
        한쪽이 보냈다는 것만으로 양쪽이 합의했다고 표시하지 않아요.
        {/* 실제 서명용 문서에는 워터마크를 찍지 않는다. 체결된 계약서에
            '초안' 표기가 남으면 분쟁 시 빌미가 되고 제17조 교부 증거로도
            약해진다. 근거: backend analyze_and_sign 주석 */}
      </p>

      <Card>
        <h2 className="text-sm font-extrabold text-ink">문서 생성 기준</h2>
        <ul className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-ink-muted">
          <li>· 문서 종류: {title}</li>
          <li>· 작성 주체: {authorLabel}</li>
          <li>
            · 조건 출처:{" "}
            {entryPath === "PHOTO" ? "계약서 사진 추출 후 사람이 확인" : "직접 입력"}
          </li>
          <li>· 검증 메모: 확인 결과를 문서 아래쪽에 함께 넣어요</li>
          <li>· 서명 순서: {firstSignerLabel(entryPath)}부터</li>
        </ul>
      </Card>

      {hasBlocking && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-4 text-sm text-red-900"
        >
          <p className="font-bold">
            <span aria-hidden="true">🚫 </span>
            아직 요청서를 만들 수 없어요
          </p>
          <p className="mt-1 leading-relaxed">
            근로계약서에 꼭 필요한 항목이 비어 있거나 잘못된 값이 있어요.
            아래를 고치면 요청서 미리보기가 만들어져요.
          </p>
          <ul className="mt-3 flex flex-col gap-3">
            {blockingIssues?.map((issue) => (
              <li key={issue.field} className="flex flex-col gap-0.5">
                <span className="font-bold">
                  {issue.label} — {issue.reason}
                </span>
                <span className="text-red-800">→ {issue.fix}</span>
              </li>
            ))}
          </ul>
          <ButtonLink href="/review" variant="secondary" className="mt-4">
            조건 수정하러 가기
          </ButtonLink>
        </div>
      )}

      {loading && (
        <SkeletonCard
          label={blockingIssues === null ? "확인하는 중" : "계약서 만드는 중"}
          lines={4}
        />
      )}

      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">계약서 미리보기를 만들지 못했어요</p>
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
            {hasBlocking
              ? "필수 항목을 고치면 발송할 수 있어요"
              : "PDF 미리보기 후 발송 정보 입력으로"}
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
