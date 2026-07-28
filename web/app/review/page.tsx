import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { FieldInput } from "@/components/FieldInput";
import { ButtonLink, Card } from "@/components/ui";
import { MOCK_TERMS } from "@/lib/mock";
import type { ContractTerms } from "@/lib/types";

/**
 * ② 확인·수정 — 사람이 최종 확정하는 단계 (기획서 단계 4 ⭐).
 * 경로 A: 추출된 조건을 보여주고 사용자가 고침. confidence=LOW는 노란색 강조.
 * 경로 B(?path=B): 직접 입력. AI 미사용.
 *
 * ⚠️ 현재 값은 lib/mock.ts. Day 3에 POST /contracts/validate 연결로 교체.
 * TODO(D): 입력 상태 관리(useState) + 확정 시 validateTerms() 호출
 */
const SECTIONS: {
  title: string;
  fields: { key: keyof ContractTerms; label: string; unit?: string; placeholder?: string }[];
}[] = [
  {
    title: "근로시간",
    fields: [
      { key: "work_start_time", label: "시업 시각", placeholder: "09:00" },
      { key: "work_end_time", label: "종업 시각", placeholder: "16:00" },
      { key: "break_start_time", label: "휴게 시작", placeholder: "12:00" },
      { key: "break_end_time", label: "휴게 종료", placeholder: "12:30" },
      { key: "work_days_per_week", label: "주 근무일수", unit: "일", placeholder: "3" },
      { key: "weekly_holiday_day", label: "주휴일", placeholder: "일요일" },
    ],
  },
  {
    title: "임금",
    fields: [
      { key: "wage_type", label: "급여 형태", placeholder: "HOURLY" },
      { key: "wage_amount", label: "금액", unit: "원", placeholder: "10320" },
      { key: "payday", label: "임금지급일", placeholder: "매월 10일" },
    ],
  },
  {
    title: "계약 기본",
    fields: [
      { key: "contract_start", label: "계약 시작일", placeholder: "2026-08-01" },
      { key: "contract_end", label: "계약 종료일", placeholder: "2027-01-31" },
      { key: "workplace", label: "근무장소" },
      { key: "job_description", label: "업무 내용" },
    ],
  },
  {
    title: "당사자",
    fields: [
      { key: "worker_name", label: "근로자 이름" },
      { key: "employer_business_name", label: "사업체명" },
      { key: "employer_name", label: "대표자" },
    ],
  },
];

export default function ReviewPage({
  searchParams,
}: {
  searchParams: { path?: string };
}) {
  const isPathB = searchParams.path === "B";
  const terms = MOCK_TERMS;

  const lowCount = Object.values(terms).filter(
    (f) => f.confidence === "LOW",
  ).length;

  return (
    <ScreenShell
      step={2}
      title={isPathB ? "조건 직접 입력" : "읽어낸 조건 확인하기"}
      description={
        isPathB
          ? "사장님이 말한 조건을 입력해주세요. 이 내용은 아직 상대방에게 전달되지 않습니다."
          : "잘못 읽힌 항목이 있으면 직접 고쳐주세요. 여기서 확정한 내용으로 검증합니다."
      }
    >
      {isPathB && <DocumentStatusBadge status="DRAFTING" />}

      {!isPathB && lowCount > 0 && (
        <div className="rounded-field border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          ⚠️ 잘못 읽었을 수 있는 항목이 {lowCount}개 있어요. 노란색 칸을 확인해주세요.
        </div>
      )}

      {SECTIONS.map((section) => (
        <Card key={section.title} className="flex flex-col gap-4">
          <h2 className="text-sm font-extrabold text-ink">{section.title}</h2>
          {section.fields.map(({ key, label, unit, placeholder }) => (
            <FieldInput
              key={String(key)}
              label={label}
              unit={unit}
              placeholder={placeholder}
              field={terms[key]}
            />
          ))}
        </Card>
      ))}

      <p className="text-center text-sm text-ink-muted">
        1일 근로시간·주 소정근로시간은 시각에서 자동 계산돼요.
      </p>

      <div className="flex flex-col gap-2">
        <ButtonLink href="/result" className="w-full">
          조건 확정하고 검증하기 →
        </ButtonLink>
        <ButtonLink href="/upload" variant="ghost" className="w-full">
          ← 뒤로
        </ButtonLink>
      </div>
    </ScreenShell>
  );
}
