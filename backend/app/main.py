"""
페어사인 백엔드

실행:
    cd backend
    uvicorn app.main:app --reload
문서:
    http://localhost:8000/docs
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, contracts, extract, general_questions, sign
from app.store import get_store, init_store

logging.basicConfig(level=logging.INFO)

# WeasyPrint가 PDF를 만들 때마다 fontTools가 글리프 목록을 통째로 쏟아낸다.
# 계약서 한 장에 수백 줄이 나와서 정작 봐야 할 로그가 묻힌다.
# 이 라이브러리들은 경고 이상만 남긴다.
for _noisy in ("fontTools", "weasyprint", "PIL", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """
    앱이 뜰 때 문서 이력 저장소를 준비한다.

    DATABASE_URL 이 있으면 Postgres 로 전환하고, 없거나 연결에 실패하면
    메모리로 계속 간다. 연결 실패로 앱이 아예 안 뜨면 데모가 죽는다.
    어느 쪽을 쓰고 있는지는 GET /health 의 "store" 로 확인할 것.
    """
    backend = await init_store()
    log.info("문서 이력 저장소: %s", backend)

    # 사용자 표는 문서 표와 같은 연결 풀을 쓴다.
    from app.auth import users

    try:
        await users.ensure_table()
    except Exception as error:
        # 로그인이 안 되더라도 판정·문구 기능은 계속 동작해야 한다.
        log.error("사용자 표 준비 실패: error_type=%s", type(error).__name__)
    yield


app = FastAPI(title="FairSign API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # CORS_ORIGINS 환경변수로 추가
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log.info("CORS 허용 도메인: %s", settings.allowed_origins)


# 지금 돌고 있는 코드가 어느 커밋인지.
#
# 고친 뒤 배포 전에 테스트를 돌려 "왜 안 고쳐졌지" 하는 일이 반복됐다.
# Railway가 빌드 중이면 이전 커밋이 응답하는데 겉으로는 구분이 안 된다.
# RAILWAY_GIT_COMMIT_SHA 는 Railway가 자동으로 넣어준다.
_COMMIT = (
    os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("GIT_COMMIT")
    or "unknown"
)[:7]


@app.get("/health")
async def health() -> dict:
    """
    배포 확인용. 각 연동의 설정 여부를 함께 보여준다.

    프론트를 붙이기 전에 이걸 먼저 확인할 것.
      upstage가 false면 /contracts/extract 가 502로 죽는다.
      commit이 로컬 HEAD와 다르면 아직 이전 코드가 돌고 있는 것이다.
      cors_origins에 프론트 도메인이 없으면 브라우저가 전부 막는다.
      store가 memory면 재배포 시 계약 이력이 사라진다.
      webhook_token이 false면 웹훅 URL을 아무나 호출할 수 있다.

    ⚠️ 비밀값은 담지 않는다. 설정됐는지(true/false)만 보여준다.
       실제 값을 노출하면 이 엔드포인트가 그대로 유출 경로가 된다.
    """
    return {
        "status": "ok",
        "commit": _COMMIT,
        "modusign": settings.modusign_configured,
        "upstage": bool(settings.upstage_api_key),
        "store": get_store().backend,
        "webhook_token": bool(settings.webhook_path_token),
        "kakao_login": settings.kakao_configured,
        # ⚠️ 비밀값이 아니다. 이 주소는 어차피 사용자 브라우저로 나간다.
        #    카카오 콘솔에 등록한 값과 **한 글자라도** 다르면 KOE006 이 나는데,
        #    로그인 화면까지 가봐야 알 수 있어서 진단이 오래 걸렸다.
        #    여기서 눈으로 대조할 수 있게 그대로 보여준다.
        "kakao_redirect_uri": settings.kakao_callback_url,
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


app.include_router(auth.router)
app.include_router(contracts.router, tags=["contracts"])
app.include_router(chat.router, tags=["contract assistant"])
app.include_router(general_questions.router, tags=["general questions"])
app.include_router(extract.router, tags=["ai"])
app.include_router(sign.router, tags=["signing"])
