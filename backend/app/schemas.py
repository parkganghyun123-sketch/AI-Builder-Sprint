"""
단일 진실 공급원 (Single Source of Truth)

A(AI 추출)와 B(검증 엔진)는 이 파일만 보고 작업한다.
변경 시 반드시 상대 담당자에게 알릴 것.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

# ============================================================
# 1. 계약 조건 — A의 출력 = B의 입력
# ============================================================


class Confidence(str, Enum):
    """AI 추출 신뢰도. LOW면 화면에서 사용자 확인을 강조한다."""

    HIGH = "HIGH"
    LOW = "LOW"
    NOT_FOUND = "NOT_FOUND"


class ExtractedField(BaseModel):
    """추출된 값 하나 + 근거"""

    value: str | int | None = None
    confidence: Confidence = Confidence.NOT_FOUND
    source_text: str | None = Field(
        default=None, description="계약서 원문 중 이 값의 근거가 된 부분"
    )


class WageType(str, Enum):
    """표준근로계약서 6번 '월(일, 시간)급'"""

    HOURLY = "HOURLY"  # 시간급
    DAILY = "DAILY"  # 일급
    MONTHLY = "MONTHLY"  # 월급


class ContractTerms(BaseModel):
    """
    계약 조건. 고용노동부 표준근로계약서(기간의 정함이 있는 경우) 항목을 따른다.
    두 경로가 모두 이 형식을 만든다.
      - 경로 A: 사진 → Document Parse → Information Extract
      - 경로 B: 사용자가 폼에 직접 입력

    필드명 옆 번호는 표준근로계약서의 항목 번호.
    """

    # 1. 근로계약기간
    contract_start: ExtractedField
    contract_end: ExtractedField

    # 2. 근무장소
    workplace: ExtractedField

    # 3. 업무의 내용
    job_description: ExtractedField

    # 4. 소정근로시간 — 시각으로 기재된다 ("09:00", "15:00")
    work_start_time: ExtractedField  # 시업 시각
    work_end_time: ExtractedField  # 종업 시각
    break_start_time: ExtractedField  # 휴게 시작 시각
    break_end_time: ExtractedField  # 휴게 종료 시각

    # 5. 근무일/휴일
    work_days_per_week: ExtractedField  # 주 ○일 근무
    weekly_holiday_day: ExtractedField  # 주휴일 매주 ○요일 (없으면 누락)

    # 6. 임금
    wage_type: ExtractedField  # WageType 값
    wage_amount: ExtractedField  # 금액 (원)
    has_bonus: ExtractedField  # 상여금 있음/없음
    other_allowance: ExtractedField  # 기타급여(제수당)
    payday: ExtractedField  # 임금지급일
    payment_method: ExtractedField  # 지급방법

    # 당사자
    employer_business_name: ExtractedField  # 사업체명
    employer_phone: ExtractedField = ExtractedField()  # 전화
    employer_address: ExtractedField
    employer_name: ExtractedField  # 대표자
    worker_address: ExtractedField
    worker_contact: ExtractedField
    worker_name: ExtractedField

    # ---------------------------------------------------------- 파생값
    # ⚠️ 아래는 모두 코드 계산이다. LLM이 만들지 않는다.

    @staticmethod
    def _to_minutes(hhmm: str | int | None) -> int | None:
        """'09:00' 또는 '9시 30분' → 분 단위 정수"""
        if hhmm is None:
            return None
        s = str(hhmm).replace("시", ":").replace("분", "").strip()
        s = s.replace(" ", "")
        if ":" not in s:
            return None
        try:
            h, m = s.split(":")[:2]
            return int(h) * 60 + int(m or 0)
        except (ValueError, TypeError):
            return None

    @property
    def break_minutes(self) -> int | None:
        """휴게시간 (분). 시각 범위에서 계산."""
        start = self._to_minutes(self.break_start_time.value)
        end = self._to_minutes(self.break_end_time.value)
        if start is None or end is None:
            return None
        return max(0, end - start)

    @property
    def hours_per_day(self) -> float | None:
        """1일 소정근로시간. 재실시간에서 휴게를 뺀 값."""
        start = self._to_minutes(self.work_start_time.value)
        end = self._to_minutes(self.work_end_time.value)
        if start is None or end is None:
            return None
        total = end - start
        if total <= 0:
            return None
        return (total - (self.break_minutes or 0)) / 60

    @property
    def weekly_hours(self) -> float | None:
        """주 소정근로시간. 주휴수당 15시간 요건 판정에 사용."""
        days = self.work_days_per_week.value
        per_day = self.hours_per_day
        if days is None or per_day is None:
            return None
        return float(days) * per_day

    @property
    def hourly_wage(self) -> int | None:
        """
        시간급 환산. 최저임금 비교에 사용.
        ⚠️ 월급→시급 환산은 소정근로시간 산정 방식에 따라 달라진다.
           MVP에서는 시간급으로 기재된 경우만 판정하고,
           월급·일급은 UNKNOWN 처리한다. (외부 조사 필요)
        """
        if self.wage_type.value != WageType.HOURLY.value:
            return None
        try:
            return int(self.wage_amount.value)
        except (TypeError, ValueError):
            return None


# ============================================================
# 2. 검증 결과 — B의 출력
# ============================================================


class CheckStatus(str, Enum):
    OK = "OK"  # 기준 충족
    VIOLATION = "VIOLATION"  # 법정 기준 미달
    MISSING = "MISSING"  # 필수 항목 누락
    UNKNOWN = "UNKNOWN"  # 정보 부족으로 판정 불가


class CheckResult(BaseModel):
    """
    판정 결과 하나.
    ⚠️ 이 값은 100% 코드가 계산한다. LLM이 만들지 않는다.
    """

    code: str = Field(description="예: MINIMUM_WAGE, WEEKLY_HOLIDAY, BREAK_TIME")
    label: str = Field(description="화면 표시명. 예: '최저임금'")
    status: CheckStatus
    legal_basis: str = Field(description="근거 조문. 예: '근로기준법 제55조'")
    standard_year: int = Field(default=2026, description="적용 기준 연도")
    calculation: str | None = Field(
        default=None, description="계산식. 예: '3일 × 6시간 = 주 18시간 ≥ 15시간'"
    )
    detail: str | None = Field(default=None, description="한계·조건 안내")


class ValidationReport(BaseModel):
    """검증 전체 결과"""

    checks: list[CheckResult]
    estimated_monthly_pay: int | None = Field(
        default=None, description="예상 월급 (원). 코드 계산값"
    )
    wage_shortfall: int | None = Field(
        default=None, description="최저임금 미달 시 월 차액 (원)"
    )

    @property
    def has_problem(self) -> bool:
        return any(
            c.status in (CheckStatus.VIOLATION, CheckStatus.MISSING)
            for c in self.checks
        )


# ============================================================
# 3. 계약 문서 상태 — C가 관리
# ============================================================


class DocumentStatus(str, Enum):
    """
    모두싸인 상태와 1:1 대응 (DRAFT 이전 단계만 우리가 추가)
    자세한 화면 문구는 README '문서 상태' 표 참고
    """

    DRAFTING = "DRAFTING"  # 작성 중 (아직 상대에게 안 보냄)
    REVIEW_REQUESTED = "REVIEW_REQUESTED"  # 확인 요청됨 — "확인 전 초안" 워터마크
    TERMS_CONFIRMED = "TERMS_CONFIRMED"  # 양쪽 조건 확인, 서명 전
    ON_PROCESSING = "ON_PROCESSING"  # 모두싸인 처리 중
    ON_GOING = "ON_GOING"  # 서명 진행 중
    COMPLETED = "COMPLETED"  # 체결 완료
    ABORTED = "ABORTED"  # 중단
    PROCESSING_FAILED = "PROCESSING_FAILED"  # 처리 실패


class EntryPath(str, Enum):
    PHOTO = "PHOTO"  # 경로 A — 계약서 사진 업로드
    MANUAL = "MANUAL"  # 경로 B — 직접 입력 (구두계약 / OCR 실패)


# ============================================================
# 4. API 요청·응답
# ============================================================


class SignRequest(BaseModel):
    worker_name: str
    worker_email: str
    employer_name: str
    employer_email: str


class SignResponse(BaseModel):
    document_id: str = Field(description="모두싸인 문서 ID")
    status: DocumentStatus
