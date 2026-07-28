import { ScreenShell } from "@/components/ScreenShell";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { CheckResultCard, CHECK_SOURCE_FIELD } from "@/components/CheckResultCard";
import { ButtonLink, Card } from "@/components/ui";
import { MOCK_REPORT, MOCK_TERMS } from "@/lib/mock";
import { MINIMUM_WAGE_2026, REFERENCE_YEAR } from "@/lib/constants";

/**
 * ③ 결과 — 백엔드 ValidationReport 표시 (기획서 단계 5).
 *
 * ⚠️ 숫자·판정·근거는 전부 POST /contracts/validate 반환값이다.
 *    프론트에서 계산하지 않는다. 현재는 lib/mock.ts.
 * TODO(D): validateTerms() 호출로 교체
 */
export default function ResultPage() {
  const report = MOCK_REPORT;
  const terms = MOCK_TERMS;

  const problems = report.checks.filter(
    (c) => c.status === "VIOLATION" || c.status === "MISSING",
  ).length;

  return (
    <ScreenShell
      step={3}
      title="검증 결과"
      description={`확정한 조건을 ${REFERENCE_YEAR}년 법정 기준과 대조했어요.`}
    >
      <Card className="text-center">
        <div className="text-3xl">{problems > 0 ? "⚠️" : "✅"}</div>
        <p className="mt-3 text-xl font-extrabold tracking-tighter text-ink">
          {problems > 0
            ? `확인이 필요한 항목이 ${problems}건 있어요`
            : "법정 기준을 모두 충족해요"}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          항목마다 계약서 근거와 법령·계산식을 함께 확인할 수 있어요.
        </p>
      </Card>

      {/* 계약 사실 vs 법정 기준 — 시각적으로 분리 (CLAUDE.md 규칙 2) */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <div className="text-xs font-bold text-ink-soft">📄 내 계약서 내용</div>
          <div className="mt-2 text-2xl font-extrabold text-ink">
            시급 {Number(terms.wage_amount.value).toLocaleString()}원
          </div>
          <div className="mt-1 text-sm text-ink-muted">
            {terms.work_start_time.value}~{terms.work_end_time.value} · 주{" "}
            {terms.work_days_per_week.value}일
          </div>
        </Card>

        <Card className="border-brand/30 bg-brand-tint/60">
          <div className="text-xs font-bold text-brand-deep">⚖️ 법정 기준</div>
          <div className="mt-2 text-2xl font-extrabold text-brand-deep">
            시급 {MINIMUM_WAGE_2026.toLocaleString()}원
          </div>
          <div className="mt-1 text-sm text-brand-deep/80">
            {REFERENCE_YEAR}년 적용 최저임금
          </div>
        </Card>
      </div>

      {/* 예상 월급·차액 — 백엔드 계산값 */}
      <Card className="flex items-center justify-between gap-4">
        <div>
          <div className="text-xs font-bold text-ink-soft">
            예상 월급 (검증 엔진 계산값)
          </div>
          <div className="mt-1 text-2xl font-extrabold text-ink">
            {report.estimated_monthly_pay?.toLocaleString() ?? "—"}원
          </div>
          {report.wage_shortfall !== null && (
            <div className="mt-1 text-xs font-bold text-amber-600">
              최저임금 기준 월 {report.wage_shortfall.toLocaleString()}원 차이
            </div>
          )}
        </div>
        <span className="text-3xl">💰</span>
      </Card>

      <div className="flex flex-col gap-3">
        {report.checks.map((check) => {
          const fieldKey = CHECK_SOURCE_FIELD[check.code];
          return (
            <CheckResultCard
              key={check.code}
              check={check}
              sourceText={fieldKey ? terms[fieldKey].source_text : null}
            />
          );
        })}
      </div>

      <div className="flex flex-col gap-2">
        <ButtonLink href="/contract" className="w-full">
          제대로 된 계약서 만들기 →
        </ButtonLink>
        <ButtonLink href="/review" variant="secondary" className="w-full">
          조건 다시 수정
        </ButtonLink>
      </div>

      <LegalDisclaimer />
    </ScreenShell>
  );
}
