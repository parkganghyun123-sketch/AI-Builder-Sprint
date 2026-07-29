"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { Button, ButtonLink, Card } from "@/components/ui";
import {
  analyzeAndSign,
  ViolationBlockedError,
} from "@/lib/api";
import { readSession, updateSession } from "@/lib/session";
import type {
  ContractTerms,
  EntryPath,
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

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setReport(session.report);
    setEntryPath(session.entryPath);
    setWorkerBirthDate(session.workerBirthDate);
    setForm({
      workerName: String(session.terms?.worker_name.value ?? ""),
      workerEmail: "",
      employerName: String(session.terms?.employer_name.value ?? ""),
      employerEmail: "",
    });
    setReady(true);
  }, []);

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

    const invalid = validateForm();
    if (invalid) {
      setFieldError(invalid);
      return;
    }

    setLoading(true);
    setError(null);
    setFieldError(null);

    try {
      const response = await analyzeAndSign({
        terms,
        worker_birth_date: workerBirthDate,
        worker_name: form.workerName.trim(),
        worker_email: form.workerEmail.trim(),
        employer_name: form.employerName.trim(),
        employer_email: form.employerEmail.trim(),
        entry_path: entryPath,
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

  return (
    <ScreenShell
      step={5}
      title="근로조건 확인 요청서 전자서명 발송"
      description="이 단계에서만 입력한 이메일로 모두싸인 서명 요청을 보냅니다. 발송 후에도 제공자 상태가 체결 완료로 확인되기 전까지는 완료로 표시하지 않습니다."
    >
      <DocumentStatusBadge status="DRAFTING" />

      <p className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950">
        발송되는 PDF는 “확인 전 초안” 워터마크가 있는 근로조건 확인
        요청서입니다. 한쪽이 폼을 제출하거나 발송을 눌렀다는 이유만으로
        “조건 확인됨” 또는 “체결 완료” 상태를 만들지 않습니다.
      </p>

      {reportProblems.length > 0 && !blockedProblems && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3.5 text-sm text-amber-900">
          <p className="font-bold">
            <span aria-hidden="true">⚠️ </span>
            결과에서 다시 확인할 항목이 {reportProblems.length}건 있습니다
          </p>
          <ul className="mt-2 list-inside list-disc">
            {reportProblems.map((problem, index) => (
              <li key={`${problem.code}-${index}`}>{problem.label}</li>
            ))}
          </ul>
          <p className="mt-2 leading-relaxed">
            백엔드는 첫 요청을 409로 차단할 수 있습니다. 차단된 뒤 내용을
            확인하고 명시적으로 체크한 경우에만 재요청할 수 있습니다.
          </p>
        </div>
      )}

      {blockedProblems && (
        <div
          role="alert"
          className="rounded-field border border-amber-400 bg-amber-50 px-4 py-4 text-sm text-amber-950"
        >
          <p className="font-extrabold">서명 요청이 일시 중단됐어요</p>
          <p className="mt-1 leading-relaxed">
            백엔드가 다음 항목을 다시 확인하도록 요청했습니다.
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
              loading || (blockedProblems !== null && !acknowledged)
            }
            aria-describedby={fieldError ? "sign-field-error" : undefined}
          >
            {loading
              ? "서명 요청을 보내고 있어요…"
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
