"""
계약서 PDF 생성 (C 담당)

고용노동부 표준근로계약서(기간의 정함이 있는 경우) 양식을 따른다.

⚠️ 모두싸인 anchor 제약
  - 생성된 PDF에 '근로자 서명', '사업주 서명' 텍스트가 반드시 있어야 한다
  - 텍스트 레이어가 있어야 한다 (이미지 렌더링 불가)
  - 한글 폰트가 임베딩되어야 한다
  WeasyPrint는 이 세 가지를 모두 만족한다.
"""

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.schemas import ContractTerms, WageType

TEMPLATE_DIR = Path(__file__).parent / "templates"

WAGE_TYPE_LABEL = {
    WageType.HOURLY.value: "시간급",
    WageType.DAILY.value: "일급",
    WageType.MONTHLY.value: "월급",
}

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _v(field, default: str = ""):
    """ExtractedField에서 값만 꺼낸다. 없으면 빈칸(양식의 밑줄이 그대로 보임)."""
    if field is None or field.value is None:
        return default
    return field.value


def _split_date(value) -> tuple[str, str, str]:
    """
    '2026년 8월 1일' / '2026-08-01' / '2026.08.01' → ('2026', '8', '1')
    표준양식은 년·월·일 칸이 분리되어 있다.
    """
    if not value:
        return "", "", ""
    s = str(value)
    for ch in ("년", "월", "일", "-", ".", "/"):
        s = s.replace(ch, " ")
    parts = [p for p in s.split() if p.isdigit()]
    if len(parts) >= 3:
        return parts[0], str(int(parts[1])), str(int(parts[2]))
    return str(value), "", ""


def _split_time(value) -> tuple[str, str]:
    """'09:00' / '9시 30분' → ('09', '00'). 표준양식은 시·분 칸이 분리되어 있다."""
    if not value:
        return "", ""
    s = str(value).replace("시", ":").replace("분", "").replace(" ", "")
    if ":" not in s:
        return str(value), ""
    h, _, m = s.partition(":")
    return h, (m or "00")


def render_contract_pdf(
    terms: ContractTerms,
    *,
    is_draft: bool = False,
    verification_note: str | None = None,
) -> bytes:
    """
    계약 조건 → PDF 바이트

    is_draft=True 이면 '확인 전 초안' 워터마크가 찍힌다.
    근로자가 혼자 입력한 문서(경로 B)는 반드시 True로 호출할 것.
    """
    today = date.today()
    amount = _v(terms.wage_amount, 0)

    start_y, start_m, start_d = _split_date(_v(terms.contract_start))
    end_y, end_m, end_d = _split_date(_v(terms.contract_end))
    ws_h, ws_m = _split_time(_v(terms.work_start_time))
    we_h, we_m = _split_time(_v(terms.work_end_time))
    bs_h, bs_m = _split_time(_v(terms.break_start_time))
    be_h, be_m = _split_time(_v(terms.break_end_time))

    context = {
        "is_draft": is_draft,
        "verification_note": verification_note,
        # 1. 근로계약기간 — 년·월·일 분리
        "start_y": start_y, "start_m": start_m, "start_d": start_d,
        "end_y": end_y, "end_m": end_m, "end_d": end_d,
        # 2~3
        "workplace": _v(terms.workplace),
        "job_description": _v(terms.job_description),
        # 4. 소정근로시간 — 시·분 분리
        "work_start_h": ws_h, "work_start_m": ws_m,
        "work_end_h": we_h, "work_end_m": we_m,
        "break_start_h": bs_h, "break_start_m": bs_m,
        "break_end_h": be_h, "break_end_m": be_m,
        # 5. 근무일/휴일
        "work_days_per_week": _v(terms.work_days_per_week),
        "weekly_holiday_day": _v(terms.weekly_holiday_day),
        # 6. 임금
        "wage_amount_formatted": f"{int(amount):,}" if amount else "",
        "has_bonus": bool(_v(terms.has_bonus, False)),
        "bonus_amount": "",
        "other_allowance": _v(terms.other_allowance),
        "payday": _v(terms.payday),
        "pay_direct": "직접" in str(_v(terms.payment_method, "")),
        # 당사자
        "employer_business_name": _v(terms.employer_business_name),
        "employer_phone": _v(terms.employer_phone),
        "employer_address": _v(terms.employer_address),
        "employer_name": _v(terms.employer_name),
        "worker_address": _v(terms.worker_address),
        "worker_contact": _v(terms.worker_contact),
        "worker_name": _v(terms.worker_name),
        # 서명일
        "signed_year": today.year,
        "signed_month": today.month,
        "signed_day": today.day,
    }

    html = _env.get_template("employment_contract.html").render(**context)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()


def verify_anchors(pdf_bytes: bytes) -> dict[str, bool]:
    """
    생성된 PDF에 anchor 텍스트가 들어갔는지 확인.

    ⚠️ PDF는 스트림이 압축되어 있어 단순 바이트 검색으로는 확인되지 않는다.
       정확한 검증은 pdftotext 등으로 텍스트를 추출해야 한다.
       False가 나와도 실패는 아니므로, PDF를 눈으로 확인할 것.
    """
    from app.signing.modusign import ANCHOR_EMPLOYER, ANCHOR_WORKER

    return {
        ANCHOR_WORKER: ANCHOR_WORKER.encode("utf-8") in pdf_bytes,
        ANCHOR_EMPLOYER: ANCHOR_EMPLOYER.encode("utf-8") in pdf_bytes,
    }
