/**
 * 백엔드 API 클라이언트.
 *
 * 엔드포인트는 backend/app/routers/ 기준이다. 명세: http://localhost:8000/docs
 *   POST /contracts/validate       조건 → 판정
 *   POST /contracts/preview        조건 → 계약서 PDF (bytes)
 *   POST /contracts/analyze-sign   조건 → 검증 → PDF → 서명 요청
 *   GET  /contracts/{id}/status    서명 상태
 */
import type {
  AnalyzeSignRequest,
  AnalyzeSignResponse,
  PreviewRequest,
  ValidationReport,
  ValidateRequest,
  ViolationBlocked,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** analyze-sign 이 위반을 이유로 막았을 때 (HTTP 409) */
export class ViolationBlockedError extends Error {
  constructor(public readonly detail: ViolationBlocked) {
    super(detail.message);
    this.name = "ViolationBlockedError";
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (res.status === 409) {
    const data = await res.json();
    throw new ViolationBlockedError(data.detail as ViolationBlocked);
  }
  if (!res.ok) {
    throw new Error(`${path} 실패 (${res.status})`);
  }
  return (await res.json()) as T;
}

/** 조건 → 법정 기준 판정 */
export function validateTerms(body: ValidateRequest) {
  return post<ValidationReport>("/contracts/validate", body);
}

/** 조건 → 검증 → PDF → 서명 요청 */
export function analyzeAndSign(body: AnalyzeSignRequest) {
  return post<AnalyzeSignResponse>("/contracts/analyze-sign", body);
}

/** 조건 → 계약서 PDF. 경로 B(MANUAL)는 "확인 전 초안" 워터마크가 찍힌다 */
export async function previewPdf(body: PreviewRequest): Promise<Blob> {
  const res = await fetch(`${BASE}/contracts/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`미리보기 실패 (${res.status})`);
  return res.blob();
}

/** 서명 상태 조회 */
export async function getSignStatus(documentId: string) {
  const res = await fetch(`${BASE}/contracts/${documentId}/status`);
  if (!res.ok) throw new Error(`상태 조회 실패 (${res.status})`);
  return res.json();
}
