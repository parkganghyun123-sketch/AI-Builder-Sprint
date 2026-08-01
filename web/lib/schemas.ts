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

const APPROVED_EXTERNAL_ACTION_HREFS = [
  "https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230700845",
  "https://1350.moel.go.kr/",
] as const;

export const actionHrefSchema = z.string().refine(
  (href) =>
    /^\/(?!\/)[^\s]*$/.test(href) ||
    APPROVED_EXTERNAL_ACTION_HREFS.some((approved) => href === approved),
  "허용되지 않은 이동 주소입니다.",
);

export const contractChatResponseSchema = z.object({
  intent: chatIntentSchema,
  answer: z.string(),
  limitations: z.string(),
  evidence: z.array(
    z.object({
      kind: chatEvidenceKindSchema,
      label: z.string(),
      value: z.string(),
      url: z.string().url().nullable(),
    }),
  ),
  action: z
    .object({
      label: z.string(),
      href: actionHrefSchema,
    })
    .nullable(),
  suggestions: z.array(z.string()),
});

export const generalQuestionTopicSchema = z.enum([
  "WEEKLY_HOLIDAY",
  "MINIMUM_WAGE",
  "BREAK_TIME",
  "WRITTEN_CONTRACT",
  "MINOR_WORK",
  "EXTRA_WORK",
  "SEVERANCE_PAY",
  "ANNUAL_LEAVE",
  "DISMISSAL_NOTICE",
  "PROBATION_MINIMUM_WAGE",
  "SOCIAL_INSURANCE",
  "MINOR_DOCUMENTS",
  "PREGNANCY_PROTECTION",
  "DISABILITY_ACCOMMODATION",
  "WAGE_PAYMENT",
  "POST_EMPLOYMENT_SETTLEMENT",
  "OUT_OF_SCOPE",
]);

export const generalQuestionResponseSchema = z.object({
  topic: generalQuestionTopicSchema,
  answer: z.string(),
  limitations: z.string(),
  evidence: z.array(
    z.object({
      kind: chatEvidenceKindSchema,
      label: z.string(),
      value: z.string(),
      url: z.string().url().nullable(),
    }),
  ),
  action: z
    .object({
      label: z.string(),
      href: actionHrefSchema,
    })
    .nullable(),
  suggestions: z.array(z.string()),
  retrieved_kb_ids: z.array(z.string()).default([]),
  retrieved_source_ids: z.array(z.string()).default([]),
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

// "말 꺼내기" 문구 — bridge/templates.py + bridge/numbers.py 대응.
export const ownerMessageSchema = z.object({
  message: z.string().nullable(),
  lines: z.array(z.string()),
  numbers_verified: z.boolean(),
});

// "몰라서 못 받는 것들" — backend/app/validation/entitlements.py 대응.
export const audienceSchema = z.enum([
  "EVERYONE",
  "MINOR",
  "PREGNANT",
  "POSTPARTUM",
  "FEMALE",
  "DISABILITY",
]);

export const entitlementSchema = z.object({
  code: z.string(),
  label: z.string(),
  audience: audienceSchema,
  summary: z.string(),
  detail: z.string(),
  legal_basis: z.string(),
  /** 계약서 값으로 판정할 수 있는가. false면 안내만 — 위반처럼 표시하지 말 것 */
  verifiable: z.boolean(),
  employer_penalty: z.string().nullable(),
});

export const entitlementsResponseSchema = z.object({
  items: z.array(entitlementSchema),
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

export const entryPathSchema = z.enum(["PHOTO", "MANUAL", "EMPLOYER"]);

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

// analyze-sign 이 성립하지 않는 값(임금 0원 등)으로 문서 생성 자체를 거부할 때(422).
// backend/app/routers/contracts.py:_reject_if_blocking — validation-state 의
// issues 와 같은 형태(reason·fix)라 화면도 blockingIssues 와 같은 UI로 보여준다.
export const invalidContractValuesEnvelopeSchema = z.object({
  detail: z.object({
    code: z.literal("INVALID_CONTRACT_VALUES"),
    message: z.string(),
    blocking_fields: z.array(z.string()),
    issues: z.array(validationIssueSchema),
  }),
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

/**
 * 문서 참여자.
 *
 * ⚠️ 우리 DB에 저장된 값이 아니다. 문서를 열 때마다 모두싸인에서 읽어온다.
 *    이름·이메일을 우리가 쌓으면 보관 기간과 삭제 책임이 생긴다.
 */
export const signParticipantSchema = z.object({
  name: z.string(),
  order: z.number().int(),
  signed: z.boolean(),
});

// ⚠️ title·participants 는 optional 로 둔다.
//
//    프론트(Vercel)와 백엔드(Railway)는 따로 배포된다. 새 화면이 옛 백엔드와
//    잠깐 만나는 구간이 반드시 생기는데, 그때 필수로 두면 스키마 파싱이 실패해
//    "서버 응답 형식이 예상과 다릅니다"로 화면 전체가 죽는다.
//    기본값은 api.ts 의 getSignStatus 가 채워 넣는다.
export const signStatusResponseSchema = z.object({
  document_id: z.string().min(1),
  title: z.string().optional(),
  status: documentStatusSchema,
  signed: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  participants: z.array(signParticipantSchema).optional(),
  download_url: z.string().url().nullable(),
});

// ============================================================
// 5. 로그인 — backend/app/routers/auth.py 대응
// ============================================================

export const userRoleSchema = z.enum(["WORKER", "EMPLOYER"]);

export const meResponseSchema = z.object({
  user_id: z.string().min(1),
  nickname: z.string(),
  role: userRoleSchema,
});

export const loginUrlResponseSchema = z.object({
  authorize_url: z.string().min(1),
});

export const callbackResponseSchema = z.object({
  access_token: z.string().min(1),
  user: meResponseSchema,
});

// 401 응답 본문. code 로 "로그인 필요"와 "세션 만료"를 구분한다.
export const authErrorEnvelopeSchema = z.object({
  detail: z
    .object({
      code: z.string().optional(),
      message: z.string().default("로그인이 필요합니다."),
    })
    .passthrough(),
});

// 보관함 목록 — backend/app/routers/sign.py ArchiveItem 대응.
//
// ⚠️ participants·download_url·stale 은 optional 로 둔다. signStatusResponseSchema
//    와 같은 이유 — 프론트가 먼저 배포되는 구간에서 필수로 두면 목록 전체가 죽는다.
//    기본값은 api.ts 의 listMyContracts 가 채운다.
export const archiveItemSchema = z.object({
  document_id: z.string().min(1),
  title: z.string(),
  status: documentStatusSchema,
  signed: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  entry_path: entryPathSchema,
  created_at: z.string(),
  participants: z.array(signParticipantSchema).optional(),
  download_url: z.string().url().nullable().optional(),
  /** 제공자 조회에 실패해 마지막 저장값을 보여주는 중인가 */
  stale: z.boolean().optional(),
});

export const archiveListSchema = z.array(archiveItemSchema);

// ============================================================
// 6. 근거 추적형 RAG 계약 비서 — POST /chat
// ============================================================

export const groundedChatIntentSchema = z.enum([
  "FIELD_LOOKUP",
  "CALCULATION",
  "MISSING_CLAUSE",
  "LEGAL_STANDARD",
  "OUT_OF_SCOPE",
]);

export const groundedChatEvidenceKindSchema = z.enum([
  "CONTRACT",
  "LEGAL",
  "CALCULATION",
]);

export const chatAnswerModeSchema = z.enum([
  "DETERMINISTIC_TEMPLATE",
  "GROUNDED_GENERATION",
  "NATURAL_GROUNDED_GENERATION",
  "OPENAI_GROUNDED_GENERATION",
]);

export const retrievedKnowledgeSchema = z.object({
  kb_id: z.string(),
  title: z.string(),
  source_ids: z.array(z.string()),
  score: z.number().min(0).max(1),
});

export const chatResponseSchema = z.object({
  intent: groundedChatIntentSchema,
  topic: z.string(),
  answer: z.string(),
  evidence: z.array(
    z.object({
      kind: groundedChatEvidenceKindSchema,
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
