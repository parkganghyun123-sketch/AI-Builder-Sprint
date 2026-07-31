"""계약서 없이 쓰는 일반 기준 질문 API."""

from fastapi import APIRouter

from app.chat.general import answer_general_question
from app.schemas import GeneralQuestionRequest, GeneralQuestionResponse

router = APIRouter()


@router.post("/questions/general", response_model=GeneralQuestionResponse)
async def general_question(body: GeneralQuestionRequest) -> GeneralQuestionResponse:
    return answer_general_question(body.question)
