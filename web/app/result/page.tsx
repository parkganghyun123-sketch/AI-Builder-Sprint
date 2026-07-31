"use client";

import { useEffect, useState } from "react";
import { ScreenShell } from "@/components/ScreenShell";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import {
  CheckResultCard,
  CHECK_SOURCE_FIELD,
} from "@/components/CheckResultCard";
import { EntitlementsCard } from "@/components/EntitlementsCard";
import { OwnerMessageCard } from "@/components/OwnerMessageCard";
import { ButtonLink, Card, SkeletonCard } from "@/components/ui";
import { ContractAssistant } from "@/components/ContractAssistant";
import { readSession } from "@/lib/session";
import type { ContractTerms, EntryPath, ValidationReport } from "@/lib/types";

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
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [workerBirthDate, setWorkerBirthDate] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = readSession();
    setTerms(session.terms);
    setReport(session.report);
    setUserEditedFields(session.userEditedFields);
    setEntryPath(session.entryPath);
    setWorkerBirthDate(session.workerBirthDate);
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <ScreenShell
        step={3}
        title="검증 결과 불러오는 중"
        description="검토 결과를 불러오는 중이에요."
      >
        <SkeletonCard label="검증 결과를 불러오는 중" lines={4} />
        <SkeletonCard lines={3} />
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
  // 경로별로 다음 행동이 다르다.
  //   PHOTO     계약서를 받았다 → 사장님께 말을 꺼내는 것이 먼저
  //   MANUAL    계약서를 못 받았다 → 확인 요청서 발송이 주 산출물
  //   EMPLOYER  사업주가 작성 중 → 계약서 발송이 주 산출물
  const isManual = entryPath === "MANUAL";
  const isEmployer = entryPath === "EMPLOYER";
  const wage = displayValue(terms, "wage_amount");
  const start = displayValue(terms, "work_start_time");
  const end = displayValue(terms, "work_end_time");
  const days = displayValue(terms, "work_days_per_week");

  return (
    <ScreenShell
      step={3}
      title="검증 결과"
      description="직접 확인한 조건을 FairSign이 다루는 법정 기준과 비교한 결과예요."
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
              정해진 규칙으로 계산
            </dd>
          </div>
        </dl>
      </Card>

      {(report.estimated_monthly_pay !== null ||
        report.wage_shortfall !== null) && (
        <Card>
          <h2 className="text-sm font-extrabold text-ink">
            계산 결과
          </h2>
          <dl className="mt-3 flex flex-col gap-2">
            {report.estimated_monthly_pay !== null && (
              <div className="flex items-center justify-between gap-3">
                <dt className="text-sm text-ink-muted">예상 월급</dt>
                <dd className="tnum font-extrabold text-ink">
                  {report.estimated_monthly_pay.toLocaleString()}원
                </dd>
              </div>
            )}
            {report.wage_shortfall !== null && (
              <div className="flex items-center justify-between gap-3">
                <dt className="text-sm text-ink-muted">기준과의 월 차이</dt>
                <dd className="tnum font-extrabold text-red-900">
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

      {/* ② 말하게 한다 — 판정과 서명 사이에 있는 단계.
          ⚠️ 사업주에게는 보여주지 않는다. 이 문구는 "사장님, 안녕하세요…"로
             시작하는 근로자 시점의 문장이다. 작성자 본인에게 보여주면
             말이 되지 않는다.
          문제가 없으면 카드가 스스로 아무것도 렌더하지 않는다. */}
      {!isEmployer && (
        <OwnerMessageCard terms={terms} workerBirthDate={workerBirthDate} />
      )}

      {/* "몰라서 못 받는 것들" — 판정과 별개의 안내.
          ⚠️ 사업주에게는 보여주지 않는다. 근로자 권리 안내이고,
             사업주 화면에 띄우면 "이거 안 지켰죠?"로 읽힌다.
             사업주용 안내는 별도로 설계해야 한다(현재 범위 밖). */}
      {!isEmployer && <EntitlementsCard />}

      {/* 다음 행동은 경로별로 다르다.
          ⚠️ 이전에는 곧바로 "요청서 만들기" 하나뿐이었다. 그래서 계약서를
             이미 받은 근로자도 "새 문서를 만들어 사장님에게 보내는" 길로
             떠밀렸다. 열여섯 살이 사장님에게 서명을 요구하는 건 힘의
             관계상 현실적이지 않다. */}
      <Card className="flex flex-col gap-4">
        <h2 className="text-sm font-extrabold text-ink">
          <span aria-hidden="true">🧭 </span>
          다음엔 무엇을 할까요
        </h2>

        {isEmployer ? (
          <div className="flex flex-col gap-2">
            <ButtonLink href="/contract" className="w-full text-center">
              계약서 만들어 근로자에게 보내기 →
            </ButtonLink>
            <p className="text-xs leading-relaxed text-ink-muted">
              사장님이 먼저 서명하시면 근로자에게 서명 요청이 갑니다. 체결되면
              양측이 같은 계약서를 갖게 되어 교부 의무(근로기준법 제17조)를
              이행한 증거가 됩니다.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-ink-muted">
                {isManual
                  ? "계약서를 아직 받지 못했다면"
                  : "계약서를 이미 받았다면"}
              </p>
              {isManual ? (
                <>
                  <ButtonLink href="/contract" className="w-full text-center">
                    근로조건 확인 요청서 만들어 보내기 →
                  </ButtonLink>
                  <p className="text-xs leading-relaxed text-ink-muted">
                    근로계약서 교부는 사업주의 의무입니다(근로기준법 제17조).
                    들은 조건을 문서로 남겨 확인을 요청할 수 있어요.
                  </p>
                </>
              ) : (
                <p className="text-xs leading-relaxed text-ink-muted">
                  위 문구를 복사해 사장님께 먼저 여쭤보세요. 조건을 고쳐 새
                  계약서를 받는 것이 가장 깔끔한 결과입니다.
                </p>
              )}
            </div>

            {!isManual && (
              <div className="flex flex-col gap-2 border-t border-brand-line pt-4">
                <p className="text-xs font-bold text-ink-muted">
                  계약서를 못 받았거나, 말해도 고쳐주지 않는다면
                </p>
                <ButtonLink
                  href="/contract"
                  variant="secondary"
                  className="w-full text-center"
                >
                  근로조건 확인 요청서 만들어 보내기 →
                </ButtonLink>
              </div>
            )}
          </>
        )}

        <ButtonLink href="/review" variant="ghost" className="w-full">
          조건 다시 수정
        </ButtonLink>
      </Card>

      <ContractAssistant terms={terms} />

      <LegalDisclaimer />
    </ScreenShell>
  );
}
