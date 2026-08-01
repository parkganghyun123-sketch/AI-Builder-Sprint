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

export const signStatusResponseSchema = z.object({
  document_id: z.string().min(1),
  status: documentStatusSchema,
  signed: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  download_url: z.string().url().nullable(),
});

export const chatIntentSchema = z.enum([
  "FIELD_LOOKUP",
  "CALCULATION",
  "MISSING_CLAUSE",
  "LEGAL_STANDARD",
  "OUT_OF_SCOPE",
]);

export const chatEvidenceKindSchema = z.enum([
  "CONTRACT",
  "LEGAL",
  "CALCULATION",
]);

export const chatAnswerModeSchema = z.enum([
  "DETERMINISTIC_TEMPLATE",
  "GROUNDED_GENERATION",
]);

export const retrievedKnowledgeSchema = z.object({
  kb_id: z.string(),
  title: z.string(),
  source_ids: z.array(z.string()),
  score: z.number().min(0).max(1),
});

export const chatResponseSchema = z.object({
  intent: chatIntentSchema,
  topic: z.string(),
  answer: z.string(),
  evidence: z.array(
    z.object({
      kind: chatEvidenceKindSchema,
      title: z.string(),
      detail: z.string(),
    }),
  ),
  limitation: z.string().nullable(),
  condition_groups: z
    .object({
      met: z.array(z.string()),
      unmet: z.array(z.string()),
      needs_check: z.array(z.string()),
    })
    .nullable(),
  retrieved_knowledge: z.array(retrievedKnowledgeSchema),
  answer_mode: chatAnswerModeSchema,
  suggested_questions: z.array(z.string()),
});
