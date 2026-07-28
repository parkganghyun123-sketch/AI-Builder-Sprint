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
        "signed": 0,
        "total": 2,  # 근로자 + 사업주
        "terms": body.terms.model_dump(),
        "entry_path": body.entry_path,
        "title": title,
    }

    return SignResponseBody(
        document_id=doc_id,
        status=status,
        message="서명 요청을 보냈습니다. 근로자부터 서명합니다.",
    )


async def reconcile(document_id: str) -> dict:
    """
    모두싸인 API를 조회해 우리 상태를 실제와 맞춘다.

    ⚠️ 상태를 쓰는 곳은 이 함수 하나뿐이다.

    웹훅 이벤트를 그대로 믿지 않는 이유:
      모두싸인 웹훅은 한 번 쏘고 마는 방식이라 재배포·크래시·네트워크 순단
      중에 도착한 이벤트는 그대로 유실된다. 실제로 컨테이너 재시작 중에
      document_started 를 놓친 사례가 있었다. 이벤트를 상태의 근거로 쓰면
      한 번 놓친 순간 영구히 틀어지고, 메모리 저장소라 복구 경로도 없다.

      대신 웹훅은 "지금 확인해보라"는 신호로만 쓰고 실제 값은 API에서 읽는다.
      이러면 이벤트를 놓쳐도 다음 이벤트나 폴링 시점에 자동으로 복구된다.
    """
    doc = await modusign.get_document(document_id)
    status = modusign.to_document_status(doc["status"])

    signed = len(doc.get("signings", []))
    total = len(doc.get("participants", []))

    record = _store.get(document_id)
    if record is not None:
        before = record.get("status")
        record["status"] = status
        record["signed"] = signed
        record["total"] = total
        if before != status:
            log.info("문서 %s 상태 갱신: %s → %s", document_id, before, status)

    return {
        "document_id": document_id,
        "status": status,
        "signed": signed,
        "total": total,
        # 다운로드 링크는 유효시간 10분이므로 저장하지 말고 그때그때 조회할 것
        "download_url": (
            doc.get("file", {}).get("downloadUrl")
            if status == DocumentStatus.COMPLETED
            else None
        ),
    }


@router.get("/contracts/{document_id}/status")
async def get_status(document_id: str) -> dict:
    """
    문서 상태 조회.

    웹훅이 유실됐더라도 이 조회 한 번으로 상태가 복구된다.
    """
    try:
        return await reconcile(document_id)
    except modusign.ModusignError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# 웹훅 이벤트 → 문서 상태 (API 조회가 실패했을 때의 대비책)
#
# ⚠️ 웹훅 페이로드에는 status 필드가 없다. 실제 수신 구조:
#      {"event": {"type": "document_started"},
#       "document": {"id": "...", "requester": {...}}}
#
# 평상시에는 reconcile()이 API에서 실제 상태를 읽으므로 이 표를 쓰지 않는다.
# 모두싸인 API가 일시적으로 죽었을 때만 근사치로 쓴다.
EVENT_TO_STATUS: dict[str, DocumentStatus] = {
    "document_started": DocumentStatus.ON_GOING,
    "document_signed": DocumentStatus.ON_GOING,  # 중간 서명자
    "document_all_signed": DocumentStatus.COMPLETED,  # 전원 서명 완료
    "document_rejected": DocumentStatus.ABORTED,
    "document_request_canceled": DocumentStatus.ABORTED,
    "document_signing_canceled": DocumentStatus.ON_GOING,  # 서명만 취소, 요청은 유지
}


@router.post("/webhooks/modusign")
async def webhook(request: Request) -> dict:
    """
    모두싸인 이벤트 수신.

    설정 위치: 모두싸인 설정 → Webhook
    구독 이벤트는 EVENT_TO_STATUS의 6가지만 켠다.

    이벤트 내용은 상태의 근거로 쓰지 않는다. "확인해보라"는 신호로만 받고,
    실제 상태는 reconcile()이 API에서 읽는다. 이유는 reconcile() 주석 참고.

    TODO: 서명 검증(MODUSIGN_WEBHOOK_SECRET) 추가 — 검증 방식 확인 필요
    """
    payload = await request.json()

    event_type = (payload.get("event") or {}).get("type")
    doc_id = (payload.get("document") or {}).get("id")

    log.info("모두싸인 webhook: event=%s document=%s", event_type, doc_id)

    if not doc_id or not event_type:
        log.warning("webhook 페이로드 형식이 예상과 다름: %s", payload)
        return {"received": True}

    if doc_id not in _store:
        # 스파이크 스크립트로 보낸 문서 등, 우리가 만들지 않은 건 조회하지 않는다
        log.info("저장소에 없는 문서: %s (event=%s)", doc_id, event_type)
        return {"received": True}

    try:
        result = await reconcile(doc_id)
        log.info("문서 %s 동기화 완료: %s (%s/%s 서명)",
                 doc_id, result["status"], result["signed"], result["total"])
    except modusign.ModusignError as e:
        # API가 일시적으로 죽은 경우. 이벤트 타입으로 근사치라도 반영해두고,
        # 다음 이벤트나 상태 조회 때 reconcile()이 정확한 값으로 덮어쓴다.
        fallback = EVENT_TO_STATUS.get(event_type)
        log.warning("문서 %s 동기화 실패(%s). 이벤트로 임시 반영: %s",
                    doc_id, e, fallback)
        if fallback is not None:
            _store[doc_id]["status"] = fallback

    # 모두싸인은 2xx를 기대한다. 여기서 500을 내면 웹훅이 실패로 집계되고
    # 반복되면 자동 비활성화될 수 있으므로, 실패해도 200을 준다.
    return {"received": True}


@router.get("/webhooks/modusign")
async def webhook_probe() -> dict:
    """
    모두싸인이 등록 시 URL 유효성을 GET으로 확인하는 경우가 있다.
    405가 뜨지 않도록 200을 돌려준다.
    """
    return {"status": "ok"}
