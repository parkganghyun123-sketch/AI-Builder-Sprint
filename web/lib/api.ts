import type { z } from "zod";
import { readToken } from "./auth";
import {
  analyzeSignResponseSchema,
  archiveListSchema,
  authErrorEnvelopeSchema,
  callbackResponseSchema,
  contractChatResponseSchema,
  contractTermsSchema,
  entitlementsResponseSchema,
  generalQuestionResponseSchema,
  invalidContractValuesEnvelopeSchema,
  loginUrlResponseSchema,
  meResponseSchema,
  ownerMessageSchema,
  reviewItemsResponseSchema,
  signBlockedEnvelopeSchema,
  signStatusResponseSchema,
  validationReportSchema,
  validationStateSchema,
  violationBlockedEnvelopeSchema,
} from "./schemas";
import type {
  AnalyzeSignRequest,
  ArchiveItem,
  ContractChatRequest,
  GeneralQuestionTopic,
  InvalidContractValues,
  Me,
  PreviewRequest,
  SignBlocked,
  UserRole,
  ValidateRequest,
  ViolationBlocked,
} from "./types";

const BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

type ApiErrorCode =
  | "BAD_INPUT"
  | "CONFLICT"
  | "FILE_TOO_LARGE"
  | "INVALID_RESPONSE"
  | "LOGIN_REQUIRED"
  | "NETWORK"
  | "SERVER"
  | "UNAVAILABLE"
  | "UNKNOWN";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null,
    public readonly code: ApiErrorCode,
    public readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 서명 발송·보관함 등 로그인이 필요한 요청이 401을 반환했을 때.
 *
 * ⚠️ reason 으로 "토큰 없음"과 "만료·위조"를 구분한다. 화면이 둘 다
 *    "요청 실패"로 뭉뚱그리면 사용자는 무엇을 해야 할지 모른다.
 *      LOGIN_REQUIRED  → "로그인하고 계속하기" 버튼
 *      SESSION_INVALID → "세션이 만료됐어요. 다시 로그인해 주세요"
 */
export class LoginRequiredError extends ApiError {
  constructor(public readonly reason: "LOGIN_REQUIRED" | "SESSION_INVALID") {
    super(
      reason === "SESSION_INVALID"
        ? "세션이 만료됐어요. 다시 로그인해 주세요."
        : "이 단계는 로그인이 필요합니다.",
      401,
      "LOGIN_REQUIRED",
      false,
    );
    this.name = "LoginRequiredError";
  }
}

/** analyze-sign이 법정 기준 위반으로 막았을 때(HTTP 409). 확인 후 진행 가능. */
export class ViolationBlockedError extends ApiError {
  constructor(public readonly detail: ViolationBlocked) {
    super(
      "서명 전에 다시 확인해야 할 계약 조건이 있습니다.",
      409,
      "CONFLICT",
      false,
    );
    this.name = "ViolationBlockedError";
  }
}

/**
 * analyze-sign이 값 확인 누락·이름 불일치로 막았을 때(HTTP 409).
 * 위반과 달리 '알고 진행'으로 넘길 수 없고, 돌아가서 확인·수정해야 한다.
 */
export class SignBlockedError extends ApiError {
  constructor(public readonly detail: SignBlocked) {
    super(detail.message, 409, "CONFLICT", false);
    this.name = "SignBlockedError";
  }
}

/**
 * analyze-sign이 성립하지 않는 값(임금 0원 등)으로 문서 생성 자체를
 * 거부했을 때(HTTP 422). 클라이언트 사전 점검(getValidationState)을
 * 우회해 직접 호출한 경우에도 서버가 같은 형태(issues)로 다시 막는다.
 */
export class InvalidContractValuesError extends ApiError {
  constructor(public readonly detail: InvalidContractValues) {
    super(detail.message, 422, "BAD_INPUT", false);
    this.name = "InvalidContractValuesError";
  }
}

/** 뒤에 붙일 백엔드 사유. 있으면 "(사유)" 형태로 덧붙인다. */
function suffix(detail?: string): string {
  return detail ? ` (${detail})` : "";
}

function responseError(
  path: string,
  status: number,
  detail?: string,
): ApiError {
  if (status === 400 || status === 422) {
    return new ApiError(
      `입력한 값을 확인한 뒤 다시 시도해 주세요.${suffix(detail)}`,
      status,
      "BAD_INPUT",
      false,
    );
  }
  if (status === 413) {
    return new ApiError(
      "파일이 너무 큽니다. 더 작은 파일로 다시 시도해 주세요.",
      status,
      "FILE_TOO_LARGE",
      false,
    );
  }
  if (status === 401 || status === 403) {
    return new ApiError(
      `요청 권한을 확인하지 못했어요. 잠시 후 다시 시도해 주세요.${suffix(detail)}`,
      status,
      "UNKNOWN",
      false,
    );
  }
  if (status === 404) {
    return new ApiError(
      `요청 주소를 찾지 못했어요. 서버 연결 설정을 확인해 주세요.${suffix(detail)}`,
      status,
      "UNKNOWN",
      false,
    );
  }
  if (status === 502 || status === 503 || status === 504) {
    return new ApiError(
      "전자서명 서비스와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
      status,
      "UNAVAILABLE",
      true,
    );
  }
  if (status >= 500) {
    return new ApiError(
      `서버에서 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.${suffix(detail)}`,
      status,
      "SERVER",
      true,
    );
  }
  return new ApiError(
    `요청을 처리하지 못했어요 (오류 코드 ${status}). 잠시 후 다시 시도해 주세요.${suffix(detail)}`,
    status,
    "UNKNOWN",
    status === 408 || status === 429,
  );
}

/** 실패 응답에서 FastAPI 오류 사유(detail)를 최대한 뽑아낸다. 실패해도 무시한다. */
async function readErrorDetail(response: Response): Promise<string | undefined> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: unknown };
        if (typeof first?.msg === "string") return first.msg;
      }
    }
  } catch {
    // 본문이 JSON이 아니면 사유 없이 진행한다.
  }
  return undefined;
}

/** 토큰이 있을 때만 Authorization 헤더를 붙인다. 로그인 없이도 되는 요청에 섞여도 무해하다. */
function authHeaders(): HeadersInit {
  const token = readToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...init?.headers },
    });
  } catch {
    throw new ApiError(
      "백엔드에 연결할 수 없습니다. 네트워크와 API 주소를 확인해 주세요.",
      null,
      "NETWORK",
      true,
    );
  }

  if (response.status === 401) {
    const json: unknown = await response.json().catch(() => null);
    const parsed = authErrorEnvelopeSchema.safeParse(json);
    const code = parsed.success ? parsed.data.detail.code : undefined;
    throw new LoginRequiredError(
      code === "SESSION_INVALID" ? "SESSION_INVALID" : "LOGIN_REQUIRED",
    );
  }

  return response;
}

async function parseJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new ApiError(
      "서버 응답 형식을 확인할 수 없습니다.",
      response.status,
      "INVALID_RESPONSE",
      false,
    );
  }

  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new ApiError(
      "서버 응답 형식이 예상과 다릅니다.",
      response.status,
      "INVALID_RESPONSE",
      false,
    );
  }
  return parsed.data;
}

async function sendJson<T>(
  path: string,
  method: string,
  body: unknown,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (response.status === 409) {
    const json: unknown = await response.json().catch(() => null);
    // 1) 법정 기준 위반 — 확인 후 진행 가능(problems 형태).
    const violation = violationBlockedEnvelopeSchema.safeParse(json);
    if (violation.success) {
      throw new ViolationBlockedError(violation.data.detail);
    }
    // 2) 값 확인 누락·이름 불일치 등 — 돌아가서 고쳐야 함.
    const blocked = signBlockedEnvelopeSchema.safeParse(json);
    if (blocked.success) {
      throw new SignBlockedError(blocked.data.detail);
    }
    throw responseError(path, response.status);
  }
  if (response.status === 422) {
    const json: unknown = await response.json().catch(() => null);
    const invalid = invalidContractValuesEnvelopeSchema.safeParse(json);
    if (invalid.success) {
      throw new InvalidContractValuesError(invalid.data.detail);
    }
    throw responseError(path, response.status);
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw responseError(path, response.status, detail);
  }
  return parseJson(response, schema);
}

function postJson<T>(path: string, body: unknown, schema: z.ZodType<T>) {
  return sendJson(path, "POST", body, schema);
}

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await request(path);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw responseError(path, response.status, detail);
  }
  return parseJson(response, schema);
}

/** 계약서 이미지/PDF → AI 추출 결과. 원본 파일은 브라우저 저장소에 보관하지 않는다. */
export async function extractTerms(file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await request("/contracts/extract", {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw responseError("/contracts/extract", response.status);
  return parseJson(response, contractTermsSchema);
}

/** 사용자가 확인한 조건 → 결정론적 법정 기준 판정. */
export function validateTerms(body: ValidateRequest) {
  return postJson("/contracts/validate", body, validationReportSchema);
}

/** 확인된 계약 조건과 검증 결과만 검색하는 계약 비서. 원문 계약서는 전송하지 않는다. */
export function askContractAssistant(body: ContractChatRequest) {
  return postJson("/contracts/chat", body, contractChatResponseSchema);
}

/** 계약서 없이 묻는 일반 기준 질문. 개인 정보나 계약서 원문은 전송하지 않는다. */
export function askGeneralQuestion(
  question: string,
  context: GeneralQuestionTopic | null = null,
) {
  return postJson(
    "/questions/general",
    { question, context },
    generalQuestionResponseSchema,
  );
}

/**
 * 입력값 유효성 + 진행 차단 판정. 프론트는 이 응답만 보고 "다음"을 켜고 끈다.
 * ⚠️ 같은 규칙을 화면에 복사하지 말 것. can_proceed·issues 를 그대로 쓴다.
 */
export function getValidationState(body: ValidateRequest) {
  return postJson("/contracts/validation-state", body, validationStateSchema);
}

/**
 * 판정 결과 → 사장님께 보낼 문의 메시지.
 *
 * 계약서가 최저임금 미달인 걸 아는 것과, 그걸 사장님에게 말하는 것은
 * 다른 문제다. 이 호출은 후자를 돕는다.
 *
 * ⚠️ numbers_verified 가 false 면 화면에 표시하지 말 것.
 *    문장의 숫자가 판정 결과와 대조되지 않았다는 뜻이다.
 */
export function buildOwnerMessage(body: ValidateRequest) {
  return postJson("/contracts/message", body, ownerMessageSchema);
}

/**
 * 확인이 필요한 항목 목록. must_confirm 은 서명 전 반드시 확인해야 하는 필드 키다.
 * 화면은 confidence 를 직접 해석하지 말고 이 응답을 그대로 쓴다.
 */
export function getReviewItems(body: ValidateRequest) {
  return postJson(
    "/contracts/review-items",
    { terms: body.terms },
    reviewItemsResponseSchema,
  );
}

/** 조건 → 검증 → PDF → 모두싸인 서명 요청. */
export function analyzeAndSign(body: AnalyzeSignRequest) {
  return postJson(
    "/contracts/analyze-sign",
    body,
    analyzeSignResponseSchema,
  );
}

/**
 * "몰라서 못 받는 것들" 전체 목록.
 *
 * ⚠️ 전체를 받아 **화면에서 필터링한다.** 그래서 서버는 사용자가
 *    임신했는지, 장애가 있는지, 미성년자인지 알지 못한다.
 *    민감정보를 다루는 가장 안전한 방법은 받지 않는 것이다.
 *
 * ⚠️ 로그인이 필요 없다. 권리를 알기 위해 가입해야 한다면 그것부터가 벽이다.
 */
export async function getEntitlements() {
  const response = await request("/entitlements");
  if (!response.ok) throw responseError("/entitlements", response.status);
  return parseJson(response, entitlementsResponseSchema);
}

/** 조건 → PDF 미리보기. 경로 B에는 백엔드가 초안 워터마크를 적용한다. */
export async function previewPdf(body: PreviewRequest): Promise<Blob> {
  const response = await request("/contracts/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw responseError("/contracts/preview", response.status);

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/pdf")) {
    throw new ApiError(
      "PDF 응답 형식이 예상과 다릅니다.",
      response.status,
      "INVALID_RESPONSE",
      false,
    );
  }
  return response.blob();
}

/** 모두싸인의 현재 서명 상태를 백엔드를 통해 조회한다. 로그인이 필요하다. */
export async function getSignStatus(documentId: string) {
  const response = await request(
    `/contracts/${encodeURIComponent(documentId)}/status`,
  );
  if (!response.ok) {
    throw responseError("/contracts/{id}/status", response.status);
  }

  const parsed = await parseJson(response, signStatusResponseSchema);

  // 프론트(Vercel)와 백엔드(Railway)는 따로 배포된다. 새 화면이 옛 백엔드와
  // 잠깐 만나는 구간에서 title·participants 가 없을 수 있다.
  // 화면이 매번 undefined 를 다루지 않도록 여기서 한 번만 채운다.
  return {
    ...parsed,
    title: parsed.title ?? "근로계약서",
    participants: parsed.participants ?? [],
  };
}

// ============================================================
// 5. 로그인 — backend/app/routers/auth.py 대응
// ============================================================

/** 카카오 로그인 주소. 프론트엔드에는 카카오 키를 두지 않는다. */
export function getLoginUrl() {
  return getJson("/auth/login-url", loginUrlResponseSchema);
}

/** 인가 코드 → 우리 세션 토큰. state 는 login-url 이 발급한 값을 그대로 넘긴다. */
export function completeKakaoLogin(body: {
  code: string;
  state: string;
  role: UserRole;
}) {
  return sendJson(
    "/auth/kakao/callback",
    "POST",
    body,
    callbackResponseSchema,
  );
}

/** 현재 로그인 사용자. 토큰이 없거나 만료됐으면 LoginRequiredError. */
export function getMe(): Promise<Me> {
  return getJson("/auth/me", meResponseSchema);
}

/** 역할 변경. 접근 통제와 무관하다 — 화면 흐름만 바꾼다. */
export function setRole(role: UserRole): Promise<Me> {
  return sendJson("/auth/me/role", "PATCH", { role }, meResponseSchema);
}

/**
 * 내 보관함 목록. 로그인이 필요하다.
 *
 * ⚠️ 옛 백엔드는 participants·download_url 을 주지 않는다. 여기서 기본값을
 *    채워 화면이 옵셔널 체이닝 없이 쓸 수 있게 한다 (getSignStatus 와 같은 처리).
 */
export async function listMyDocuments(): Promise<ArchiveItem[]> {
  const items = await getJson("/contracts", archiveListSchema);
  return items.map((item) => ({
    ...item,
    participants: item.participants ?? [],
    download_url: item.download_url ?? null,
    stale: item.stale ?? false,
  }));
}
