"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import {
  FieldInput,
  type FieldOption,
} from "@/components/FieldInput";
import { Button, ButtonLink, Card } from "@/components/ui";
import { validateTerms } from "@/lib/api";
import {
  createEmptyTerms,
  readSession,
  startSession,
  updateSession,
} from "@/lib/session";
import type {
  ContractTerms,
  EntryPath,
  ExtractedField,
} from "@/lib/types";

type FieldConfig = {
  key: keyof ContractTerms;
  label: string;
  unit?: string;
  placeholder?: string;
  type?: "text" | "date" | "time" | "tel";
  inputMode?: "numeric" | "text" | "tel";
  options?: FieldOption[];
};

const WAGE_OPTIONS: FieldOption[] = [
  { value: "HOURLY", label: "시간급" },
  { value: "DAILY", label: "일급" },
  { value: "MONTHLY", label: "월급" },
];

const YES_NO_OPTIONS: FieldOption[] = [
  { value: "있음", label: "있음" },
  { value: "없음", label: "없음" },
];

const SECTIONS: { title: string; description?: string; fields: FieldConfig[] }[] =
  [
    {
      title: "계약기간",
      fields: [
        {
          key: "contract_start",
          label: "계약 시작일",
          placeholder: "계약서에 적힌 날짜를 그대로 입력",
        },
        {
          key: "contract_end",
          label: "계약 종료일",
          placeholder: "계약서에 적힌 날짜를 그대로 입력",
        },
      ],
    },
    {
      title: "근무 조건",
      fields: [
        { key: "workplace", label: "근무장소" },
        { key: "job_description", label: "업무 내용" },
      ],
    },
    {
      title: "소정근로시간",
      description:
        "시각과 근무일수를 바탕으로 백엔드 검증 코드가 근로시간을 계산합니다.",
      fields: [
        {
          key: "work_start_time",
          label: "시업 시각",
          type: "time",
          placeholder: "HH:MM",
        },
        {
          key: "work_end_time",
          label: "종업 시각",
          type: "time",
          placeholder: "HH:MM",
        },
        {
          key: "break_start_time",
          label: "휴게 시작 시각",
          type: "time",
          placeholder: "HH:MM",
        },
        {
          key: "break_end_time",
          label: "휴게 종료 시각",
          type: "time",
          placeholder: "HH:MM",
        },
        {
          key: "work_days_per_week",
          label: "주 근무일수",
          unit: "일",
          inputMode: "numeric",
          placeholder: "숫자만 입력",
        },
        { key: "weekly_holiday_day", label: "주휴일" },
      ],
    },
    {
      title: "임금",
      fields: [
        {
          key: "wage_type",
          label: "급여 형태",
          options: WAGE_OPTIONS,
        },
        {
          key: "wage_amount",
          label: "임금 금액",
          unit: "원",
          inputMode: "numeric",
          placeholder: "숫자만 입력",
        },
        {
          key: "has_bonus",
          label: "상여금",
          options: YES_NO_OPTIONS,
        },
        {
          key: "other_allowance",
          label: "기타급여(제수당)",
          unit: "원 또는 계약서 표기",
        },
        { key: "payday", label: "임금지급일" },
        { key: "payment_method", label: "지급방법" },
      ],
    },
    {
      title: "사업주 정보",
      fields: [
        { key: "employer_business_name", label: "사업체명" },
        { key: "employer_name", label: "대표자 이름" },
      ],
    },
    {
      title: "근로자 정보",
      fields: [{ key: "worker_name", label: "근로자 이름" }],
    },
  ];

function ReviewContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wantsManual = searchParams.get("path") === "B";
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [userEditedFields, setUserEditedFields] = useState<
    (keyof ContractTerms)[]
  >([]);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const existing = readSession();

    if (wantsManual) {
      if (existing.entryPath === "MANUAL" && existing.terms) {
        setTerms(existing.terms);
        setUserEditedFields(existing.userEditedFields);
      } else {
        const emptyTerms = createEmptyTerms();
        const created = startSession(emptyTerms, "MANUAL");
        setTerms(created.terms);
        setUserEditedFields(created.userEditedFields);
      }
      setEntryPath("MANUAL");
    } else {
      setTerms(existing.terms);
      setEntryPath(existing.entryPath);
      setUserEditedFields(existing.userEditedFields);
    }
    setReady(true);
  }, [wantsManual]);

  function changeField(key: keyof ContractTerms, value: string) {
    if (!terms) return;
    const current = terms[key];
    const nextField: ExtractedField = {
      ...current,
      value: value.trim() === "" ? null : value,
      confidence: value.trim() === "" ? "NOT_FOUND" : "HIGH",
      // 사용자가 값을 손댄 순간 기존 계약서 원문과의 연결은 더 이상 유효하지 않다.
      source_text: null,
    };
    const next = { ...terms, [key]: nextField };
    const nextEditedFields = userEditedFields.includes(key)
      ? userEditedFields
      : [...userEditedFields, key];
    setTerms(next);
    setUserEditedFields(nextEditedFields);
    updateSession({
      terms: next,
      userEditedFields: nextEditedFields,
      report: null,
      sign: null,
    });
    setError(null);
  }

  async function submit() {
    if (!terms || loading) return;
    setLoading(true);
    setError(null);
    try {
      const report = await validateTerms({ terms });
      updateSession({ terms, entryPath, report, sign: null });
      router.push("/result");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "검증 요청을 완료하지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (!ready) {
    return (
      <ScreenShell
        step={2}
        title="조건 불러오는 중"
        description="현재 브라우저 탭의 계약 조건을 확인하고 있어요."
      >
        <Card>
          <p aria-live="polite" className="text-sm text-ink-muted">
            잠시만 기다려 주세요.
          </p>
        </Card>
      </ScreenShell>
    );
  }

  if (!terms) {
    return (
      <ScreenShell
        step={2}
        title="확인할 계약 조건이 없어요"
        description="이 브라우저 탭에서 파일을 다시 올리거나 직접 입력해 주세요."
      >
        <Card className="flex flex-col gap-3">
          <ButtonLink href="/upload" className="w-full">
            계약서 파일 올리기
          </ButtonLink>
          <ButtonLink href="/review?path=B" variant="secondary" className="w-full">
            조건 직접 입력
          </ButtonLink>
        </Card>
      </ScreenShell>
    );
  }

  const lowCount = Object.values(terms).filter(
    (field) => field.confidence === "LOW",
  ).length;
  const isManual = entryPath === "MANUAL";

  return (
    <ScreenShell
      step={2}
      title={isManual ? "조건 직접 입력" : "읽어낸 조건 확인하기"}
      description={
        isManual
          ? "말로 들은 내용만 입력해 주세요. 모르는 항목은 비워 두면 정보 부족 또는 찾지 못함으로 확인합니다."
          : "AI가 읽은 값과 원문 근거를 비교해 주세요. 여기서 확인한 조건만 백엔드 검증에 사용합니다."
      }
    >
      {isManual && <DocumentStatusBadge status="DRAFTING" />}

      {!isManual && lowCount > 0 && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span aria-hidden="true">⚠️ </span>
          확인이 필요한 추출 항목이 {lowCount}개 있습니다. 원문 근거와 함께
          확인해 주세요.
        </div>
      )}

      <p className="rounded-field border border-brand-line bg-brand-tint/60 px-4 py-3 text-sm leading-relaxed text-ink-muted">
        검증에 필요하지 않은 사업주 전화·주소와 근로자 주소·연락처는 이
        화면에서 수집하거나 탭 세션에 저장하지 않습니다. 이름과 확인한 계약
        조건은 현재 브라우저 탭을 닫을 때까지 세션에 남을 수 있습니다.
      </p>

      {SECTIONS.map((section) => (
        <Card key={section.title} className="flex flex-col gap-5">
          <div>
            <h2 className="text-base font-extrabold text-ink">
              {section.title}
            </h2>
            {section.description && (
              <p className="mt-1 text-sm leading-relaxed text-ink-muted">
                {section.description}
              </p>
            )}
          </div>
          {section.fields.map(({ key, ...fieldProps }) => {
            const field = terms[key];
            const userEdited = userEditedFields.includes(key);
            const hasValue = field.value !== null && String(field.value) !== "";

            return (
              <div key={key} className="flex flex-col gap-1">
                <FieldInput
                  {...fieldProps}
                  field={field}
                  onChange={(value) => changeField(key, value)}
                />
                {userEdited ? (
                  <p className="text-xs font-semibold text-brand-deep">
                    <span aria-hidden="true">✍️ </span>
                    사용자 입력·수정값입니다. 계약서 원문 근거로 표시하지
                    않습니다.
                  </p>
                ) : field.source_text ? (
                  <p className="text-xs font-semibold text-ink-muted">
                    <span aria-hidden="true">📄 </span>
                    계약서에서 읽은 값입니다.
                  </p>
                ) : !isManual && hasValue ? (
                  <p className="text-xs font-semibold text-amber-900">
                    <span aria-hidden="true">📄 </span>
                    계약서에서 읽은 값이지만 연결된 원문 근거를 찾지
                    못했습니다. 원본을 직접 확인해 주세요.
                  </p>
                ) : null}
              </div>
            );
          })}
        </Card>
      ))}

      {error && (
        <div
          role="alert"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">검증 요청을 완료하지 못했어요</p>
          <p className="mt-1">{error}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={submit}
            disabled={loading}
          >
            다시 시도
          </Button>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Button onClick={submit} disabled={loading} className="w-full">
          {loading ? "검증 코드가 확인 중이에요…" : "조건 확인하고 검증하기 →"}
        </Button>
        <ButtonLink
          href={isManual ? "/" : "/upload"}
          variant="ghost"
          className="w-full"
        >
          ← 뒤로
        </ButtonLink>
      </div>
    </ScreenShell>
  );
}

export default function ReviewPage() {
  return (
    <Suspense>
      <ReviewContent />
    </Suspense>
  );
}
