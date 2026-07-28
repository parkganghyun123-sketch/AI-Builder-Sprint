# FairSign 백엔드
#
# ⚠️ WeasyPrint는 순수 파이썬이 아니다.
#    pango / cairo / gdk-pixbuf 같은 C 라이브러리와 한글 폰트가 있어야
#    계약서 PDF가 정상 생성된다. 없으면 한글이 통째로 깨진다.

FROM python:3.10-slim

# ---------------------------------------------------------------- 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint 렌더링 엔진
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # 한글 폰트 — 이게 없으면 계약서가 □□□로 나온다
    fonts-noto-cjk \
    # anchor 텍스트 검사용 (pdftotext)
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

# ---------------------------------------------------------------- 파이썬 의존성
# requirements를 먼저 복사해야 코드 변경 시 레이어 캐시가 유지된다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ---------------------------------------------------------------- 실행
# Railway 등은 PORT 환경변수를 주입한다
ENV PORT=8000
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
