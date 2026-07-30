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
// 2-2. 입력값 유효성 + 진행 차단 — severity.py 대응
// ============================================================

/** error(차단) / warning(진행 가능) / info(참고) */
export type ValidationSeverity = "error" | "warning" | "info";

/**
 * 화면에 그대로 뿌리는 이슈 하나. 문구를 프론트에서 새로 만들지 않는다.
 * reason·fix 를 그대로 쓰고, field 로 해당 입력란에 포커스를 옮긴다.
 */
export interface ValidationIssue {
  field: string;
  label: string;
  severity: ValidationSeverity;
  /** 문제가 된 현재 값 */
  value: string | number | null;
  /** 왜 문제인가 */
  reason: string;
  /** 어떻게 고치나 */
  fix: string;
  /** 다음 단계를 막는가 */
  blocks: boolean;
  /** 어느 화면에서 고치나 */
  step: string;
  /** input(값 자체) / legal(법정 기준) */
  source: string;
}

/**
 * 진행 차단 판정. 프론트는 이 응답만 보고 "다음" 버튼을 켜고 끈다.
 * ⚠️ 같은 규칙을 화면에 복사하지 말 것. 두 곳에 두면 반드시 어긋난다.
 */
export interface ValidationState {
  can_proceed: boolean;
  blocking_fields: string[];
  counts: { error: number; warning: number; info: number };
  issues: ValidationIssue[];
}

/**
 * analyze-sign 이 성립하지 않는 값(임금 0원 등)으로 문서 생성 자체를
 * 거부할 때(422). ValidationState 의 issues 와 같은 형태다.
 */
export interface InvalidContractValues {
  code: "INVALID_CONTRACT_VALUES";
  message: string;
  blocking_fields: string[];
  issues: ValidationIssue[];
}

// ============================================================
// 2-3. "말 꺼내기" 문구 — bridge/templates.py 대응
// ============================================================

/**
 * 판정 결과를 사장님께 보낼 문의 메시지로 바꾼 것.
 *
 * ⚠️ 문장의 숫자는 백엔드가 ValidationReport 에서 그대로 꺼내 쓰고,
 *    반환 전에 app/bridge/numbers.py 로 한 번 더 대조한다.
 *    LLM 이 만들지 않으므로 환각이 구조적으로 불가능하다.
 *
 * ⚠️ numbers_verified 가 false 면 화면에 표시하지 말 것.
 *    대조에 실패했다는 뜻이고, 근거 없는 숫자를 사용자가 사장님에게
 *    보내면 이 기능의 신뢰가 한 번에 무너진다.
 */
export interface OwnerMessage {
  /** 전체 메시지. 문제가 없으면 null */
  message: string | null;
  /** 문제 항목별 한 줄 문장 */
  lines: string[];
  /** 문장의 숫자가 판정 결과와 일치하는가 */
  numbers_verified: boolean;
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

/**
 * 조건이 어디서 왔는가. 문서의 출처 표시와 서명 순서를 결정한다.
 * backend/app/schemas.py EntryPath 와 1:1.
 */
export type EntryPath =
  | "PHOTO" // 경로 A — 근로자가 받은 계약서 사진
  | "MANUAL" // 경로 B — 근로자가 직접 입력 (구두계약 / OCR 실패)
  | "EMPLOYER"; // 경로 C — 사업주가 계약서를 작성

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
  /**
   * 사용자가 "값이 맞다"고 확인한 항목의 키 목록.
   * review-items 의 must_confirm 을 여기에 담아 보내야 백엔드가 서명을 진행한다.
   * 비우면 백엔드가 409(UNCONFIRMED_FIELDS)로 막는다.
   */
  confirmed_fields: string[];
  /** 위반이 남아 있어도 진행할지. 기본 false → 백엔드가 409로 막는다 */
  proceed_with_violations: boolean;
}

// ============================================================
// 4-2. 확인이 필요한 항목 — review-items
// ============================================================

/** 서명 전에 확인받아야 하는 우선순위 */
export type ReviewPriority = "high" | "medium" | "low";

/** 확인이 필요한 항목 하나. 백엔드 build_review_items 와 대응. */
export interface ReviewItem {
  /** ContractTerms 키. confirmed_fields 에 담아 보낼 값. */
  field: string;
  label: string;
  value: string | number | null;
  confidence: Confidence;
  source_text: string | null;
  priority: ReviewPriority;
  /** 왜 확인이 필요한지 */
  reasons: string[];
  /** 판정에 쓰이는 값인가 */
  affects_judgment: boolean;
  /** 계약서에 인쇄되는 신원 정보인가 */
  printed_on_contract: boolean;
}

export interface ReviewItemsResponse {
  items: ReviewItem[];
  /** priority=high — 서명 전 반드시 확인해야 하는 필드 키 */
  must_confirm: string[];
}

/**
 * analyze-sign 이 409로 되돌릴 때 오는 본문 (확인 필요·이름 불일치 등).
 * 위반(proceed 가능)과 달리 사용자가 돌아가서 고쳐야 한다.
 */
export interface SignBlocked {
  code?: string;
  message: string;
  hint: string;
  /** 확인/수정이 필요한 항목 라벨 */
  fields?: string[];
  /**
   * NAME_MISMATCH — 계약서에서 읽은 이름과 서명 요청에 입력한 이름이 다른 항목들.
   * 어느 쪽이 맞는지 코드가 고르지 않는다(contracts.py:_name_conflicts).
   */
  conflicts?: {
    field: string;
    label: string;
    on_contract: string;
    typed: string;
  }[];
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

// ============================================================
// 5. 로그인 — backend/app/routers/auth.py 대응
// ============================================================

export type UserRole = "WORKER" | "EMPLOYER";

export interface Me {
  user_id: string;
  nickname: string;
  role: UserRole;
}

/** 보관함 목록 항목. GET /contracts — 다운로드 링크는 없다(유효시간 10분). */
export interface ArchiveItem {
  document_id: string;
  title: string;
  status: DocumentStatus;
  signed: number;
  total: number;
  entry_path: EntryPath;
  created_at: string;
}
