"""
모두싸인 연동 (C 담당)

핵심: anchor 기반 필드 배치를 쓴다.
PDF 안에 '근로자 서명', '사업주 서명' 텍스트가 반드시 있어야 한다.
"""

import base64

import httpx

from app.config import settings
from app.schemas import DocumentStatus

# ⚠️ anchor 텍스트와 서명 박스 좌표는 app/signing/anchors.py 가 유일한 출처다.
#
#    이 파일에도 같은 상수를 따로 두었던 시기가 있었고, 두 값이 어긋났다.
#      anchors.py  (실측 보정)  x=-0.010  y=-0.246
#      modusign.py (자체 정의)  x= 0.028  y=-0.25   ← X는 부호까지 달랐다
#    실제 발송에 쓰인 쪽은 이 파일이었으므로, anchors.py 에 기록해 둔
#    "모두싸인이 세로로 22.5% 밀어놓는다"는 실측 보정이 반영되지 않았다.
#
#    좌표를 바꿔야 하면 anchors.py 만 고칠 것. 여기에 다시 정의하지 말 것.
from app.signing.anchors import (
    ANCHOR_EMPLOYER,
    ANCHOR_WORKER,
    SIGN_BOX_H,
    SIGN_BOX_W,
    SIGN_OFFSET_X,
    SIGN_OFFSET_Y,
)

BASE_URL = "https://api.modusign.co.kr"

__all__ = [
    "ANCHOR_EMPLOYER",
    "ANCHOR_WORKER",
    "ModusignError",
    "get_document",
    "request_signature",
    "to_document_status",
]


class ModusignError(Exception):
    pass


def _auth_header() -> str:
    if not settings.modusign_configured:
        raise ModusignError("MODUSIGN_EMAIL / MODUSIGN_API_KEY 미설정")
    raw = f"{settings.modusign_email}:{settings.modusign_api_key}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _raise_for_status(res: httpx.Response, what: str) -> None:
    """
    실패 응답을 ModusignError 로 바꾼다.

    ⚠️ 응답 본문(res.text)을 예외 메시지에 담지 않는다.
       본문에는 문서 제목·참여자 이메일 등 계약 관련 정보가 들어올 수 있고,
       예외 메시지는 상위에서 로그로 흘러갈 수 있다.
       AGENTS.md: "API 키, 계약서 내용, 개인정보를 로그에 남기지 않습니다."

       진단이 필요하면 상태 코드로 시작할 것.
       anchor 텍스트를 못 찾으면 400 "Anchor text not found in PDF" 가 온다.
    """
    if res.status_code >= 400:
        raise ModusignError(f"{what} 실패 (HTTP {res.status_code})")


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
    *,
    employer_first: bool = False,
) -> dict:
    """
    서명 요청 발송.

    반환: {"id": 문서ID, "status": ...}

    --- 서명 순서 ---

    ``employer_first=False`` (기본): 근로자 → 사업주
        근로자가 만든 문서다. 경로 A·B. 근로자가 먼저 서명하고
        사업주에게 확인·서명을 요청한다.

    ``employer_first=True``: 사업주 → 근로자
        사업주가 만든 문서다(경로 C). 문서를 만든 쪽이 먼저 서명하고
        상대에게 보내는 것이 계약 관행이고, 근로자가 마지막에 서명해야
        조건을 확인한 뒤 결정할 수 있다.

    ⚠️ 순서만 바꾼다. anchor 텍스트와 참여자의 매핑은 바꾸지 않는다.
       ``(근로자 서명)`` 자리에는 항상 근로자가, ``(사업주 서명)`` 자리에는
       항상 사업주가 들어간다. 이걸 섞으면 서명란이 뒤바뀐 계약서가 나간다.
    """
    worker = {
        "name": worker_name,
        "signingOrder": 2 if employer_first else 1,
        "signingMethod": {"type": "EMAIL", "value": worker_email},
        "fields": [_signature_field(ANCHOR_WORKER)],
    }
    employer = {
        "name": employer_name,
        "signingOrder": 1 if employer_first else 2,
        "signingMethod": {"type": "EMAIL", "value": employer_email},
        "fields": [_signature_field(ANCHOR_EMPLOYER)],
    }

    payload = {
        "title": title,
        "file": {
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "extension": "pdf",
        },
        # 배열 순서와 무관하게 signingOrder 가 순서를 정하지만,
        # 사람이 페이로드를 읽을 때 헷갈리지 않도록 순서대로 담는다.
        "participants": [employer, worker] if employer_first else [worker, employer],
    }

    # ⚠️ 인증 헤더를 먼저 만든다.
    #    미설정이면 ModusignError 가 여기서 나야 한다. try 안에서 만들면
    #    아래 except httpx.HTTPError 와 섞여 원인을 구분하기 어려워진다.
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{BASE_URL}/documents", json=payload, headers=headers
            )
    except httpx.HTTPError:
        # 타임아웃·DNS 실패·연결 끊김.
        #
        # ⚠️ 이 예외를 흘리면 호출부(ModusignError 만 잡는다)를 지나쳐
        #    500 이 나간다. 프론트엔드는 500을 "서버 오류"로 안내하는데
        #    실제로는 외부 연동 실패이므로 502 로 알려야 한다.
        #
        #    httpx 원본 메시지에는 요청 URL 등 외부 요청 정보가 포함될 수
        #    있어 전달하지 않는다.
        raise ModusignError("모두싸인 서명 요청 연결 실패") from None

    _raise_for_status(res, "모두싸인 서명 요청")

    try:
        return res.json()
    except ValueError:
        # JSON 디코더의 원본 메시지에는 응답 본문 일부가 포함될 수 있다.
        raise ModusignError("모두싸인 서명 요청 응답 검증 실패") from None


async def get_document(document_id: str) -> dict:
    headers = {"Authorization": _auth_header()}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                f"{BASE_URL}/documents/{document_id}", headers=headers
            )
    except httpx.HTTPError:
        raise ModusignError("모두싸인 문서 조회 연결 실패") from None

    _raise_for_status(res, "모두싸인 문서 조회")

    try:
        return res.json()
    except ValueError:
        raise ModusignError("모두싸인 문서 조회 응답 검증 실패") from None


def to_document_status(modusign_status: str) -> DocumentStatus:
    """모두싸인 상태 → 우리 상태. 값이 1:1이라 그대로 매핑된다."""
    try:
        return DocumentStatus(modusign_status)
    except ValueError:
        return DocumentStatus.PROCESSING_FAILED
