"""
페어사인 백엔드

실행:
    cd backend
    uvicorn app.main:app --reload
문서:
    http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import contracts, sign

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


@app.get("/health/pdf")
async def health_pdf() -> Response:
    """
    배포 환경 PDF 진단.

    리눅스 서버에는 한글 폰트가 기본 탑재되지 않아, 로컬에서는 멀쩡하던
    계약서가 서버에서만 □□□로 깨지는 사고가 잦다.
    배포 후 이 주소를 브라우저로 열어 한글이 정상인지 눈으로 확인한다.
    """
    from app.pdf.generator import render_contract_pdf
    from make_test_pdf import SAMPLE

    pdf = render_contract_pdf(
        SAMPLE,
        verification_note="※ 배포 환경 폰트 진단용 문서입니다. 한글이 깨지지 않았는지 확인하세요.",
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="font_check.pdf"'},
    )


app.include_router(contracts.router, tags=["contracts"])
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
