"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import {
  FieldInput,
  type FieldOption,
} from "@/components/FieldInput";
import { Button, ButtonLink, Card } from "@/components/ui";
import {
  getReviewItems,
  getValidationState,
  validateTerms,
} from "@/lib/api";
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
  ReviewItem,
  ValidationState,
} from "@/lib/types";

/** 오류 목록에서 클릭한 항목의 입력란으로 스크롤 + 포커스. */
function focusField(field: string) {
  const el = document.querySelector<HTMLElement>(`[data-field="${field}"]`);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
  el?.focus();
}

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
          placeholder: "예: 2026-03-01 (일하기로 한 첫날)",
        },
        {
          key: "contract_end",
          label: "계약 종료일",
          placeholder: "예: 2026-08-31 · 기간을 안 정했으면 비워 두세요",
        },
      ],
    },
    {
      title: "근무 조건",
      fields: [
        {
          key: "workplace",
          label: "근무장소",
          placeholder: "예: 서울시 강남구 ○○카페 신사점",
        },
        {
          key: "job_description",
          label: "업무 내용",
          placeholder: "예: 홀 서빙, 음료 제조, 매장 정리",
        },
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
          placeholder: "예: 5 (주 5일 근무면 5)",
        },
        {
          key: "weekly_holiday_day",
          label: "주휴일",
          placeholder: "예: 일요일",
        },
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
          placeholder: "예: 시급이면 10320, 월급이면 2100000",
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
          placeholder: "예: 주휴수당 포함 · 없으면 비워 두세요",
        },
        {
          key: "payday",
          label: "임금지급일",
          placeholder: "예: 매월 25일",
        },
        {
          key: "payment_method",
          label: "지급방법",
          placeholder: "예: 근로자 명의 통장으로 입금",
        },
      ],
    },
    {
      title: "사업주 정보",
      fields: [
        {
          key: "employer_business_name",
          label: "사업체명",
          placeholder: "예: ○○커피 강남점",
        },
        {
          key: "employer_name",
          label: "대표자 이름",
          placeholder: "예: 홍길동",
        },
      ],
    },
    {
      title: "근로자 정보",
      fields: [
        {
          key: "worker_name",
          label: "근로자 이름",
          placeholder: "예: 김근로",
        },
      ],
    },
  ];

function ReviewContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wantsManual = searchParams.get("path") === "B";
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [workerBirthDate, setWorkerBirthDate] = useState("");
  const [userEditedFields, setUserEditedFields] = useState<
    (keyof ContractTerms)[]
  >([]);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 진행 차단 판정. null = 아직 확인 전(첫 검증 도착 전에는 막지 않는다).
  const [validation, setValidation] = useState<ValidationState | null>(null);
  // 확인이 필요한 항목(review-items). 화면은 confidence 를 직접 해석하지 않는다.
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  // 서명 전 반드시 확인해야 하는 필드 키(priority=high).
  const [mustConfirm, setMustConfirm] = useState<string[]>([]);
  // 사용자가 "값이 맞다"고 확인한 필드 키.
  const [confirmedFields, setConfirmedFields] = useState<string[]>([]);
  // 마지막으로 보낸 요청만 반영한다. 값이 빠르게 바뀌면 응답 순서가 뒤집힐 수 있다.
  const revalidateSeq = useRef(0);

  useEffect(() => {
    const existing = readSession();

    if (wantsManual) {
      if (existing.entryPath === "MANUAL" && existing.terms) {
        setTerms(existing.terms);
        setWorkerBirthDate(existing.workerBirthDate ?? "");
        setUserEditedFields(existing.userEditedFields);
        setConfirmedFields(existing.confirmedFields);
      } else {
        const emptyTerms = createEmptyTerms();
        const created = startSession(emptyTerms, "MANUAL");
        setTerms(created.terms);
        setWorkerBirthDate(created.workerBirthDate ?? "");
        setUserEditedFields(created.userEditedFields);
        setConfirmedFields(created.confirmedFields);
      }
      setEntryPath("MANUAL");
    } else {
      setTerms(existing.terms);
      setEntryPath(existing.entryPath);
      setWorkerBirthDate(existing.workerBirthDate ?? "");
      setUserEditedFields(existing.userEditedFields);
      setConfirmedFields(existing.confirmedFields);
    }
    setReady(true);
  }, [wantsManual]);

  // 값이 바뀔 때마다 백엔드에 다시 물어 진행 차단 여부를 갱신한다.
  // onChange마다 부르면 요청이 쏟아지므로 입력이 멈춘 뒤 400ms 두고 부른다.
  // 판정 규칙은 백엔드 소유다 — 여기서 재현하지 않는다.
  useEffect(() => {
    if (!ready || !terms) return;
    const seq = ++revalidateSeq.current;
    const timer = setTimeout(async () => {
      // 진행 차단 판정과 확인 필요 항목을 함께 갱신한다.
      const [stateResult, reviewResult] = await Promise.allSettled([
        getValidationState({ terms, worker_birth_date: workerBirthDate || null }),
        getReviewItems({ terms }),
      ]);
      // 더 늦게 보낸 요청이 이미 있으면 이 응답은 버린다.
      if (seq !== revalidateSeq.current) return;

      // 판정을 못 받으면 차단 정보를 지워 사용자를 가두지 않는다(서버 422가 최종 방어).
      setValidation(
        stateResult.status === "fulfilled" ? stateResult.value : null,
      );

      if (reviewResult.status === "fulfilled") {
        setReviewItems(reviewResult.value.items);
        setMustConfirm(reviewResult.value.must_confirm);
      } else {
        setReviewItems([]);
        setMustConfirm([]);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [ready, terms, workerBirthDate]);

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
    // 값을 바꾸면 이전 확인은 무효다 — 바뀐 값으로 다시 확인해야 한다.
    const nextConfirmed = confirmedFields.filter((f) => f !== key);
    setTerms(next);
    setUserEditedFields(nextEditedFields);
    setConfirmedFields(nextConfirmed);
    updateSession({
      terms: next,
      userEditedFields: nextEditedFields,
      confirmedFields: nextConfirmed,
      report: null,
      sign: null,
    });
    setError(null);
  }

  // "이 값이 맞아요" 체크 토글. 확인한 필드는 서명 시 confirmed_fields 로 보낸다.
  function toggleConfirm(field: string) {
    const next = confirmedFields.includes(field)
      ? confirmedFields.filter((f) => f !== field)
      : [...confirmedFields, field];
    setConfirmedFields(next);
    updateSession({ confirmedFields: next });
  }

  function changeWorkerBirthDate(value: string) {
    setWorkerBirthDate(value);
    updateSession({
      workerBirthDate: value || null,
      report: null,
      sign: null,
    });
    setError(null);
  }

  async function submit() {
    if (!terms || loading) return;
    // 차단 항목이 남아 있으면 진행하지 않는다. 버튼 비활성과 이중 방어.
    if (validation && !validation.can_proceed) {
      focusField(validation.blocking_fields[0]);
      return;
    }
    // 서명에 쓰일 값을 아직 확인하지 않았으면 진행하지 않는다.
    const stillUnconfirmed = mustConfirm.find(
      (f) => !confirmedFields.includes(f),
    );
    if (stillUnconfirmed) {
      focusField(stillUnconfirmed);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const report = await validateTerms({
        terms,
        worker_birth_date: workerBirthDate || null,
      });
      updateSession({
        terms,
        entryPath,
        workerBirthDate: workerBirthDate || null,
        report,
        sign: null,
      });
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

  // 이 화면은 여기서 고칠 수 있는 항목(step === "review")만 보여준다.
  // 법정 기준 판정(step === "result")은 field 가 판정 코드라 이 화면 입력란과
  // 연결되지 않는다 — 그대로 두면 "확인하러 가기"가 헛돈다. 그 항목들은
  // 다음 결과 화면이 근거·계산식과 함께 이미 보여준다.
  const reviewIssues =
    validation?.issues.filter((issue) => issue.step === "review") ?? [];
  const blockingIssues = reviewIssues.filter((issue) => issue.blocks);
  // 막지는 않지만 알고 진행해야 하는 입력 항목.
  const warningIssues = reviewIssues.filter(
    (issue) => !issue.blocks && issue.severity === "warning",
  );
  // 결과 화면에서 다룰 법정 기준 항목 수 (여기서는 안내만 한다).
  const deferredCount =
    validation?.issues.filter((issue) => issue.step !== "review").length ?? 0;
  const blocked = validation ? !validation.can_proceed : false;

  // 서명에 그대로 쓰이는 항목 — 사용자가 값을 확인해야 한다(review-items).
  const mustConfirmItems = reviewItems.filter((item) =>
    mustConfirm.includes(item.field),
  );
  const unconfirmedCount = mustConfirm.filter(
    (f) => !confirmedFields.includes(f),
  ).length;
  const allConfirmed = unconfirmedCount === 0;

  return (
    <ScreenShell
      step={2}
      backHref={isManual ? "/" : "/upload"}
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

      <Card className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-extrabold text-ink">
            연령별 근로조건 확인
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-muted">
            생년월일을 입력하면 백엔드 검증 코드가 계약 시작일을 기준으로
            15세 이상 18세 미만 근로시간과 야간근로 항목을 확인합니다.
            입력하지 않으면 해당 검사를 결과에 추가하지 않습니다.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="worker-birth-date"
            className="text-sm font-bold text-ink"
          >
            근로자 생년월일 (선택)
          </label>
          <input
            id="worker-birth-date"
            type="date"
            value={workerBirthDate}
            autoComplete="off"
            aria-describedby="worker-birth-date-help"
            disabled={loading}
            onChange={(event) => changeWorkerBirthDate(event.target.value)}
            className="min-h-14 w-full rounded-field border border-slate-400 bg-white px-4 py-3 text-ink outline-none transition disabled:cursor-not-allowed disabled:bg-slate-100 focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
          <p
            id="worker-birth-date-help"
            className="text-xs leading-relaxed text-ink-muted"
          >
            생년월일은 계약 조건이나 계약서·PDF에 넣지 않습니다. 브라우저에서는
            검증과 서명 요청을 이어가기 위해 현재 탭의 sessionStorage에만 임시
            저장하고, 검증·서명 요청 때 백엔드로 전송합니다. 서명 요청이
            성공하면 현재 탭의 저장값에서도 즉시 지우며, 409 응답이나 오류로
            재시도가 필요하면 탭을 닫을 때까지만 유지합니다. 브라우저
            자동완성은 사용하지 않고 결과 화면, 오류 메시지, 로그에도 표시하지
            않습니다. 서버의 보관·삭제 정책은 아직 검증되지 않았습니다.
          </p>
        </div>
      </Card>

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
                  name={key}
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

      {mustConfirmItems.length > 0 && (
        <Card
          className={`flex flex-col gap-4 border-2 ${
            allConfirmed ? "border-brand-line" : "border-amber-300"
          }`}
        >
          <div>
            <h2 className="text-base font-extrabold text-ink">
              서명에 쓰일 값 확인 {allConfirmed ? "✅" : `(${unconfirmedCount}건 남음)`}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">
              아래 항목은 계약서와 서명에 그대로 쓰여요. 값이 맞는지 확인하고
              체크해 주세요. 틀리면 값을 고치면 다시 확인 대상이 됩니다.
            </p>
          </div>

          <ul className="flex flex-col gap-3">
            {mustConfirmItems.map((item) => {
              const confirmed = confirmedFields.includes(item.field);
              const current = terms[item.field as keyof ContractTerms]?.value;
              const shown =
                current === null ||
                current === undefined ||
                String(current) === ""
                  ? "(비어 있음)"
                  : String(current);
              return (
                <li
                  key={item.field}
                  className={`rounded-field border px-4 py-3 ${
                    confirmed
                      ? "border-brand-line bg-brand-tint/40"
                      : "border-amber-300 bg-amber-50"
                  }`}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-bold text-ink">
                      {item.label}
                    </span>
                    <span className="text-sm font-extrabold text-ink">
                      {shown}
                    </span>
                  </div>
                  {item.reasons.length > 0 && (
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                      {item.reasons.join(" · ")}
                    </p>
                  )}
                  {item.source_text && (
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                      <span aria-hidden="true">📄 </span>
                      계약서 근거: “{item.source_text}”
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        onChange={() => toggleConfirm(item.field)}
                        className="h-5 w-5"
                      />
                      이 값이 맞아요
                    </label>
                    <button
                      type="button"
                      onClick={() => focusField(item.field)}
                      className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-bold text-ink-muted transition hover:border-brand hover:text-ink"
                    >
                      값 고치러 가기
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

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

      {blockingIssues.length > 0 && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">
            <span aria-hidden="true">🚫 </span>
            다음 단계로 갈 수 없습니다
          </p>
          <ul className="mt-2 flex flex-col gap-3">
            {blockingIssues.map((issue) => (
              <li key={issue.field} className="flex flex-col gap-1">
                <span className="font-bold">
                  {issue.label} — {issue.reason}
                </span>
                <span className="text-red-800">→ {issue.fix}</span>
                <button
                  type="button"
                  onClick={() => focusField(issue.field)}
                  className="self-start rounded-full border border-red-300 bg-white px-3 py-1 text-xs font-bold text-red-900 transition hover:border-red-500"
                >
                  고치러 가기
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {warningIssues.length > 0 && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-bold">
            <span aria-hidden="true">⚠️ </span>
            알고 진행하는 항목
          </p>
          <ul className="mt-2 flex flex-col gap-3">
            {warningIssues.map((issue) => (
              <li key={issue.field} className="flex flex-col gap-1">
                <span className="font-bold">
                  {issue.label} — {issue.reason}
                </span>
                <span className="text-amber-800">→ {issue.fix}</span>
                <button
                  type="button"
                  onClick={() => focusField(issue.field)}
                  className="self-start rounded-full border border-amber-300 bg-white px-3 py-1 text-xs font-bold text-amber-900 transition hover:border-amber-500"
                >
                  확인하러 가기
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {deferredCount > 0 && (
        <div className="rounded-field border border-brand-line bg-brand-tint/40 px-4 py-3 text-sm text-ink-muted">
          <span aria-hidden="true">ℹ️ </span>
          법정 기준과 관련된 {deferredCount}개 항목은 다음{" "}
          <span className="font-bold text-ink">검증 결과</span> 화면에서 근거와
          계산식을 함께 보여드려요.
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Button
          onClick={submit}
          disabled={loading || blocked || !allConfirmed}
          className="w-full"
        >
          {loading
            ? "검증 코드가 확인 중이에요…"
            : blocked
              ? "고쳐야 할 항목이 있어요"
              : !allConfirmed
                ? `값 확인이 ${unconfirmedCount}건 남았어요`
                : "조건 확인하고 검증하기 →"}
        </Button>
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
