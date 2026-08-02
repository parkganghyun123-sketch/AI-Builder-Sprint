"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ScreenShell } from "@/components/ScreenShell";
import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import {
  FieldInput,
  type FieldOption,
} from "@/components/FieldInput";
import { Button, ButtonLink, Card, Spinner } from "@/components/ui";
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

/** 서버 내부 용어를 그대로 노출하지 않고 사용자가 확인할 이유만 설명한다. */
function reviewItemMessage(item: ReviewItem, hasValue: boolean) {
  if (!hasValue) return "위 입력란에 내용을 적어 주세요.";

  const messages: string[] = [];
  if (item.printed_on_contract) {
    messages.push("서명할 문서에 들어갈 내용이에요.");
  }
  if (item.affects_judgment) {
    messages.push("근로조건을 확인하는 데 필요한 내용이에요.");
  }
  if (item.confidence !== "HIGH") {
    messages.push("입력한 값이 맞는지 한 번 더 확인해 주세요.");
  }

  return messages.join(" ") || "입력한 값이 맞는지 확인해 주세요.";
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
      title: "근무시간",
      description: "출근·퇴근 시각과 주 근무일수를 입력해 주세요.",
      fields: [
        {
          key: "work_start_time",
          label: "출근 시각",
          type: "time",
          placeholder: "HH:MM",
        },
        {
          key: "work_end_time",
          label: "퇴근 시각",
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
          label: "기타 수당",
          unit: "원 또는 계약서 표기",
          placeholder: "예: 주휴수당 포함 · 없으면 비워 두세요",
        },
        {
          key: "payday",
          label: "급여일",
          placeholder: "예: 매월 25일",
        },
        {
          key: "payment_method",
          label: "급여 받는 방법",
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
  // 빈 폼으로 시작하는 두 경로.
  //   path=B         근로자가 구두로 들은 조건을 입력 (계약서 없음)
  //   path=EMPLOYER  사업주가 계약서를 작성
  // 둘은 **같은 입력 폼과 같은 검증 API**를 쓴다. 다른 것은 화면 문구와
  // 서명 순서뿐이다(백엔드 modusign.request_signature employer_first 참고).
  const pathParam = searchParams.get("path");
  const blankFormPath: EntryPath | null =
    pathParam === "B" ? "MANUAL" : pathParam === "EMPLOYER" ? "EMPLOYER" : null;
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [entryPath, setEntryPath] = useState<EntryPath>("PHOTO");
  const [workerBirthDate, setWorkerBirthDate] = useState("");
  const [workerIsPregnant, setWorkerIsPregnant] = useState(false);
  const [workerPregnancyWeek, setWorkerPregnancyWeek] = useState<number | null>(
    null,
  );
  const [workerIsPostpartumWithinYear, setWorkerIsPostpartumWithinYear] =
    useState(false);
  const [workerIsDisabled, setWorkerIsDisabled] = useState(false);
  const [userEditedFields, setUserEditedFields] = useState<
    (keyof ContractTerms)[]
  >([]);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 빈칸 경고는 사용자가 다음 버튼을 누른 뒤에만 보여준다.
  const [submitAttempted, setSubmitAttempted] = useState(false);
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

    if (blankFormPath) {
      // 같은 경로로 돌아온 경우엔 입력값을 살린다. 새로고침 한 번에
      // 다 지워지면 스무 개 넘는 항목을 처음부터 다시 입력해야 한다.
      if (existing.entryPath === blankFormPath && existing.terms) {
        setTerms(existing.terms);
        setWorkerBirthDate(existing.workerBirthDate ?? "");
        setWorkerIsPregnant(existing.workerIsPregnant);
        setWorkerPregnancyWeek(existing.workerPregnancyWeek);
        setWorkerIsPostpartumWithinYear(existing.workerIsPostpartumWithinYear);
        setWorkerIsDisabled(existing.workerIsDisabled);
        setUserEditedFields(existing.userEditedFields);
        setConfirmedFields(existing.confirmedFields);
      } else {
        const created = startSession(createEmptyTerms(), blankFormPath);
        setTerms(created.terms);
        setWorkerBirthDate(created.workerBirthDate ?? "");
        setWorkerIsPregnant(created.workerIsPregnant);
        setWorkerPregnancyWeek(created.workerPregnancyWeek);
        setWorkerIsPostpartumWithinYear(created.workerIsPostpartumWithinYear);
        setWorkerIsDisabled(created.workerIsDisabled);
        setUserEditedFields(created.userEditedFields);
        setConfirmedFields(created.confirmedFields);
      }
      setEntryPath(blankFormPath);
    } else {
      setTerms(existing.terms);
      setEntryPath(existing.entryPath);
      setWorkerBirthDate(existing.workerBirthDate ?? "");
      setWorkerIsPregnant(existing.workerIsPregnant);
      setWorkerPregnancyWeek(existing.workerPregnancyWeek);
      setWorkerIsPostpartumWithinYear(existing.workerIsPostpartumWithinYear);
      setWorkerIsDisabled(existing.workerIsDisabled);
      setUserEditedFields(existing.userEditedFields);
      setConfirmedFields(existing.confirmedFields);
    }
    setReady(true);
  }, [blankFormPath]);

  // 값이 바뀔 때마다 백엔드에 다시 물어 진행 차단 여부를 갱신한다.
  // onChange마다 부르면 요청이 쏟아지므로 입력이 멈춘 뒤 400ms 두고 부른다.
  // 판정 규칙은 백엔드 소유다 — 여기서 재현하지 않는다.
  useEffect(() => {
    if (!ready || !terms) return;
    const seq = ++revalidateSeq.current;
    const timer = setTimeout(async () => {
      // 진행 차단 판정과 확인 필요 항목을 함께 갱신한다.
      const [stateResult, reviewResult] = await Promise.allSettled([
        getValidationState({
          terms,
          worker_birth_date: workerBirthDate || null,
          worker_is_pregnant: workerIsPregnant,
          worker_pregnancy_week: workerPregnancyWeek,
          worker_is_postpartum_within_year: workerIsPostpartumWithinYear,
          worker_is_disabled: workerIsDisabled,
        }),
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
  }, [
    ready,
    terms,
    workerBirthDate,
    workerIsPregnant,
    workerPregnancyWeek,
    workerIsPostpartumWithinYear,
    workerIsDisabled,
  ]);

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

  function changeWorkerIsPregnant(value: boolean) {
    setWorkerIsPregnant(value);
    // 임신 중이 아니게 되면 주수 입력도 함께 지운다 — 화면에서 숨겨질 값이
    // 세션에 남아 다음 방문 때 불쑥 나타나지 않게 한다.
    const nextWeek = value ? workerPregnancyWeek : null;
    setWorkerPregnancyWeek(nextWeek);
    updateSession({
      workerIsPregnant: value,
      workerPregnancyWeek: nextWeek,
      report: null,
      sign: null,
    });
    setError(null);
  }

  function changeWorkerPregnancyWeek(value: string) {
    const week = value === "" ? null : Number(value);
    setWorkerPregnancyWeek(week);
    updateSession({ workerPregnancyWeek: week, report: null, sign: null });
    setError(null);
  }

  function changeWorkerIsPostpartumWithinYear(value: boolean) {
    setWorkerIsPostpartumWithinYear(value);
    updateSession({
      workerIsPostpartumWithinYear: value,
      report: null,
      sign: null,
    });
    setError(null);
  }

  function changeWorkerIsDisabled(value: boolean) {
    setWorkerIsDisabled(value);
    updateSession({ workerIsDisabled: value, report: null, sign: null });
    setError(null);
  }

  async function submit() {
    if (!terms || loading) return;
    setSubmitAttempted(true);
    setLoading(true);
    setError(null);
    try {
      const request = {
        terms,
        worker_birth_date: workerBirthDate || null,
        worker_is_pregnant: workerIsPregnant,
        worker_pregnancy_week: workerPregnancyWeek,
        worker_is_postpartum_within_year: workerIsPostpartumWithinYear,
        worker_is_disabled: workerIsDisabled,
      };
      // 다음 버튼을 누른 시점의 최신 값으로 누락 항목과 확인 목록을 받는다.
      const [latestValidation, latestReview] = await Promise.all([
        getValidationState(request),
        getReviewItems({ terms }),
      ]);
      setValidation(latestValidation);
      setReviewItems(latestReview.items);
      setMustConfirm(latestReview.must_confirm);

      if (!latestValidation.can_proceed) {
        focusField(latestValidation.blocking_fields[0]);
        return;
      }

      const stillUnconfirmed = latestReview.must_confirm.find(
        (field) => !confirmedFields.includes(field),
      );
      if (stillUnconfirmed) {
        focusField(stillUnconfirmed);
        return;
      }

      const report = await validateTerms(request);
      updateSession({
        terms,
        entryPath,
        workerBirthDate: workerBirthDate || null,
        workerIsPregnant,
        workerPregnancyWeek,
        workerIsPostpartumWithinYear,
        workerIsDisabled,
        report,
        sign: null,
      });
      router.push("/result");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "조건을 확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
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
        description="입력한 조건을 불러오는 중이에요."
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
        description="계약서를 다시 올리거나 조건을 직접 입력해 주세요."
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
  const isEmployer = entryPath === "EMPLOYER";
  // 빈 폼에서 직접 입력하는 두 경로. AI 추출 근거가 없다는 점이 공통이다.
  const isBlankForm = isManual || isEmployer;

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

  const workerProtectionCard = (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-base font-extrabold text-ink">
          해당되는 보호 항목이 있나요? (선택)
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          답해 주시면 나이와 상황에 따라 꼭 알아야 할 근로시간·휴식 기준을
          함께 안내해 드려요. 입력하지 않아도 다음 단계로 갈 수 있습니다.
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
          나이에 따라 적용되는 보호 기준을 확인할 때만 사용하며 계약서에는
          표시하지 않습니다. 입력 내용은 확인 과정에서 전송되며, 전송 후
          보관·삭제 방식은 아직 확인되지 않았습니다. 원하지 않으면 입력하지
          않아도 됩니다.
        </p>
      </div>

      <div className="flex flex-col gap-2 border-t border-brand-line pt-4">
        <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink">
          <input
            type="checkbox"
            checked={workerIsPregnant}
            disabled={loading}
            onChange={(event) => changeWorkerIsPregnant(event.target.checked)}
            className="h-5 w-5"
          />
          임신 중이에요
        </label>
        {workerIsPregnant && (
          <div className="ml-7 flex flex-col gap-1.5">
            <label
              htmlFor="worker-pregnancy-week"
              className="text-sm font-bold text-ink"
            >
              임신 주수 (선택)
            </label>
            <input
              id="worker-pregnancy-week"
              type="number"
              min={1}
              max={42}
              inputMode="numeric"
              value={workerPregnancyWeek ?? ""}
              disabled={loading}
              onChange={(event) =>
                changeWorkerPregnancyWeek(event.target.value)
              }
              className="min-h-14 w-32 rounded-field border border-slate-400 bg-white px-4 py-3 text-ink outline-none transition disabled:cursor-not-allowed disabled:bg-slate-100 focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <p className="text-xs leading-relaxed text-ink-muted">
              임신 주수에 따라 신청할 수 있는 근로시간 단축 기준도 함께
              안내해 드려요.
            </p>
          </div>
        )}
        <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink">
          <input
            type="checkbox"
            checked={workerIsPostpartumWithinYear}
            disabled={loading}
            onChange={(event) =>
              changeWorkerIsPostpartumWithinYear(event.target.checked)
            }
            className="h-5 w-5"
          />
          출산한 지 1년이 안 됐어요
        </label>
        <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink">
          <input
            type="checkbox"
            checked={workerIsDisabled}
            disabled={loading}
            onChange={(event) => changeWorkerIsDisabled(event.target.checked)}
            className="h-5 w-5"
          />
          장애가 있어요
        </label>
        <p className="text-xs leading-relaxed text-ink-muted">
          선택한 내용은 관련 보호 기준을 안내할 때만 사용하며 계약서와 결과
          화면에는 표시하지 않습니다. 입력 내용은 확인 과정에서 전송되며,
          전송 후 보관·삭제 방식은 아직 확인되지 않았습니다. 원하지 않으면
          선택하지 않아도 되며 증빙 서류도 받지 않습니다.
        </p>
      </div>
    </Card>
  );

  return (
    <ScreenShell
      step={2}
      backHref={isBlankForm ? "/" : "/upload"}
      title={
        isEmployer
          ? "근로계약서 작성"
          : isManual
            ? "조건 직접 입력"
            : "읽어낸 조건 확인하기"
      }
      description={
        isEmployer
          ? "정한 근로조건을 아는 만큼 입력해 주세요. 빠진 필수 항목은 다음 버튼을 누르면 알려드릴게요."
          : isManual
            ? "말로 들은 근로조건을 아는 만큼 입력해 주세요. 빠진 필수 항목은 다음 버튼을 누르면 알려드릴게요."
            : "사진에서 읽은 내용이 계약서와 같은지 확인해 주세요."
      }
    >
      {isBlankForm && <DocumentStatusBadge status="DRAFTING" />}

      {isEmployer && (
        <div className="rounded-field border border-brand-line bg-brand-tint/40 px-4 py-3 text-sm leading-relaxed text-ink">
          <span aria-hidden="true">🏪 </span>
          <strong>사장님, 여기서 확인하시면 나중에 다툴 일이 줄어듭니다.</strong>
          <p className="mt-1 text-ink-muted">
            근로계약서 미작성의 1위 이유는 &ldquo;작성해야 하는지
            몰라서&rdquo;입니다. 최저임금·주휴·휴게시간 기준을 입력과 동시에
            확인해 드리고, 작성된 계약서는 전자서명으로 양측이 갖게 됩니다.
          </p>
        </div>
      )}

      {!isBlankForm && lowCount > 0 && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span aria-hidden="true">⚠️ </span>
          확인이 필요한 항목이 {lowCount}개 있어요. 계약서 원문과 함께
          확인해 주세요.
        </div>
      )}

      <p className="rounded-field border border-brand-line bg-brand-tint/60 px-4 py-3 text-sm leading-relaxed text-ink-muted">
        전화번호와 주소는 받지 않아요. 입력한 이름과 근로조건은 다음 단계를
        이어가는 동안만 이 기기에 잠시 보관해요.
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
                  name={key}
                  field={field}
                  onChange={(value) => changeField(key, value)}
                  showExtractionStatus={!isBlankForm}
                />
                {userEdited ? (
                  <p className="text-xs font-semibold text-brand-deep">
                    <span aria-hidden="true">✍️ </span>
                    직접 입력한 값이에요.
                  </p>
                ) : field.source_text ? (
                  <p className="text-xs font-semibold text-ink-muted">
                    <span aria-hidden="true">📄 </span>
                    계약서에서 읽은 값입니다.
                  </p>
                ) : !isBlankForm && hasValue ? (
                  <p className="text-xs font-semibold text-amber-900">
                    <span aria-hidden="true">📄 </span>
                    계약서에서 읽은 값이지만 사진의 어느 부분인지 찾지
                    못했어요. 계약서를 직접 확인해 주세요.
                  </p>
                ) : null}
              </div>
            );
          })}
        </Card>
      ))}

      {mustConfirmItems.length > 0 && (!isManual || submitAttempted) && (
        <Card
          className={`flex flex-col gap-4 border-2 ${
            allConfirmed ? "border-brand-line" : "border-amber-300"
          }`}
        >
          <div>
            <h2 className="text-base font-extrabold text-ink">
              마지막으로 확인해 주세요 {allConfirmed ? "✅" : `(${unconfirmedCount}건 남음)`}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">
              아래 내용이 맞는지 확인해 주세요. 잘못된 값은 위 입력란에서
              고칠 수 있어요.
            </p>
          </div>

          <ul className="flex flex-col gap-3">
            {mustConfirmItems.map((item) => {
              const confirmed = confirmedFields.includes(item.field);
              const current = terms[item.field as keyof ContractTerms]?.value;
              const hasCurrentValue =
                current !== null &&
                current !== undefined &&
                String(current) !== "";
              const shown = hasCurrentValue
                ? String(current)
                : "입력되지 않음";
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
                  <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                    {reviewItemMessage(item, hasCurrentValue)}
                  </p>
                  {item.source_text && (
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                      <span aria-hidden="true">📄 </span>
                      계약서에 적힌 내용: “{item.source_text}”
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
                      {hasCurrentValue ? "값 고치기" : "입력하러 가기"}
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
          <p className="font-bold">조건을 확인하지 못했어요</p>
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

      {submitAttempted && blockingIssues.length > 0 && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-field border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-bold">
            <span aria-hidden="true">🚫 </span>
            입력할 내용이 남아 있어요
          </p>
          <ul className="mt-2 flex flex-col gap-3">
            {blockingIssues.map((issue) => {
              const isMissing =
                issue.value === null ||
                issue.value === undefined ||
                String(issue.value).trim() === "";
              const reason =
                isBlankForm && isMissing
                  ? "다음 단계에 필요한 항목이에요."
                  : issue.reason;
              const fix =
                isBlankForm && isMissing
                  ? isManual
                    ? "말로 들은 내용을 입력해 주세요."
                    : "정한 내용을 입력해 주세요."
                  : issue.fix;

              return (
                <li key={issue.field} className="flex flex-col gap-1">
                  <span className="font-bold">
                    {issue.label} — {reason}
                  </span>
                  <span className="text-red-800">→ {fix}</span>
                  <button
                    type="button"
                    onClick={() => focusField(issue.field)}
                    className="self-start rounded-full border border-red-300 bg-white px-3 py-1 text-xs font-bold text-red-900 transition hover:border-red-500"
                  >
                    {isMissing ? "입력하러 가기" : "고치러 가기"}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {warningIssues.length > 0 && (
        <div className="rounded-field border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-bold">
            <span aria-hidden="true">⚠️ </span>
            한 번 더 확인해 주세요
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
          입력한 근로조건과 꼭 알아야 할 기준은 다음 화면에서 함께 보여드려요.
        </div>
      )}

      {workerProtectionCard}

      <div className="flex flex-col gap-2">
        <Button
          onClick={submit}
          disabled={loading}
          className="w-full"
        >
          {loading
            ? (
                <>
                  <Spinner />
                  확인하는 중
                </>
              )
            : submitAttempted && blocked
              ? "고쳐야 할 항목이 있어요"
              : submitAttempted && !allConfirmed
                ? `확인할 내용이 ${unconfirmedCount}건 남았어요`
                : "다음으로 →"}
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
