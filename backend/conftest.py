"""
테스트 공통 설정.

--- 왜 필요한가 ---

app/chat/rag.py 는 OpenAI 키가 있으면 OpenAI 를 먼저 호출하고,
없으면 Upstage 근거 생성으로 넘어간다. 실제 서비스에서는 맞는 순서다.

문제는 테스트다. 일부 테스트는 Upstage 경로만 가짜로 바꿔 놓는다.
  · 키가 없는 사람  → OpenAI 를 건너뛰고 가짜 Upstage 를 타서 통과
  · 키가 있는 사람  → **진짜 OpenAI 로 나간다**

같은 코드인데 .env 에 무엇이 들어 있느냐로 결과가 갈린다.
실제로 "613 passed, 4 failed" 가 여기서 나왔고, 그 4건은 코드 문제가
아니라 개발자 기기에 키가 있다는 사실 하나 때문이었다.

⚠️ 테스트가 개발자 환경에 따라 달라지면 테스트가 아니다.
   그래서 기본값을 "키 없음"으로 고정한다. 키가 필요한 테스트는
   지금도 각자 monkeypatch 로 넣고 있으므로(그리고 그 값이 이 기본값을
   덮으므로) 아무것도 깨지지 않는다.

부수 효과로 전체 실행 시간도 줄어든다. 7분의 상당 부분이
실제 LLM 왕복이었다.
"""

import pytest

from app.config import settings

# 외부 LLM 호출을 유발하는 키들.
# ⚠️ 새 제공자를 붙이면 여기에도 추가할 것.
#    빠뜨리면 그 제공자만 조용히 실제 호출로 나간다.
_PROVIDER_KEYS = ("openai_api_key", "upstage_api_key")


@pytest.fixture(autouse=True)
def _no_live_provider_keys(monkeypatch):
    """
    기본은 '키 없음'. 키가 필요한 테스트는 스스로 넣는다.

    settings 는 모듈 간 공유되는 단일 객체라서 여기 한 번만 비우면
    app.chat.rag / app.chat.general / app.ai.* 어디서 봐도 비어 있다.
    """
    for name in _PROVIDER_KEYS:
        monkeypatch.setattr(settings, name, "")
