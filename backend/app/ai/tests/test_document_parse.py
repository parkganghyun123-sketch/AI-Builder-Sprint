"""
document_parse.py 단위 테스트. 실제 API를 호출하지 않는다 (httpx를 mock).
실제 API 연동 확인은 spikes/extract_spike.py 로 별도 진행.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.document_parse import DocumentParseError, parse_document
from app.config import settings


class FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text or str(json_body)

    def json(self):
        return self._json_body


@pytest.fixture(autouse=True)
def upstage_key(monkeypatch):
    monkeypatch.setattr(settings, "upstage_api_key", "test-key")


class TestParseDocument:
    @pytest.mark.asyncio
    async def test_success_returns_json_and_sends_auth_header(self):
        fake = FakeResponse(200, {"content": {"text": "가상 계약서 본문"}})
        with patch(
            "httpx.AsyncClient.post", new=AsyncMock(return_value=fake)
        ) as mock_post:
            result = await parse_document(b"fake-bytes", "contract.png")

        assert result["content"]["text"] == "가상 계약서 본문"
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["data"]["model"] == "document-parse"
        assert kwargs["data"]["mode"] == "standard"

    @pytest.mark.asyncio
    async def test_http_error_raises_document_parse_error(self):
        fake = FakeResponse(400, text="bad request")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
            with pytest.raises(DocumentParseError):
                await parse_document(b"fake-bytes", "contract.png")

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_before_request(self, monkeypatch):
        monkeypatch.setattr(settings, "upstage_api_key", "")
        with pytest.raises(DocumentParseError):
            await parse_document(b"fake-bytes", "contract.png")
