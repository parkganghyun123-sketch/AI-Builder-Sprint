"""계약 비서 API. 원문을 저장하거나 외부 LLM으로 보내지 않는다."""

from fastapi import APIRouter

from app.chat.service import answer
from app.routers.contracts import _validate_for_worker
from app.schemas import ContractChatRequest, ContractChatResponse

router = APIRouter()


@router.post("/contracts/chat", response_model=ContractChatResponse)
async def contract_chat(body: ContractChatRequest) -> ContractChatResponse:
    """확인된 계약 조건과 검증 결과를 검색해 근거가 있는 답변만 반환한다."""
    report = _validate_for_worker(body.terms, body.worker_birth_date)
    return answer(body.question, body.terms, report)
