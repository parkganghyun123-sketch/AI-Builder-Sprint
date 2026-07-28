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
from app.signing.anchors import ANCHOR_EMPLOYER, ANCHOR_WORKER  # noqa: E402,F401

# 값의 출처는 anchors.py 한 곳이다. 여기에 복사해두지 말 것.
# (재수출은 기존 import 경로를 깨지 않기 위한 것)
from app.signing.anchors import (  # noqa: E402,F401
    SIGN_BOX_H,
    SIGN_BOX_W,
    SIGN_OFFSET_X,
    SIGN_OFFSET_Y,
)


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
        # SIGNATURE 필드 필수 항목. SIGN(서명) / STAMP(도장), 1~2개
        "signatureTypes": ["SIGN"],
        "position": {
            "anchor": {
                "text": anchor_text,
                "offset": {"x": SIGN_OFFSET_X, "y": SIGN_OFFSET_Y},
            }
        },
        "size": {"width": SIGN_BOX_W, "height": SIGN_BOX_H},
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
