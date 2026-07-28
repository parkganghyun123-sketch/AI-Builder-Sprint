"""
Upstage Document Parse 연동 (A 담당)

계약서 이미지/PDF → 텍스트 + 표 구조.
Standard 모드로 시작한다. Enhanced($0.03)는 Standard($0.01)가 실패하는
케이스를 확인한 뒤에 검토한다.

참고: https://console.upstage.ai/docs/capabilities/document-digitization/document-parsing
"""

import httpx

from app.config import settings

BASE_URL = "https://api.upstage.ai/v1/document-digitization"

MODE_STANDARD = "standard"
MODE_ENHANCED = "enhanced"


class DocumentParseError(Exception):
    pass


def _auth_header() -> dict[str, str]:
    if not settings.upstage_api_key:
        raise DocumentParseError("UPSTAGE_API_KEY 미설정")
    return {"Authorization": f"Bearer {settings.upstage_api_key}"}


async def parse_document(
    file_bytes: bytes,
    filename: str,
    *,
    mode: str = MODE_STANDARD,
) -> dict:
    """
    문서 파싱 요청.

    반환값은 Upstage 응답 그대로 (dict). 주로 쓰는 필드:
      - result["content"]["text"]      전체 텍스트
      - result["content"]["markdown"]  마크다운 (표 구조 보존)
      - result["elements"]             레이아웃 요소 배열 (문단·표·제목 등)
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(
            BASE_URL,
            headers=_auth_header(),
            data={
                "model": "document-parse",
                "mode": mode,
                "output_formats": '["text", "markdown"]',
                "ocr": "auto",
            },
            files={"document": (filename, file_bytes)},
        )

    if res.status_code >= 400:
        raise DocumentParseError(f"HTTP {res.status_code}: {res.text}")

    return res.json()
