"""
페어사인 백엔드

실행:
    cd backend
    uvicorn app.main:app --reload
문서:
    http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import sign

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FairSign API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 배포 시 프론트 도메인 추가
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """배포 확인용. 각 연동의 설정 여부를 함께 보여준다."""
    return {
        "status": "ok",
        "modusign": settings.modusign_configured,
        "upstage": bool(settings.upstage_api_key),
    }


app.include_router(sign.router, tags=["signing"])

# ------------------------------------------------------------------
# 담당자별 라우터 자리. 각자 파일을 만들어 아래에 추가한다.
#
#   A → app/routers/extract.py    POST /contracts/extract   (사진 → 조건)
#   B → app/routers/validate.py   POST /contracts/validate  (조건 → 판정)
#   C → app/routers/sign.py       ✅ 완료
#
# 예시:
#   from app.routers import extract
#   app.include_router(extract.router, tags=["ai"])
# ------------------------------------------------------------------
