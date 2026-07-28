"""
계약서 추출 라우터 (A 담당)

  POST /contracts/extract   계약서 사진/PDF → ContractTerms

⚠️ 여기서 나온 값은 AI 추출 직후의 값이다. 검증(/contracts/validate)에
   넘기기 전에 사용자가 화면에서 확인·수정해야 한다.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.ai.extract import ExtractError, extract_contract_terms
from app.schemas import ContractTerms

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/contracts/extract", response_model=ContractTerms)
async def extract_terms(file: Annotated[UploadFile, File()]) -> ContractTerms:
    """계약서 이미지/PDF 한 장을 업로드받아 ContractTerms로 추출한다."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        return await extract_contract_terms(file_bytes, file.filename or "contract")
    except ExtractError as e:
        log.error("추출 실패: %s", e)
        raise HTTPException(status_code=502, detail=f"추출 실패: {e}") from e
