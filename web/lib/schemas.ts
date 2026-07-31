import { z } from "zod";

export const confidenceSchema = z.enum(["HIGH", "LOW", "NOT_FOUND"]);

export const extractedFieldSchema = z.object({
  value: z.union([z.string(), z.number(), z.null()]),
  confidence: confidenceSchema,
  source_text: z.string().nullable(),
});

export const contractTermsSchema = z.object({
  contract_start: extractedFieldSchema,
  contract_end: extractedFieldSchema,
  workplace: extractedFieldSchema,
  job_description: extractedFieldSchema,
  work_start_time: extractedFieldSchema,
  work_end_time: extractedFieldSchema,
  break_start_time: extractedFieldSchema,
  break_end_time: extractedFieldSchema,
  work_days_per_week: extractedFieldSchema,
  weekly_holiday_day: extractedFieldSchema,
  wage_type: extractedFieldSchema,
  wage_amount: extractedFieldSchema,
  has_bonus: extractedFieldSchema,
  other_allowance: extractedFieldSchema,
  payday: extractedFieldSchema,
  payment_method: extractedFieldSchema,
  employer_business_name: extractedFieldSchema,
  employer_phone: extractedFieldSchema,
  employer_address: extractedFieldSchema,
  employer_name: extractedFieldSchema,
  worker_address: extractedFieldSchema,
  worker_contact: extractedFieldSchema,
  worker_name: extractedFieldSchema,
});

export const checkStatusSchema = z.enum([
  "OK",
  "VIOLATION",
  "MISSING",
  "UNKNOWN",
]);

export const checkResultSchema = z.object({
  code: z.string(),
  label: z.string(),
  status: checkStatusSchema,
  legal_basis: z.string(),
  standard_year: z.number(),
  calculation: z.string().nullable(),
  detail: z.string().nullable(),
});

export const validationReportSchema = z.object({
  checks: z.array(checkResultSchema),
  estimated_monthly_pay: z.number().nullable(),
  wage_shortfall: z.number().nullable(),
});

export const chatIntentSchema = z.enum([
  "FIELD_LOOKUP",
  "CALCULATION",
  "MISSING_CLAUSE",
  "LEGAL_STANDARD",
  "OUT_OF_SCOPE",
  "NEEDS_CLARIFICATION",
]);

export const chatEvidenceKindSchema = z.enum([
  "CONTRACT",
  "VALIDATION",
  "LEGAL_STANDARD",
  "OFFICIAL_GUIDANCE",
]);

export const contractChatResponseSchema = z.object({
  intent: chatIntentSchema,
  answer: z.string(),
  limitations: z.string(),
  evidence: z.array(
    z.object({
      kind: chatEvidenceKindSchema,
      label: z.string(),
      value: z.string(),
    }),
  ),
  action: z
    .object({
      label: z.string(),
      href: z.string().startsWith("/"),
    })
    .nullable(),
  suggestions: z.array(z.string()),
});

export const generalQuestionResponseSchema = z.object({
  answer: z.string(),
  limitations: z.string(),
  evidence: z.array(
    z.object({
      kind: chatEvidenceKindSchema,
      label: z.string(),
      value: z.string(),
    }),
  ),
  action: z
    .object({
      label: z.string(),
      href: z.string().startsWith("/"),
    })
    .nullable(),
  suggestions: z.array(z.string()),
});

// 입력값 유효성 + 진행 차단 판정. 백엔드 severity.py 의 Issue/ValidationState 와 1:1.
export const validationSeveritySchema = z.enum(["error", "warning", "info"]);

export const validationIssueSchema = z.object({
  field: z.string(),
  label: z.string(),
  severity: validationSeveritySchema,
  value: z.union([z.string(), z.number(), z.null()]),
  reason: z.string(),
  fix: z.string(),
  blocks: z.boolean(),
  step: z.string(),
  source: z.string(),
});

export const validationStateSchema = z.object({
  can_proceed: z.boolean(),
  blocking_fields: z.array(z.string()),
  counts: z.object({
    error: z.number().int().nonnegative(),
    warning: z.number().int().nonnegative(),
    info: z.number().int().nonnegative(),
  }),
  issues: z.array(validationIssueSchema),
});

export const documentStatusSchema = z.enum([
  "DRAFTING",
  "REVIEW_REQUESTED",
  "TERMS_CONFIRMED",
  "ON_PROCESSING",
  "ON_GOING",
  "COMPLETED",
  "ABORTED",
  "PROCESSING_FAILED",
]);

export const entryPathSchema = z.enum(["PHOTO", "MANUAL"]);

export const analyzeSignResponseSchema = z.object({
  document_id: z.string().min(1),
  status: documentStatusSchema,
  report: validationReportSchema,
  message: z.string(),
});

export const violationBlockedEnvelopeSchema = z.object({
  detail: z.object({
    message: z.string(),
    problems: z.array(z.string()),
    hint: z.string(),
  }),
});

// analyze-sign 이 확인 필요·이름 불일치 등으로 막을 때(위반과 다른 409 형태).
export const signBlockedEnvelopeSchema = z.object({
  detail: z
    .object({
      code: z.string().optional(),
      message: z.string(),
      hint: z.string().default(""),
      fields: z.array(z.string()).optional(),
    })
    .passthrough(),
});

// review-items — 확인이 필요한 항목 목록.
export const reviewItemSchema = z.object({
  field: z.string(),
  label: z.string(),
  value: z.union([z.string(), z.number(), z.null()]),
  confidence: confidenceSchema,
  source_text: z.string().nullable(),
  priority: z.enum(["high", "medium", "low"]),
  reasons: z.array(z.string()),
  affects_judgment: z.boolean(),
  printed_on_contract: z.boolean(),
});

export const reviewItemsResponseSchema = z.object({
  items: z.array(reviewItemSchema),
  must_confirm: z.array(z.string()),
});

export const signStatusResponseSchema = z.object({
  document_id: z.string().min(1),
  status: documentStatusSchema,
  signed: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  download_url: z.string().url().nullable(),
});
