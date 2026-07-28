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
from app.routers import contracts, extract, sign

logging.basicConfig(level=logging.INFO)

# WeasyPrint가 PDF를 만들 때마다 fontTools가 글리프 목록을 통째로 쏟아낸다.
# 계약서 한 장에 수백 줄이 나와서 정작 봐야 할 로그가 묻힌다.
# 이 라이브러리들은 경고 이상만 남긴다.
for _noisy in ("fontTools", "weasyprint", "PIL", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

app = FastAPI(title="FairSign API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # CORS_ORIGINS 환경변수로 추가
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log = logging.getLogger(__name__)
log.info("CORS 허용 도메인: %s", settings.allowed_origins)


@app.get("/health")
async def health() -> dict:
    """
    배포 확인용. 각 연동의 설정 여부를 함께 보여준다.

    프론트를 붙이기 전에 이걸 먼저 확인할 것.
    upstage가 false면 /contracts/extract 가 502로 죽는다.
    """
    return {
        "status": "ok",
        "modusign": settings.modusign_configured,
        "upstage": bool(settings.upstage_api_key),
        "cors_origins": settings.allowed_origins,
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
app.include_router(extract.router, tags=["ai"])
app.include_router(sign.router, tags=["signing"])
