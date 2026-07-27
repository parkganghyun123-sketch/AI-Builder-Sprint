"""
서명 라우터 (C 담당)

  POST /contracts/sign          계약 조건 → PDF 생성 → 서명 요청 발송
  GET  /contracts/{id}/status   문서 상태 조회
  POST /webhooks/modusign       모두싸인 상태 변경 수신

⚠️ 저장소는 아직 메모리다. DB 붙이면 store를 교체할 것.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.pdf.generator import render_contract_pdf
from app.schemas import ContractTerms, DocumentStatus, EntryPath
from app.signing import modusign

log = logging.getLogger(__name__)
router = APIRouter()

# 임시 저장소 — DB 연결 전까지 사용
_store: dict[str, dict] = {}


class SignRequestBody(BaseModel):
    terms: ContractTerms
    worker_name: str
    worker_email: str
    employer_name: str
    employer_email: str
    entry_path: EntryPath = EntryPath.PHOTO


class SignResponseBody(BaseModel):
    document_id: str
    status: DocumentStatus
    message: str


@router.post("/contracts/sign", response_model=SignResponseBody)
async def create_and_send(body: SignRequestBody) -> SignResponseBody:
    """
    계약 조건을 받아 PDF를 만들고 서명 요청을 보낸다.
    근로자 → 사업주 순서로 서명한다.
    """
    # 경로 B(구두계약)는 근로자가 혼자 입력한 것이므로 초안 표시가 필요하다.
    # 다만 서명 단계까지 왔다면 양측이 조건을 확인한 것으로 보고 초안 표시를 뗀다.
    pdf = render_contract_pdf(body.terms, is_draft=False)

    title = f"근로계약서_{body.worker_name}_{body.employer_name}"

    try:
        result = await modusign.request_signature(
            pdf_bytes=pdf,
            title=title,
            worker_name=body.worker_name,
            worker_email=body.worker_email,
            employer_name=body.employer_name,
            employer_email=body.employer_email,
        )
    except modusign.ModusignError as e:
        log.error("모두싸인 서명 요청 실패: %s", e)
        # anchor 텍스트 미발견이 가장 흔한 원인
        raise HTTPException(status_code=502, detail=f"서명 요청 실패: {e}") from e

    doc_id = result["id"]
    status = modusign.to_document_status(result["status"])

    _store[doc_id] = {
        "status": status,
        "terms": body.terms.model_dump(),
        "entry_path": body.entry_path,
        "title": title,
    }

    return SignResponseBody(
        document_id=doc_id,
        status=status,
        message="서명 요청을 보냈습니다. 근로자부터 서명합니다.",
    )


@router.get("/contracts/{document_id}/status")
async def get_status(document_id: str) -> dict:
    """
    문서 상태 조회.
    Webhook이 안 붙은 동안에는 프론트가 이걸 폴링한다.
    """
    try:
        doc = await modusign.get_document(document_id)
    except modusign.ModusignError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    status = modusign.to_document_status(doc["status"])
    if document_id in _store:
        _store[document_id]["status"] = status

    signed_count = len(doc.get("signings", []))
    total = len(doc.get("participants", []))

    return {
        "document_id": document_id,
        "status": status,
        "signed": signed_count,
        "total": total,
        # 다운로드 링크는 유효시간 10분이므로 저장하지 말고 그때그때 조회할 것
        "download_url": (
            doc.get("file", {}).get("downloadUrl")
            if status == DocumentStatus.COMPLETED
            else None
        ),
    }


@router.post("/webhooks/modusign")
async def webhook(request: Request) -> dict:
    """
    모두싸인 상태 변경 수신.

    설정 위치: 모두싸인 설정 → 워크스페이스 관리 → Webhook
    로컬 개발 시 ngrok 등으로 외부 접근 URL이 필요하다.

    TODO: 서명 검증(MODUSIGN_WEBHOOK_SECRET) 추가 — 검증 방식 확인 필요
    """
    payload = await request.json()
    log.info("모두싸인 webhook: %s", payload)

    doc = payload.get("document") or payload
    doc_id = doc.get("id")
    raw_status = doc.get("status")

    if doc_id and raw_status:
        status = modusign.to_document_status(raw_status)
        if doc_id in _store:
            _store[doc_id]["status"] = status
        log.info("문서 %s 상태 → %s", doc_id, status)

    # 모두싸인은 2xx를 기대한다. 실패해도 200을 주고 로그로 처리할 것
    return {"received": True}
