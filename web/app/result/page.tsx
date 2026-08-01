"use client";

import { useEffect, useState } from "react";
import { ScreenShell } from "@/components/ScreenShell";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { ContractChat } from "@/components/ContractChat";
import {
  CheckResultCard,
  CHECK_SOURCE_FIELD,
} from "@/components/CheckResultCard";
import { ButtonLink, Card } from "@/components/ui";
import { readSession } from "@/lib/session";
import type { ContractTerms, ValidationReport } from "@/lib/types";

function displayValue(
  terms: ContractTerms,
  key: keyof ContractTerms,
): string | null {
  const value = terms[key].value;
  return value === null || String(value).trim() === "" ? null : String(value);
}

export default function ResultPage() {
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [userEditedFields, setUserEditedFields] = useState<
    (keyof ContractTerms)[]
  >([]);
  const [workerBirthDate, setWorkerBirthDate] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setReport(session.report);
    setUserEditedFields(session.userEditedFields);
    setWorkerBirthDate(session.workerBirthDate);
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <ScreenShell
        step={3}
        title="검증 결과 불러오는 중"
        description="백엔드가 반환한 결과를 확인하고 있어요."
      >
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            잠시만 기다려 주세요.
          </p>
        </Card>
      </ScreenShell>
    );
  }

  if (!terms || !report) {
    return (
      <ScreenShell
        step={3}
        title="표시할 검증 결과가 없어요"
        description="현재 브라우저 탭에서 계약 조건을 다시 확인하고 검증해 주세요."
      >
        <Card className="flex flex-col gap-3">
          <ButtonLink href="/review" className="w-full">
            조건 확인으로 돌아가기
          </ButtonLink>
          <ButtonLink href="/" variant="secondary" className="w-full">
            처음부터 시작
          </ButtonLink>
        </Card>
        <LegalDisclaimer />
      </ScreenShell>
    );
  }

  const problems = report.checks.filter(
    (check) =>
      check.status === "VIOLATION" || check.status === "MISSING",
  ).length;
  const unknowns = report.checks.filter(
    (check) => check.status === "UNKNOWN",
  ).length;
  const wage = displayValue(terms, "wage_amount");
  const start = displayValue(terms, "work_start_time");
  const end = displayValue(terms, "work_end_time");
  const days = displayValue(terms, "work_days_per_week");

  return (
    <ScreenShell
      step={3}
      title="검증 결과"
      description="사용자가 확인한 계약 조건을 백엔드 검증 코드가 지원하는 기준과 비교한 결과입니다."
    >
      <Card className="text-center">
        <div aria-hidden="true" className="text-3xl">
          {problems > 0 ? "⚠️" : unknowns > 0 ? "🔍" : "✅"}
        </div>
        <p className="mt-3 text-xl font-extrabold tracking-tighter text-ink">
          {problems > 0
            ? `다시 확인할 항목이 ${problems}건 있습니다`
            : unknowns > 0
              ? `정보 부족으로 확인하지 못한 항목이 ${unknowns}건 있습니다`
              : "FairSign이 지원하는 항목에서 기준 미달·누락을 찾지 못했습니다"}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          상태는 법률 결론이 아니며, 각 항목의 적용 기준일·근거·계산식과
          한계를 함께 확인해 주세요.
        </p>
      </Card>

      <Card>
        <h2 className="text-sm font-extrabold text-ink">
          <span aria-hidden="true">📄 </span>
          사용자가 확인한 계약 조건
        </h2>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-field bg-brand-tint/60 p-4">
            <dt className="font-bold text-ink-muted">임금 금액</dt>
            <dd className="mt-1 font-extrabold text-ink">
              {wage ? `${wage}원` : "입력되지 않음"}
            </dd>
          </div>
          <div className="rounded-field bg-brand-tint/60 p-4">
            <dt className="font-bold text-ink-muted">소정근로 시각</dt>
            <dd className="mt-1 font-extrabold text-ink">
              {start && end ? `${start} ~ ${end}` : "입력되지 않음"}
            </dd>
          </div>
          <div className="rounded-field bg-brand-tint/60 p-4">
            <dt className="font-bold text-ink-muted">주 근무일수</dt>
            <dd className="mt-1 font-extrabold text-ink">
              {days ? `주 ${days}일` : "입력되지 않음"}
            </dd>
          </div>
          <div className="rounded-field bg-brand-tint/60 p-4">
            <dt className="font-bold text-ink-muted">검증 주체</dt>
            <dd className="mt-1 font-extrabold text-ink">
              백엔드 결정론적 규칙
            </dd>
          </div>
        </dl>
      </Card>

      {(report.estimated_monthly_pay !== null ||
        report.wage_shortfall !== null) && (
        <Card>
          <h2 className="text-sm font-extrabold text-ink">
            백엔드 계산 결과
          </h2>
          <dl className="mt-3 flex flex-col gap-2">
            {report.estimated_monthly_pay !== null && (
              <div className="flex items-center justify-between gap-3">
                <dt className="text-sm text-ink-muted">예상 월급</dt>
                <dd className="font-extrabold text-ink">
                  {report.estimated_monthly_pay.toLocaleString()}원
                </dd>
              </div>
            )}
            {report.wage_shortfall !== null && (
              <div className="flex items-center justify-between gap-3">
                <dt className="text-sm text-ink-muted">기준과의 월 차이</dt>
                <dd className="font-extrabold text-red-900">
                  {report.wage_shortfall.toLocaleString()}원
                </dd>
              </div>
            )}
          </dl>
        </Card>
      )}

      <div className="flex flex-col gap-3">
        {report.checks.map((check, index) => {
          const fieldKey = CHECK_SOURCE_FIELD[check.code];
          const field = fieldKey ? terms[fieldKey] : null;
          const userEdited = fieldKey
            ? userEditedFields.includes(fieldKey)
            : false;
          const sourceValue =
            field?.value === null || field?.value === undefined
              ? null
              : String(field.value);
          return (
            <CheckResultCard
              key={`${check.code}-${index}`}
              check={check}
              sourceText={field?.source_text ?? null}
              sourceOrigin={
                userEdited
                  ? "USER"
                  : field && (field.source_text || sourceValue)
                    ? "CONTRACT"
                    : undefined
              }
              sourceValue={sourceValue}
            />
          );
        })}
      </div>

      <ContractChat
        terms={terms}
        workerBirthDate={workerBirthDate}
      />

      <div className="flex flex-col gap-2">
        <ButtonLink href="/contract" className="w-full text-center">
          확인한 조건으로 근로조건 확인 요청서 만들기 →
        </ButtonLink>
        <ButtonLink href="/review" variant="secondary" className="w-full">
          조건 다시 수정
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
