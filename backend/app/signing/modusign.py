"""
모두싸인 연동 (C 담당)

핵심: anchor 기반 필드 배치를 쓴다.
PDF 안에 '근로자 서명', '사업주 서명' 텍스트가 반드시 있어야 한다.
"""

import base64

import httpx

from app.config import settings
from app.schemas import DocumentStatus

BASE_URL = "https://api.modusign.co.kr"

# PDF 템플릿에 반드시 포함되어야 하는 anchor 텍스트
#
# 표준근로계약서 원본은 서명란을 "(서명)"으로만 표기하지만,
# 같은 텍스트가 2번 등장하면 모두싸인이 매칭 개수만큼 필드를 만들어
# 근로자·사업주를 구분할 수 없다.
# 따라서 각 서명란에서 유일하게 등장하는 '대표자' / '성명'을 기준점으로 쓴다.
# (템플릿에서는 letter-spacing으로 자간만 넓혀 원본과 동일하게 보이게 한다)
ANCHOR_EMPLOYER = "대표자"
ANCHOR_WORKER = "성명"

# anchor 텍스트에서 오른쪽으로 이동시켜 "(서명)" 위치에 서명란을 배치한다.
# 문서 너비 대비 비율. PDF 레이아웃을 바꾸면 함께 조정할 것.
SIGN_OFFSET_X = 0.36
SIGN_OFFSET_Y = -0.005


class ModusignError(Exception):
    pass


def _auth_header() -> str:
    if not settings.modusign_configured:
        raise ModusignError("MODUSIGN_EMAIL / MODUSIGN_API_KEY 미설정")
    raw = f"{settings.modusign_email}:{settings.modusign_api_key}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _signature_field(anchor_text: str) -> dict:
    """anchor 기준 서명 필드. 좌표(x,y,page)와 anchor는 동시 사용 불가."""
    return {
        "type": "SIGNATURE",
        "required": True,
        "position": {
            "anchor": {
                "text": anchor_text,
                "offset": {"x": SIGN_OFFSET_X, "y": SIGN_OFFSET_Y},
            }
        },
        "size": {"width": 0.14, "height": 0.045},
    }


async def request_signature(
    pdf_bytes: bytes,
    title: str,
    worker_name: str,
    worker_email: str,
    employer_name: str,
    employer_email: str,
) -> dict:
    """
    서명 요청 발송. 근로자 → 사업주 순서로 서명한다.
    반환: {"id": 문서ID, "status": ...}
    """
    payload = {
        "title": title,
        "file": {
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "extension": "pdf",
        },
        "participants": [
            {
                "name": worker_name,
                "signingOrder": 1,
                "signingMethod": {"type": "EMAIL", "value": worker_email},
                "fields": [_signature_field(ANCHOR_WORKER)],
            },
            {
                "name": employer_name,
                "signingOrder": 2,
                "signingMethod": {"type": "EMAIL", "value": employer_email},
                "fields": [_signature_field(ANCHOR_EMPLOYER)],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{BASE_URL}/documents",
            json=payload,
            headers={
                "Authorization": _auth_header(),
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    if res.status_code >= 400:
        # anchor 텍스트를 못 찾으면 400 "Anchor text not found in PDF"
        raise ModusignError(f"HTTP {res.status_code}: {res.text}")

    return res.json()


async def get_document(document_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            f"{BASE_URL}/documents/{document_id}",
            headers={"Authorization": _auth_header()},
        )

    if res.status_code >= 400:
        raise ModusignError(f"HTTP {res.status_code}: {res.text}")

    return res.json()


def to_document_status(modusign_status: str) -> DocumentStatus:
    """모두싸인 상태 → 우리 상태. 값이 1:1이라 그대로 매핑된다."""
    try:
        return DocumentStatus(modusign_status)
    except ValueError:
        return DocumentStatus.PROCESSING_FAILED
