/**
 * 백엔드 `backend/app/schemas.py` 와 1:1 대응하는 프론트 타입.
 *
 * ⚠️ schemas.py 가 단일 진실 공급원이다. 이 파일을 임의로 바꾸지 말고,
 *    schemas.py 가 바뀌면 여기도 함께 갱신한다.
 *
 * 원칙(CLAUDE.md): 화면에 뜨는 판정·숫자·근거는 전부 백엔드 반환값이다.
 * 프론트는 계산하지 않는다.
 */

// ============================================================
// 1. 계약 조건 — A(추출) 출력 = B(검증) 입력
// ============================================================

/** AI 추출 신뢰도. LOW면 화면에서 사용자 확인을 강조한다. */
export type Confidence = "HIGH" | "LOW" | "NOT_FOUND";

/** 추출된 값 하나 + 근거 */
export interface ExtractedField {
  value: string | number | null;
  confidence: Confidence;
  /** 계약서 원문 중 이 값의 근거가 된 부분. 챗봇 "📄 계약서 근거"의 출처 */
  source_text: string | null;
}

/** 표준근로계약서 6번 '월(일, 시간)급' */
export type WageType = "HOURLY" | "DAILY" | "MONTHLY";

/**
 * 계약 조건. 고용노동부 표준근로계약서 항목을 따른다.
 * 경로 A(사진 추출)와 경로 B(직접 입력) 모두 이 형식을 만든다.
 *
 * ⚠️ 시간은 "시각"으로 담는다 ("09:00"). 1일 근로시간·휴게시간·주 소정근로시간은
 *    백엔드 property가 계산하므로 프론트에서 만들지 않는다.
 */
export interface ContractTerms {
  // 1. 근로계약기간
  contract_start: ExtractedField;
  contract_end: ExtractedField;

  // 2. 근무장소
  workplace: ExtractedField;

  // 3. 업무의 내용
  job_description: ExtractedField;

  // 4. 소정근로시간 — 시각
  work_start_time: ExtractedField;
  work_end_time: ExtractedField;
  break_start_time: ExtractedField;
  break_end_time: ExtractedField;

  // 5. 근무일 / 휴일
  work_days_per_week: ExtractedField;
  weekly_holiday_day: ExtractedField;

  // 6. 임금
  wage_type: ExtractedField;
  wage_amount: ExtractedField;
  has_bonus: ExtractedField;
  other_allowance: ExtractedField;
  payday: ExtractedField;
  payment_method: ExtractedField;

  // 당사자
  employer_business_name: ExtractedField;
  employer_phone: ExtractedField;
  employer_address: ExtractedField;
  employer_name: ExtractedField;
  worker_address: ExtractedField;
  worker_contact: ExtractedField;
  worker_name: ExtractedField;
}

// ============================================================
// 2. 검증 결과 — B의 출력
// ============================================================

export type CheckStatus =
  | "OK" // 기준 충족
  | "VIOLATION" // 법정 기준을 벗어남
  | "MISSING" // 필수 항목 누락
  | "UNKNOWN"; // 정보 부족으로 판정 불가

/** 판정 결과 하나. 100% 백엔드 코드 계산값이다. */
export interface CheckResult {
  /** 예: MINIMUM_WAGE, WEEKLY_HOLIDAY, BREAK_TIME */
  code: string;
  /** 화면 표시명. 예: '최저임금' */
  label: string;
  status: CheckStatus;
  /** 근거 조문. 예: '근로기준법 제55조' */
  legal_basis: string;
  /** 적용 기준 연도 */
  standard_year: number;
  /** 계산식. 예: '3일 × 6시간 = 주 18시간 ≥ 15시간' */
  calculation: string | null;
  /** 한계·조건 안내 */
  detail: string | null;
}

export interface ValidationReport {
  checks: CheckResult[];
  /** 예상 월급 (원). 코드 계산값 */
  estimated_monthly_pay: number | null;
  /** 최저임금 미달 시 월 차액 (원) */
  wage_shortfall: number | null;
}

// ============================================================
// 3. 문서 상태 — C가 관리 (모두싸인 상태와 대응)
// ============================================================

export type DocumentStatus =
  | "DRAFTING" // 작성 중 (아직 상대에게 안 보냄)
  | "REVIEW_REQUESTED" // 확인 요청됨 — "확인 전 초안" 워터마크
  | "TERMS_CONFIRMED" // 양쪽 조건 확인, 서명 전
  | "ON_PROCESSING" // 모두싸인 처리 중
  | "ON_GOING" // 서명 진행 중
  | "COMPLETED" // 체결 완료
  | "ABORTED" // 중단
  | "PROCESSING_FAILED"; // 처리 실패

export type EntryPath =
  | "PHOTO" // 경로 A — 계약서 사진 업로드
  | "MANUAL"; // 경로 B — 직접 입력 (구두계약 / OCR 실패)

// ============================================================
// 4. API 요청·응답
// ============================================================

export interface ValidateRequest {
  terms: ContractTerms;
  /** 사용자가 선택 입력한 생년월일. 계약서 추출값에는 포함하지 않는다. */
  worker_birth_date?: string | null;
}

export interface PreviewRequest {
  terms: ContractTerms;
  entry_path: EntryPath;
  include_verification: boolean;
}

export interface AnalyzeSignRequest {
  terms: ContractTerms;
  /** 검증 단계에서 선택 입력한 생년월일. 계약서/PDF에는 포함하지 않는다. */
  worker_birth_date?: string | null;
  worker_name: string;
  worker_email: string;
  employer_name: string;
  employer_email: string;
  entry_path: EntryPath;
  /** 위반이 남아 있어도 진행할지. 기본 false → 백엔드가 409로 막는다 */
  proceed_with_violations: boolean;
}

export interface AnalyzeSignResponse {
  document_id: string;
  status: DocumentStatus;
  report: ValidationReport;
  message: string;
}

/** analyze-sign 이 409로 막을 때 오는 본문 */
export interface ViolationBlocked {
  message: string;
  problems: string[];
  hint: string;
}

export interface SignStatusResponse {
  document_id: string;
  status: DocumentStatus;
  signed: number;
  total: number;
  download_url: string | null;
}
