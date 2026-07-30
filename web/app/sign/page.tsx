"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import {
  analyzeAndSign,
  getValidationState,
  SignBlockedError,
  ViolationBlockedError,
} from "@/lib/api";
import { documentTitle, firstSignerLabel } from "@/lib/constants";
import { readSession, updateSession } from "@/lib/session";
import type {
  ContractTerms,
  EntryPath,
  ValidationIssue,
  ValidationReport,
} from "@/lib/types";

type PartyForm = {
  workerName: string;
  workerEmail: string;
  employerName: string;
  employerEmail: string;
};

const EMPTY_FORM: PartyForm = {
  workerName: "",
  workerEmail: "",
  employerName: "",
  employerEmail: "",
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignPage() {
  const router = useRouter();
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [workerBirthDate, setWorkerBirthDate] = useState<string | null>(null);
  const [form, setForm] = useState<PartyForm>(EMPTY_FORM);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [blockedProblems, setBlockedProblems] = useState<string[] | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  // 필수 항목 누락·값 오류. 하나라도 있으면 서명 요청(PDF 생성)을 막는다.
  const [blockingIssues, setBlockingIssues] = useState<ValidationIssue[]>([]);
  // 사용자가 review 화면에서 "값이 맞다"고 확인한 필드 키.
  const [confirmedFields, setConfirmedFields] = useState<string[]>([]);
  // 값 확인 누락·이름 불일치 등으로 막혔을 때(위반과 다른 409). 돌아가서 고쳐야 한다.
  const [signBlock, setSignBlock] = useState<SignBlockedError["detail"] | null>(
    null,
  );

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setReport(session.report);
    setEntryPath(session.entryPath);
    setWorkerBirthDate(session.workerBirthDate);
    setConfirmedFields(session.confirmedFields);
    setForm({
      workerName: String(session.terms?.worker_name.value ?? ""),
      workerEmail: "",
      employerName: String(session.terms?.employer_name.value ?? ""),
      employerEmail: "",
    });
    setReady(true);
  }, []);

  // 필수 항목·값 오류를 확인해 서명 요청 자체를 막을지 정한다.
  // (review에서 걸러지지만, PDF를 만드는 경로라 여기서도 다시 본다.)
  useEffect(() => {
    if (!terms) return;
    let cancelled = false;
    getValidationState({ terms, worker_birth_date: workerBirthDate })
      .then((state) => {
        if (!cancelled) {
          setBlockingIssues(state.issues.filter((issue) => issue.blocks));
        }
      })
      .catch(() => {
        // 판정을 못 받으면 서버 재검증(422)에 맡긴다.
        if (!cancelled) setBlockingIssues([]);
      });
    return () => {
      cancelled = true;
    };
  }, [terms, workerBirthDate]);

  function setValue(key: keyof PartyForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldError(null);
    setError(null);
  }

  function validateForm(): string | null {
    if (
      !form.workerName.trim() ||
      !form.employerName.trim() ||
      !form.workerEmail.trim() ||
      !form.employerEmail.trim()
    ) {
      return "이름과 이메일 네 항목을 모두 입력해 주세요.";
    }
    if (
      !EMAIL_PATTERN.test(form.workerEmail) ||
      !EMAIL_PATTERN.test(form.employerEmail)
    ) {
      return "이메일 형식을 확인해 주세요.";
    }
    if (blockedProblems && !acknowledged) {
      return "백엔드가 확인을 요청한 항목을 읽고 체크해 주세요.";
    }
    return null;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!terms || loading) return;
    // 필수 항목이 비었거나 값이 잘못됐으면 서명 요청을 보내지 않는다.
    if (blockingIssues.length > 0) return;

    const invalid = validateForm();
    if (invalid) {
      setFieldError(invalid);
      return;
    }

    setLoading(true);
    setError(null);
    setFieldError(null);
    setSignBlock(null);

    try {
      const response = await analyzeAndSign({
        terms,
        worker_birth_date: workerBirthDate,
        worker_name: form.workerName.trim(),
        worker_email: form.workerEmail.trim(),
        employer_name: form.employerName.trim(),
        employer_email: form.employerEmail.trim(),
        entry_path: entryPath,
        // review 화면에서 확인한 값 목록. 비면 백엔드가 409로 막는다.
        confirmed_fields: confirmedFields,
        proceed_with_violations:
          blockedProblems !== null && acknowledged,
      });
      setWorkerBirthDate(null);
      updateSession({
        workerBirthDate: null,
        report: response.report,
        sign: {
          documentId: response.document_id,
          status: response.status,
        },
      });
      router.push("/complete");
    } catch (caught) {
      if (caught instanceof ViolationBlockedError) {
        setBlockedProblems(caught.detail.problems);
        setAcknowledged(false);
      } else if (caught instanceof SignBlockedError) {
        // 값 확인 누락·이름 불일치 — 돌아가서 고쳐야 한다(진행 강행 불가).
        setSignBlock(caught.detail);
      } else {
        setError(
          caught instanceof Error
            ? caught.message
            : "서명 요청을 보내지 못했습니다.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  if (!ready) {
    return (
      <ScreenShell step={5} title="서명 단계 준비 중">
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            현재 세션의 조건을 불러오고 있어요.
          </p>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  if (!terms || !report) {
    return (
      <ScreenShell
        step={5}
        title="서명을 요청할 검증 결과가 없어요"
        description="계약 조건을 확인하고 백엔드 검증을 먼저 완료해 주세요."
      >
        <ButtonLink href="/review" className="w-full">
          조건 확인으로 돌아가기
        </ButtonLink>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  const reportProblems = report.checks.filter(
    (check) =>
      check.status === "VIOLATION" || check.status === "MISSING",
  );

  // 문서 종류와 서명 순서는 경로가 결정한다.
  // ⚠️ 백엔드 DOCUMENT_TITLES / employer_first 와 같은 기준을 쓴다.
  const title = documentTitle(entryPath);
  const firstSigner = firstSignerLabel(entryPath);

  return (
    <ScreenShell
      step={5}
      title={`${title} 전자서명 발송`}
      description="이 단계에서만 입력한 이메일로 모두싸인 서명 요청을 보냅니다. 발송 후에도 제공자 상태가 체결 완료로 확인되기 전까지는 완료로 표시하지 않습니다."
    >
      <DocumentStatusBadge status="DRAFTING" />

      <p className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
        <strong>{firstSigner}부터 서명</strong>하고, 그다음 상대방에게 서명
        요청이 갑니다. 서명할 문서에는 “확인 전 초안” 워터마크를 찍지 않습니다
        — 체결된 문서에 초안 표기가 남으면 나중에 “초안인 줄 알았다”는 주장의
        빌미가 되고, 근로기준법 제17조 교부 의무를 이행한 증거로도 약해집니다.
        조건의 출처는 문서 하단에 문장으로 밝힙니다.
      </p>
      <p className="rounded-field border border-brand-line bg-brand-tint/40 px-4 py-3 text-sm leading-relaxed text-ink-muted">
        한쪽이 폼을 제출하거나 발송을 눌렀다는 이유만으로 “조건 확인됨” 또는
        “체결 완료” 상태를 만들지 않습니다. 상태는 모두싸인에서 직접 읽어옵니다.
      </p>

      {signBlock && (
        <div
          role="alert"
          className="rounded-field border border-amber-400 bg-amber-50 px-4 py-4 text-sm text-amber-950"
        >
          <p className="font-extrabold">
            <span aria-hidden="true">↩️ </span>
            {signBlock.message}
          </p>
          {signBlock.fields && signBlock.fields.length > 0 && (
            <ul className="mt-2 list-inside list-disc">
              {signBlock.fields.map((field, index) => (
                <li key={`${field}-${index}`}>{field}</li>
              ))}
            </ul>
          )}
          {signBlock.hint && (
            <p className="mt-2 leading-relaxed">{signBlock.hint}</p>
          )}
          <ButtonLink href="/review" variant="secondary" className="mt-4">
            조건 확인으로 돌아가기
          </ButtonLink>
        </div>
      )}

      {blockingIssues.length > 0 && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-4 text-sm text-red-900"
        >
          <p className="font-bold">
            <span aria-hidden="true">🚫 </span>
            필수 항목이 비어 있거나 잘못됐어요
          </p>
          <p className="mt-1 leading-relaxed">
            근로계약서에 꼭 필요한 항목을 채우기 전에는 서명 요청을 보낼 수
            없어요.
          </p>
          <ul className="mt-3 flex flex-col gap-3">
            {blockingIssues.map((issue) => (
              <li key={issue.field} className="flex flex-col gap-0.5">
                <span className="font-bold">
                  {issue.label} — {issue.reason}
                </span>
                <span className="text-red-800">→ {issue.fix}</span>
              </li>
            ))}
          </ul>
          <ButtonLink href="/review" variant="secondary" className="mt-4">
            조건 확인으로 돌아가기
          </ButtonLink>
        </div>
      )}

      {reportProblems.length > 0 && !blockedProblems && blockingIssues.length === 0 && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3.5 text-sm text-amber-900">
          <p className="font-bold">
            <span aria-hidden="true">⚠️ </span>
            서명 전에 한 번 더 확인하면 좋은 항목이 {reportProblems.length}건
            있어요
          </p>
          <ul className="mt-2 flex flex-col gap-2">
            {reportProblems.map((problem, index) => (
              <li key={`${problem.code}-${index}`}>
                <span className="font-bold">{problem.label}</span>
                {(problem.detail || problem.calculation) && (
                  <span className="mt-0.5 block leading-relaxed text-amber-800">
                    {problem.detail || problem.calculation}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 leading-relaxed">
            이 항목이 있어도 서명 요청은 보낼 수 있어요. 사장님과 조건을
            조정해 보거나, 내용을 확인한 뒤 지금 조건 그대로 진행하셔도 됩니다.
            발송을 누르면 확인하셨는지 한 번만 더 여쭤볼게요.
          </p>
        </div>
      )}

      {blockedProblems && (
        <div
          role="alert"
          className="rounded-field border border-amber-400 bg-amber-50 px-4 py-4 text-sm text-amber-950"
        >
          <p className="font-extrabold">보내기 전에 이 항목을 확인해 주세요</p>
          <p className="mt-1 leading-relaxed">
            아래 내용을 한 번만 더 확인하시면, 지금 조건 그대로 서명 요청을
            보낼 수 있어요.
          </p>
          <ul className="mt-2 list-inside list-disc">
            {blockedProblems.map((problem, index) => (
              <li key={`${problem}-${index}`}>{problem}</li>
            ))}
          </ul>
          <label className="mt-4 flex min-h-12 cursor-pointer items-start gap-3 rounded-field border border-amber-400 bg-white p-3">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              className="mt-1 h-5 w-5"
            />
            <span>
              위 항목과 검증 결과의 한계를 확인했습니다. 이 체크는 권리를
              포기한다는 뜻이 아니며, 현재 입력한 조건으로 서명 요청을 다시
              보내는 데 동의합니다.
            </span>
          </label>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-5">
        <Card className="flex flex-col gap-5">
          <div>
            <h2 className="text-base font-extrabold text-ink">서명 당사자</h2>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">
              이름은 서명 당사자 표시에 사용합니다. 이메일은 지금 발송하는
              모두싸인 요청에만 사용하며, 검증 단계에서는 수집하지 않았습니다.
            </p>
          </div>

          <FormField
            id="worker-name"
            label="근로자 이름"
            value={form.workerName}
            onChange={(value) => setValue("workerName", value)}
            autoComplete="name"
          />
          <FormField
            id="worker-email"
            label="근로자 이메일"
            value={form.workerEmail}
            onChange={(value) => setValue("workerEmail", value)}
            type="email"
            autoComplete="email"
            placeholder="name@example.com"
          />
          <FormField
            id="employer-name"
            label="사업주 이름"
            value={form.employerName}
            onChange={(value) => setValue("employerName", value)}
            autoComplete="off"
          />
          <FormField
            id="employer-email"
            label="사업주 이메일"
            value={form.employerEmail}
            onChange={(value) => setValue("employerEmail", value)}
            type="email"
            autoComplete="off"
            placeholder="boss@example.com"
          />

          <p className="text-xs leading-relaxed text-ink-muted">
            이메일은 이 화면의 메모리에만 잠시 유지하며 sessionStorage에
            저장하지 않습니다. 로그나 오류 메시지에도 포함하지 않고, 발송 뒤
            다음 화면에는 다시 표시하지 않습니다.
          </p>
        </Card>

        {fieldError && (
          <p
            id="sign-field-error"
            role="alert"
            className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
          >
            {fieldError}
          </p>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
          >
            <p className="font-bold">서명 요청을 보내지 못했어요</p>
            <p className="mt-1">{error}</p>
            <p className="mt-1">입력값은 유지됩니다. 다시 시도해 주세요.</p>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <Button
            type="submit"
            className="w-full"
            disabled={
              loading ||
              blockingIssues.length > 0 ||
              (blockedProblems !== null && !acknowledged)
            }
            aria-describedby={fieldError ? "sign-field-error" : undefined}
          >
            {loading
              ? "서명 요청을 보내고 있어요…"
              : blockingIssues.length > 0
                ? "필수 항목을 먼저 채워 주세요"
                : blockedProblems
                  ? "확인한 조건으로 서명 요청 다시 보내기"
                  : "확인 전 요청서 발송"}
          </Button>
          <ButtonLink href="/result" variant="secondary" className="w-full">
            검증 결과 다시 확인
          </ButtonLink>
        </div>
      </form>

      <LegalDisclaimer />
    </ScreenShell>
  );
}

function FormField({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "email";
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-bold text-ink">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-14 w-full rounded-field border border-slate-400 bg-white px-4 py-3 text-ink outline-none transition placeholder:text-ink-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
      />
    </div>
  );
}
