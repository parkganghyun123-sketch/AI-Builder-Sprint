import { z } from "zod";
import {
  contractTermsSchema,
  documentStatusSchema,
  entryPathSchema,
  validationReportSchema,
} from "./schemas";
import type {
  ContractTerms,
  EntryPath,
  ExtractedField,
} from "./types";

const STORAGE_KEY = "fairsign:contract-session:v1";

const contractTermKeySchema = z.enum([
  "contract_start",
  "contract_end",
  "workplace",
  "job_description",
  "work_start_time",
  "work_end_time",
  "break_start_time",
  "break_end_time",
  "work_days_per_week",
  "weekly_holiday_day",
  "wage_type",
  "wage_amount",
  "has_bonus",
  "other_allowance",
  "payday",
  "payment_method",
  "employer_business_name",
  "employer_phone",
  "employer_address",
  "employer_name",
  "worker_address",
  "worker_contact",
  "worker_name",
]);

const sessionSchema = z.object({
  terms: contractTermsSchema.nullable(),
  entryPath: entryPathSchema,
  report: validationReportSchema.nullable(),
  userEditedFields: z.array(contractTermKeySchema).default([]),
  sign: z
    .object({
      documentId: z.string().min(1),
      status: documentStatusSchema,
    })
    .nullable(),
});

export type FairSignSession = z.infer<typeof sessionSchema>;

export const EMPTY_SESSION: FairSignSession = {
  terms: null,
  entryPath: "PHOTO",
  report: null,
  userEditedFields: [],
  sign: null,
};

function emptyField(): ExtractedField {
  return {
    value: null,
    confidence: "NOT_FOUND",
    source_text: null,
  };
}

const CONTACT_FIELDS = [
  "employer_phone",
  "employer_address",
  "worker_address",
  "worker_contact",
] as const satisfies readonly (keyof ContractTerms)[];

/**
 * 검증 단계에는 필요하지 않은 전화·주소·연락처를 탭 저장소에 남기지 않는다.
 * 스키마 호환을 위해 해당 키는 유지하되 값과 원문 근거를 모두 비운다.
 */
export function minimizeTermsForValidation(
  terms: ContractTerms,
): ContractTerms {
  const minimized = { ...terms };
  for (const key of CONTACT_FIELDS) {
    minimized[key] = emptyField();
  }
  return minimized;
}

function normalizeSession(session: FairSignSession): FairSignSession {
  return {
    ...session,
    terms: session.terms ? minimizeTermsForValidation(session.terms) : null,
  };
}

/** 직접 입력 경로는 계약서에 없던 사실을 추정하지 않고 모든 항목을 비워 시작한다. */
export function createEmptyTerms(): ContractTerms {
  return {
    contract_start: emptyField(),
    contract_end: emptyField(),
    workplace: emptyField(),
    job_description: emptyField(),
    work_start_time: emptyField(),
    work_end_time: emptyField(),
    break_start_time: emptyField(),
    break_end_time: emptyField(),
    work_days_per_week: emptyField(),
    weekly_holiday_day: emptyField(),
    wage_type: emptyField(),
    wage_amount: emptyField(),
    has_bonus: emptyField(),
    other_allowance: emptyField(),
    payday: emptyField(),
    payment_method: emptyField(),
    employer_business_name: emptyField(),
    employer_phone: emptyField(),
    employer_address: emptyField(),
    employer_name: emptyField(),
    worker_address: emptyField(),
    worker_contact: emptyField(),
    worker_name: emptyField(),
  };
}

export function readSession(): FairSignSession {
  if (typeof window === "undefined") return EMPTY_SESSION;

  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return EMPTY_SESSION;

  try {
    const parsed = sessionSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return EMPTY_SESSION;

    const normalized = normalizeSession(parsed.data);
    const serialized = JSON.stringify(normalized);
    if (serialized !== raw) {
      window.sessionStorage.setItem(STORAGE_KEY, serialized);
    }
    return normalized;
  } catch {
    return EMPTY_SESSION;
  }
}

export function writeSession(session: FairSignSession): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(normalizeSession(session)),
  );
}

export function startSession(
  terms: ContractTerms,
  entryPath: EntryPath,
): FairSignSession {
  const session: FairSignSession = {
    terms: minimizeTermsForValidation(terms),
    entryPath,
    report: null,
    userEditedFields: [],
    sign: null,
  };
  writeSession(session);
  return session;
}

export function updateSession(
  patch: Partial<FairSignSession>,
): FairSignSession {
  const session = normalizeSession({ ...readSession(), ...patch });
  writeSession(session);
  return session;
}
