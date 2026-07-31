"""
계약서 추출 라우터 (A 담당)

  POST /contracts/extract         계약서 사진/PDF → ContractTerms
  POST /contracts/review-items    조건 → 확인이 필요한 항목 목록

⚠️ 여기서 나온 값은 AI 추출 직후의 값이다. 검증(/contracts/validate)에
   넘기기 전에 사용자가 화면에서 확인·수정해야 한다.
"""

import logging
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.ai.document_parse import DocumentParseError
from app.ai.extract import ExtractError, extract_contract_terms
from app.review.fields import build_review_items
from app.schemas import ContractTerms
from app.validation.entitlements import all_entitlements

log = logging.getLogger(__name__)
router = APIRouter()

# ------------------------------------------------------------ 업로드 제한
#
# ⚠️ 이 엔드포인트는 인증이 없고 배포 링크가 공개된다.
#    그리고 요청 한 번이 Upstage 유료 API를 두 번 호출한다
#    (Document Parse + Information Extract).
#
#    제한이 없으면 아무나 크레딧을 소진시킬 수 있고, 그러면
#    데모 당일에 서비스가 멈춘다. 실제로 막아야 하는 위험이다.
#
#    CORS는 브라우저만 막는다. curl 은 막지 못한다.
#    그래서 서버에서 크기와 형식을 직접 본다.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — 휴대폰 사진 1장이면 충분하다

# web/app/upload/page.tsx 의 accept 속성과 동일하게 유지할 것.
ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "application/pdf"})
ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".pdf"})


def _reject_unsupported_file(file: UploadFile) -> None:
    """
    계약서 사진으로 볼 수 없는 파일은 Upstage에 보내기 전에 거른다.

    Content-Type 과 확장자를 둘 다 본다.
      · Content-Type 은 클라이언트가 정하므로 신뢰할 수 없다
      · 확장자만 보면 Content-Type 이 없는 정상 요청까지 막힌다
    둘 중 하나라도 허용 목록에 있으면 통과시키고, 둘 다 아니면 막는다.

    ⚠️ 415 대신 400을 쓴다. 프론트엔드가 400을 "입력한 값을 확인해 주세요"로
       안내하고, 415는 "잠시 후 다시 시도"라는 틀린 안내로 떨어진다.
       파일 형식이 틀린 것은 기다려서 해결되는 문제가 아니다.
    """
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    suffix = Path(file.filename or "").suffix.lower()

    if content_type in ALLOWED_CONTENT_TYPES or suffix in ALLOWED_SUFFIXES:
        return

    log.info("지원하지 않는 업로드 형식: content_type=%s suffix=%s", content_type, suffix)
    raise HTTPException(
        status_code=400,
        detail="JPG · PNG · PDF 파일만 올릴 수 있어요.",
    )


@router.post("/contracts/extract", response_model=ContractTerms)
async def extract_terms(file: Annotated[UploadFile, File()]) -> ContractTerms:
    """
    계약서 이미지/PDF 한 장을 업로드받아 ContractTerms로 추출한다.

    ⚠️ 이 응답만으로 서명 단계로 가면 안 된다.
       확인이 필요한 항목은 /contracts/review-items 로 받는다.
       (기존 연동을 깨지 않으려고 응답 형태는 그대로 둔다)
    """
    # 형식 검사를 먼저 한다 — 본문을 읽지 않고 끝낼 수 있으면 그게 가장 싸다.
    _reject_unsupported_file(file)

    # 한도보다 1바이트만 더 읽는다. 초과 판정에 그 1바이트로 충분하고,
    # 전체를 읽으면 제한을 두는 의미가 없어진다.
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        log.info("업로드 크기 초과로 거부: %d bytes 초과", MAX_UPLOAD_BYTES)
        raise HTTPException(
            status_code=413,
            detail="파일이 너무 커요. 10MB 이하로 올려 주세요.",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="파일이 비어 있어요. 다시 골라 주세요.")

    try:
        terms = await extract_contract_terms(file_bytes, file.filename or "contract")
    except (ExtractError, DocumentParseError, httpx.HTTPError) as error:
        # 내부 오류 내용을 사용자에게 노출하지 않는다. 로그에만 종류를 남긴다.
        log.error("계약서 추출 실패: error_type=%s", type(error).__name__)
        raise HTTPException(
            status_code=502,
            detail="지금은 계약서를 읽을 수 없어요. 잠시 뒤 다시 시도해 주세요.",
        ) from None

    items = build_review_items(terms)
    high = [i["field"] for i in items if i["priority"] == "high"]
    log.info("추출 완료 — 확인 필요 %d건 (반드시 확인 %s)", len(items), high or "없음")

    return terms


class EntitlementsResponse(BaseModel):
    items: list[dict]


@router.get("/entitlements", response_model=EntitlementsResponse)
async def entitlements() -> EntitlementsResponse:
    """
    "몰라서 못 받는 것들" 전체 목록.

    ⚠️ 전체를 주고 화면이 필터링한다. 그래서 **서버는 사용자가 임신했는지,
       장애가 있는지, 미성년자인지 알지 못한다.**
       민감정보를 다루는 가장 안전한 방법은 받지 않는 것이다.

    ⚠️ 로그인이 필요 없다. 권리를 알기 위해 가입해야 한다면 그것부터가 벽이다.
    """
    return EntitlementsResponse(items=all_entitlements())


class ReviewRequest(BaseModel):
    terms: ContractTerms


class ReviewResponse(BaseModel):
    items: list[dict]
    must_confirm: list[str]


@router.post("/contracts/review-items", response_model=ReviewResponse)
async def review_items(body: ReviewRequest) -> ReviewResponse:
    """
    확인이 필요한 항목과 그 이유.

    기준 (app/review/fields.py 참고):
      · 신뢰도가 낮거나 못 읽은 항목  — 값 자체가 의심스럽다
      · 판정에 쓰이는 항목            — 틀리면 판정이 틀린다
      · 계약서에 찍히는 신원 정보      — 틀리면 남의 이름으로 서명한다

    priority 가 high 인 항목은 서명 전에 반드시 확인받아야 한다.
    확인하지 않고 /contracts/analyze-sign 을 부르면 409로 막힌다.

    ⚠️ 손글씨는 source_text 도 AI가 읽은 결과라 근거가 되지 못한다.
       화면에서 원본 사진의 해당 위치를 함께 보여줄 것.
    """
    items = build_review_items(body.terms)
    return ReviewResponse(
        items=items,
        must_confirm=[i["field"] for i in items if i["priority"] == "high"],
    )
