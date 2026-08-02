"""
서명 라우터 (C 담당)

  POST /contracts/sign          계약 조건 → PDF 생성 → 서명 요청 발송
  GET  /contracts/{id}/status   문서 상태 조회
  POST /webhooks/modusign       모두싸인 상태 변경 수신

⚠️ 저장소는 아직 메모리다. DB 붙이면 store를 교체할 것.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.auth.deps import CurrentUser
from app.config import settings
from app.schemas import (
    ContractTerms,
    DocumentStatus,
    EmailAddress,
    EntryPath,
    ExtractedField,
    PartyName,
)
from app.signing import modusign
from app.store import get_store

log = logging.getLogger(__name__)
router = APIRouter()


def render_contract_pdf(*args, **kwargs) -> bytes:
    """PDF 발송 시점에만 WeasyPrint를 불러 로컬 검증 서버를 살린다."""
    try:
        from app.pdf.generator import render_contract_pdf as render
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="지금은 계약서 파일을 만들 수 없어요. 조건 확인과 상담은 그대로 쓸 수 있어요.",
        ) from exc
    return render(*args, **kwargs)

async def remember_document(
    document_id: str,
    *,
    status: DocumentStatus,
    entry_path: EntryPath,
    title: str,
    total: int = 2,  # 근로자 + 사업주
    owner_id: str | None = None,
) -> None:
    """
    발송한 문서를 이력에 남긴다.

    ⚠️ 서명 요청을 보내는 **모든** 경로가 이 함수를 불러야 한다.

    한동안 /contracts/sign 만 저장하고 /contracts/analyze-sign 은 저장하지
    않았다. 그런데 화면이 실제로 쓰는 건 analyze-sign 이다. 결과적으로
    webhook() 의 "저장소에 없으면 무시" 분기에서 모든 이벤트가 조용히
    버려졌고, 상태는 사용자가 /complete 화면을 열어 폴링하는 동안에만
    갱신됐다. 화면을 닫으면 갱신이 멈췄다.

    저장 대상은 문서 식별자와 진행 상태뿐이다.
    계약 조건·이름·이메일은 남기지 않는다 — 이력 조회에 필요하지 않고,
    남기면 그 순간부터 보관 기간과 삭제 책임이 생긴다.

    ⚠️ 이력 기록이 실패해도 서명 요청 자체는 이미 발송됐다.
       여기서 예외를 올리면 사용자는 "실패했다"고 보는데 상대방에게는
       메일이 가 있는, 가장 혼란스러운 상태가 된다.
       그래서 실패를 로그로만 남기고 응답은 성공으로 돌려준다.
       상태는 /contracts/{id}/status 가 모두싸인에서 직접 읽으므로
       이력이 없어도 사용자 흐름은 이어진다.
    """
    try:
        await get_store().remember(
            document_id,
            status=status,
            entry_path=entry_path,
            title=title,
            total=total,
            owner_id=owner_id,
        )
    except Exception as error:
        log.error(
            "문서 이력 기록 실패 (서명 요청은 이미 발송됨): document=%s error_type=%s",
            document_id,
            type(error).__name__,
        )


def _minimize_contact_fields(terms: ContractTerms) -> ContractTerms:
    """서명 요청서에 불필요한 전화·주소·연락처를 보존하지 않는다."""
    return terms.model_copy(
        update={
            "employer_phone": ExtractedField(),
            "employer_address": ExtractedField(),
            "worker_address": ExtractedField(),
            "worker_contact": ExtractedField(),
        }
    )


class SignRequestBody(BaseModel):
    terms: ContractTerms
    worker_name: PartyName
    worker_email: EmailAddress
    employer_name: PartyName
    employer_email: EmailAddress
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
    # 폼 제출이나 발송만으로 양쪽의 조건 확인 또는 체결 완료를 추정하지 않는다.
    terms = _minimize_contact_fields(body.terms)
    pdf = render_contract_pdf(terms, is_draft=True)

    title = "근로조건 확인 요청서"

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
        log.error("모두싸인 서명 요청 실패: error_type=%s reason=%s", type(e).__name__, e)
        raise HTTPException(
            status_code=502,
            detail="지금은 서명 요청을 보낼 수 없어요. 잠시 뒤 다시 시도해 주세요.",
        ) from e

    doc_id = result["id"]
    status = modusign.to_document_status(result["status"])

    await remember_document(
        doc_id,
        status=status,
        entry_path=body.entry_path,
        title=title,
    )

    return SignResponseBody(
        document_id=doc_id,
        status=status,
        message=(
            "확인 요청서를 보냈어요. "
            "체결 완료는 양쪽이 서명한 게 확인되면 알려드릴게요."
        ),
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

    record = await get_store().get(document_id)

    # 조회 자체를 항상 남긴다.
    # 예전에는 "저장소에 있고 + 상태가 바뀐" 경우에만 찍어서,
    # 재배포로 저장소가 빈 뒤에는 동기화가 도는지 로그로 확인할 수 없었다.
    log.info(
        "문서 %s 동기화: %s (%s/%s 서명)%s",
        document_id,
        status,
        signed,
        total,
        "" if record is not None else "  [이력에 없음 — 외부 문서이거나 기록 실패]",
    )

    if record is not None:
        before = record.get("status")
        await get_store().update_progress(
            document_id, status=status, signed=signed, total=total
        )
        if before != status:
            log.info("문서 %s 상태 변경: %s → %s", document_id, before, status)

    return {
        "document_id": document_id,
        "title": doc.get("title") or "근로계약서",
        "status": status,
        "signed": signed,
        "total": total,
        # 누가 누구와 맺은 계약인가.
        #
        # ⚠️ 저장하지 않고 **열 때마다 제공자에서 읽는다.**
        #    보관함에 이름이 없으면 "무슨 계약인지 알 수 없는 목록"이 되는데,
        #    그렇다고 우리 DB에 이름·이메일을 쌓으면 보관 기간과 삭제 책임이
        #    생긴다. 원본은 모두싸인이 갖고 있으므로 우리는 가리키기만 한다.
        #    (다운로드 링크를 저장하지 않는 것과 같은 이유다)
        "participants": _participants(doc),
        # 다운로드 링크는 유효시간 10분이므로 저장하지 말고 그때그때 조회할 것
        "download_url": (
            doc.get("file", {}).get("downloadUrl")
            if status == DocumentStatus.COMPLETED
            else None
        ),
    }


def _participants(doc: dict) -> list[dict]:
    """
    문서 참여자와 서명 여부.

    ⚠️ 제공자 응답 구조가 바뀌어도 상태 조회 전체가 깨지지 않도록
       모든 필드를 방어적으로 읽는다. 이름을 못 읽으면 순서로 대신한다 —
       빈 목록을 주는 것보다 "1번 서명자"라도 보여주는 편이 낫다.
    """
    signed_ids = {
        str(s.get("participantId"))
        for s in doc.get("signings") or []
        if isinstance(s, dict) and s.get("participantId") is not None
    }

    result: list[dict] = []
    for index, participant in enumerate(doc.get("participants") or [], start=1):
        if not isinstance(participant, dict):
            continue
        participant_id = str(participant.get("id", ""))
        result.append(
            {
                "name": (participant.get("name") or "").strip()
                or f"{index}번 서명자",
                "order": participant.get("signingOrder", index),
                # signings 에 없으면 아직 서명 전
                "signed": participant_id in signed_ids,
            }
        )

    result.sort(key=lambda p: p["order"])
    return result


def _assert_owner(record: dict | None, user: dict) -> None:
    """
    남의 문서를 볼 수 없게 한다.

    ⚠️ 403 이 아니라 404 를 낸다. 403 은 "그 문서는 존재하지만 네 것이
       아니다"를 알려주는 셈이라, 문서 ID 를 무작위로 넣어보며 존재 여부를
       알아낼 수 있다. 계약서의 존재 자체가 개인정보다.

    ⚠️ owner_id 가 없는 문서(로그인 도입 전에 만들어진 것)는 통과시킨다.
       지금은 서명 발송에 로그인이 필요하므로 새로 생기지 않는다.
       기존 문서를 조회 불가로 만들면 이미 서명 진행 중인 사람이
       상태를 볼 수 없게 된다.
    """
    if record is None:
        return  # 외부 문서. reconcile 이 제공자에서 직접 읽는다.

    owner_id = record.get("owner_id")
    if owner_id and owner_id != user["user_id"]:
        log.warning("다른 사용자의 문서 접근 시도 — 거부")
        raise HTTPException(
            status_code=404,
            # ⚠️ "권한이 없습니다"라고 쓰지 않는다. 그렇게 쓰면 "그 문서는
            #    존재한다"를 알려주는 셈이다. 계약서의 존재 자체가 개인정보다.
            detail="문서를 찾을 수 없어요. 보관함에서 다시 선택해 주세요.",
        )


class ArchiveItem(BaseModel):
    document_id: str
    title: str
    status: DocumentStatus
    signed: int
    total: int
    entry_path: EntryPath
    created_at: str
    # 아래 셋은 모두싸인에서 그때그때 읽어온다. 저장하지 않는다.
    participants: list[dict] = []
    download_url: str | None = None
    # 제공자 조회에 실패했는가. true 면 status·signed 는 마지막 저장값이다.
    stale: bool = False


# 목록을 열 때 제공자에 동시에 물어볼 문서 수.
#
# ⚠️ 무제한으로 열면 모두싸인 쿼터를 한 번에 태우고, 응답도 가장 느린
#    요청에 묶인다. 보관함은 최근 문서부터 보므로 앞쪽만 채워도 충분하다.
_DETAIL_CONCURRENCY = 5
_DETAIL_LIMIT = 20


async def _enrich(record: dict) -> ArchiveItem:
    """
    저장된 이력 한 건에 제공자 정보를 덧붙인다.

    ⚠️ 실패해도 목록에서 빠지지 않는다. 제공자가 잠깐 죽었다고
       "계약서가 사라진" 화면을 보여주면 안 된다.
       저장된 값으로 보여주고 stale=true 로 알린다.
    """
    base = {
        "document_id": record["document_id"],
        "title": record["title"],
        "status": record["status"],
        "signed": record.get("signed", 0),
        "total": record.get("total", 2),
        "entry_path": record["entry_path"],
        "created_at": record["created_at"].isoformat(),
    }

    try:
        doc = await modusign.get_document(record["document_id"])
    except Exception as error:
        # ⚠️ ModusignError 만 잡지 않는다. 응답 구조가 바뀌어 KeyError 가 나도
        #    보관함 전체가 500 이 되면 안 된다. 한 건의 실패는 한 건으로 끝난다.
        log.info(
            "보관함 항목 상세 조회 실패 — 저장값으로 표시: document=%s error_type=%s",
            record["document_id"],
            type(error).__name__,
        )
        return ArchiveItem(**base, stale=True)

    status = modusign.to_document_status(doc.get("status") or base["status"])
    return ArchiveItem(
        **{
            **base,
            "status": status,
            "signed": len(doc.get("signings") or []),
            "total": len(doc.get("participants") or []) or base["total"],
        },
        participants=_participants(doc),
        # 유효시간 10분. 목록을 연 시점부터 세므로 바로 누르면 받아진다.
        # 만료되면 화면이 "다시 조회" 버튼을 보여준다.
        download_url=(
            doc.get("file", {}).get("downloadUrl")
            if status == DocumentStatus.COMPLETED
            else None
        ),
    )


@router.get("/contracts", response_model=list[ArchiveItem])
async def list_my_documents(user: CurrentUser) -> list[ArchiveItem]:
    """
    내가 만든 문서 목록 (보관함).

    각 항목에 **누구와 맺었는지**와 **다운로드 링크**를 함께 담는다.

    ⚠️ 예전에는 저장된 상태만 돌려줬다. 그래서 보관함이 "체결 완료 · 날짜"만
       보이는 목록이었고, 실제로 문서를 받으려면 두 번 더 눌러야 했다.
       보관함이라면 여기서 바로 받을 수 있어야 한다.

    ⚠️ 그래도 이름과 링크를 저장하지는 않는다. 목록을 열 때 제공자에서
       읽는다. 우리 DB에 이름을 쌓으면 보관 기간과 삭제 책임이 생긴다.

    ⚠️ 동시 조회 수를 제한한다. 문서가 많아도 제공자 쿼터를 한꺼번에
       태우지 않는다. 앞쪽 문서만 상세를 채우고 나머지는 저장값을 쓴다.
    """
    records = await get_store().list_for_owner(user["user_id"])
    if not records:
        return []

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def enrich_bounded(record: dict) -> ArchiveItem:
        async with semaphore:
            return await _enrich(record)

    detailed = await asyncio.gather(
        *(enrich_bounded(r) for r in records[:_DETAIL_LIMIT])
    )

    # 상세를 채우지 않은 나머지는 저장값 그대로.
    rest = [
        ArchiveItem(
            document_id=r["document_id"],
            title=r["title"],
            status=r["status"],
            signed=r.get("signed", 0),
            total=r.get("total", 2),
            entry_path=r["entry_path"],
            created_at=r["created_at"].isoformat(),
            stale=True,
        )
        for r in records[_DETAIL_LIMIT:]
    ]
    return [*detailed, *rest]


@router.get("/contracts/{document_id}/status")
async def get_status(document_id: str, user: CurrentUser) -> dict:
    """
    문서 상태 조회.

    웹훅이 유실됐더라도 이 조회 한 번으로 상태가 복구된다.

    ⚠️ 로그인이 필요하다. 이 응답에는 체결 문서 다운로드 링크가 들어간다.
    """
    _assert_owner(await get_store().get(document_id), user)

    try:
        return await reconcile(document_id)
    except modusign.ModusignError as e:
        log.error(
            "서명 상태 조회 실패: document=%s error_type=%s reason=%s",
            document_id,
            type(e).__name__,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail="지금은 서명 상태를 확인할 수 없어요. 잠시 뒤 다시 시도해 주세요.",
        ) from e


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


class WebhookEvent(BaseModel):
    type: str | None = None


class WebhookDocument(BaseModel):
    id: str | None = None


class WebhookPayload(BaseModel):
    event: WebhookEvent | None = None
    document: WebhookDocument | None = None


def _check_token(token: str | None) -> None:
    """
    웹훅 호출자 확인.

    모두싸인은 웹훅 서명(HMAC) 기능을 제공하지 않는다.
    (워크스페이스 → Webhook 설정에 시크릿 항목이 없음)
    그래서 URL 경로에 무작위 토큰을 넣어 URL 자체를 비밀로 삼는다.

    토큰이 비어 있으면 검증을 건너뛴다 — 로컬 개발용.

    ⚠️ 존재 자체를 숨기기 위해 401이 아니라 404를 낸다.
    ⚠️ 타이밍 공격을 막기 위해 == 대신 compare_digest 를 쓴다.
    """
    expected = settings.webhook_path_token
    if not expected:
        return
    if not token or not hmac.compare_digest(token, expected):
        log.warning("웹훅 토큰 불일치 — 요청 거부")
        raise HTTPException(
            status_code=404,
            # ⚠️ "권한이 없습니다"라고 쓰지 않는다. 그렇게 쓰면 "그 문서는
            #    존재한다"를 알려주는 셈이다. 계약서의 존재 자체가 개인정보다.
            detail="문서를 찾을 수 없어요. 보관함에서 다시 선택해 주세요.",
        )


@router.post("/webhooks/modusign/{token}")
@router.post("/webhooks/modusign")
async def webhook(request: Request, token: str | None = None) -> dict:
    """
    모두싸인 이벤트 수신.

    설정 위치: 모두싸인 설정 → 워크스페이스 관리 → Webhook
    구독 이벤트는 EVENT_TO_STATUS의 6가지만 켠다.

    이벤트 내용은 상태의 근거로 쓰지 않는다. "확인해보라"는 신호로만 받고,
    실제 상태는 reconcile()이 API에서 읽는다. 이유는 reconcile() 주석 참고.
    따라서 웹훅을 위조해도 상태를 조작할 수는 없고,
    토큰은 엔드포인트 남용(쿼터 소모)을 막기 위한 것이다.
    """
    _check_token(token)

    try:
        payload = WebhookPayload.model_validate(await request.json())
    except (ValueError, ValidationError):
        log.warning("webhook 페이로드를 검증하지 못함")
        return {"received": True}

    event_type = payload.event.type if payload.event else None
    doc_id = payload.document.id if payload.document else None

    log.info("모두싸인 webhook: event=%s document=%s", event_type, doc_id)

    if not doc_id or not event_type:
        log.warning(
            "webhook 필수 식별자 누락: event=%s document=%s",
            event_type,
            doc_id,
        )
        return {"received": True}

    record = await get_store().get(doc_id)
    if record is None:
        # 스파이크 스크립트로 보낸 문서 등, 우리가 만들지 않은 건 조회하지 않는다.
        # 모두싸인 API 를 부르지 않으므로 쿼터도 쓰지 않는다.
        log.info("이력에 없는 문서: %s (event=%s)", doc_id, event_type)
        return {"received": True}

    try:
        await reconcile(doc_id)  # 로그는 reconcile 안에서 남긴다
    except modusign.ModusignError as e:
        # API가 일시적으로 죽은 경우. 이벤트 타입으로 근사치라도 반영해두고,
        # 다음 이벤트나 상태 조회 때 reconcile()이 정확한 값으로 덮어쓴다.
        fallback = EVENT_TO_STATUS.get(event_type)
        log.warning(
            "문서 %s 동기화 실패(error_type=%s). 이벤트로 임시 반영: %s",
            doc_id,
            type(e).__name__,
            fallback,
        )
        if fallback is not None:
            await get_store().update_progress(
                doc_id,
                status=fallback,
                # 서명 진행도는 이벤트로 알 수 없다. 지어내지 않고 기존 값을 둔다.
                signed=record.get("signed", 0),
                total=record.get("total", 2),
            )

    # 모두싸인은 2xx를 기대한다. 여기서 500을 내면 웹훅이 실패로 집계되고
    # 반복되면 자동 비활성화될 수 있으므로, 실패해도 200을 준다.
    return {"received": True}


@router.get("/webhooks/modusign/{token}")
@router.get("/webhooks/modusign")
async def webhook_probe(token: str | None = None) -> dict:
    """
    모두싸인이 등록 시 URL 유효성을 GET으로 확인하는 경우가 있다.
    405가 뜨지 않도록 200을 돌려준다.
    """
    _check_token(token)
    return {"status": "ok"}
