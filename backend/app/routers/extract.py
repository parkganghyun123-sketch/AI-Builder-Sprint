"""
계약서 추출 라우터 (A 담당)

  POST /contracts/extract         계약서 사진/PDF → ContractTerms
  POST /contracts/review-items    조건 → 확인이 필요한 항목 목록

⚠️ 여기서 나온 값은 AI 추출 직후의 값이다. 검증(/contracts/validate)에
   넘기기 전에 사용자가 화면에서 확인·수정해야 한다.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.ai.extract import ExtractError, extract_contract_terms
from app.review.fields import build_review_items
from app.schemas import ContractTerms

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/contracts/extract", response_model=ContractTerms)
async def extract_terms(file: Annotated[UploadFile, File()]) -> ContractTerms:
    """
    계약서 이미지/PDF 한 장을 업로드받아 ContractTerms로 추출한다.

    ⚠️ 이 응답만으로 서명 단계로 가면 안 된다.
       확인이 필요한 항목은 /contracts/review-items 로 받는다.
       (기존 연동을 깨지 않으려고 응답 형태는 그대로 둔다)
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        terms = await extract_contract_terms(file_bytes, file.filename or "contract")
    except ExtractError as e:
        log.error("추출 실패: %s", e)
        raise HTTPException(status_code=502, detail=f"추출 실패: {e}") from e

    items = build_review_items(terms)
    high = [i["field"] for i in items if i["priority"] == "high"]
    log.info("추출 완료 — 확인 필요 %d건 (반드시 확인 %s)", len(items), high or "없음")

    return terms


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
