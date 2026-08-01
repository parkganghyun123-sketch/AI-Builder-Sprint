"""
DATABASE_URL 연결 진단 (C 담당)

app/store.py 의 init_store() 는 연결에 실패해도 앱을 죽이지 않고
메모리로 폴백한다. 데모가 DB 때문에 멈추면 안 되기 때문이다.
대신 원인을 찾기 어려워지므로, 이 스크립트가 전체 예외 사슬을 보여준다.

⚠️ 비밀번호·사용자명·호스트는 출력에서 가린다.
   진단 결과를 팀 채널이나 이슈에 그대로 붙일 수 있어야 한다.

실행:
    cd backend
    source .venv/bin/activate
    python -m scripts.check_database_url
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.store import (  # noqa: E402
    describe_database_url,
    normalize_database_url,
)

MASK = "***"


def _redact(text: str) -> str:
    """접속 문자열에서 온 비밀 조각을 지운다."""
    url = settings.database_url
    if not url:
        return text

    secrets = [url, normalize_database_url(url)]

    # user:password@host 구간을 조각내서 각각 가린다.
    scheme, _, rest = url.partition("://")
    creds, sep, hostpart = rest.rpartition("@")
    if sep:
        user, _, password = creds.partition(":")
        secrets += [creds, user, password]
        host = hostpart.partition("/")[0].rpartition(":")[0]
        secrets.append(host)

    for secret in sorted(set(s for s in secrets if s and len(s) > 3), key=len, reverse=True):
        text = text.replace(secret, MASK)
    return text


def _report_dependencies() -> bool:
    """드라이버가 설치돼 있는지 먼저 본다. 여기서 걸리는 경우가 많다."""
    ok = True
    for module, why in (
        ("sqlalchemy", "엔진"),
        ("psycopg", "Postgres 드라이버"),
        ("greenlet", "SQLAlchemy async 실행에 필수"),
    ):
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            print(f"  ✅ {module:12s} {version:12s} ({why})")
        except Exception as error:
            ok = False
            print(f"  ❌ {module:12s} 없음 — {type(error).__name__} ({why})")
    if not ok:
        print("\n  → 해결: pip install -r requirements.txt")
    return ok


async def _try_connect() -> None:
    from app.store import PostgresDocumentStore

    store = await PostgresDocumentStore.connect(settings.database_url)
    print(f"  ✅ 연결 성공 — backend={store.backend}")

    # 실제로 읽고 쓸 수 있는지까지 확인한다. 표 생성만 되고 권한이 없는 경우가 있다.
    from app.schemas import DocumentStatus, EntryPath

    probe_id = "__fairsign_connectivity_probe__"
    await store.remember(
        probe_id,
        status=DocumentStatus.DRAFTING,
        entry_path=EntryPath.PHOTO,
        title="연결 확인용",
    )
    record = await store.get(probe_id)
    print(f"  ✅ 쓰기·읽기 확인 — status={record['status'].value}")
    print("\n  ⚠️ 확인용 행이 남아 있습니다. 지우려면:")
    print(f"     DELETE FROM fairsign_documents WHERE document_id = '{probe_id}';")


def main() -> int:
    print("\n[1] 환경변수")
    if not settings.database_url:
        print("  ❌ DATABASE_URL 이 비어 있습니다.")
        print("     .env 를 확인하세요. 없으면 메모리 저장소로 동작합니다")
        print("     (재시작 시 계약 이력 소실).")
        return 1
    print(f"  구조: {describe_database_url(settings.database_url)}")
    print(f"  변환: {describe_database_url(normalize_database_url(settings.database_url))}")

    print("\n[2] 의존성")
    if not _report_dependencies():
        return 1

    print("\n[3] 연결")
    try:
        asyncio.run(_try_connect())
    except Exception:
        print("  ❌ 실패. 전체 예외 사슬 (비밀값 가림):\n")
        print(_redact(traceback.format_exc()))
        return 1

    print("\n완료. uvicorn 을 띄우면 /health 의 store 가 postgres 로 바뀝니다.")
    return 0


if __name__ == "__main__":
    # 로컬 프록시 환경변수가 psycopg 연결을 방해하는 경우가 있어 알려만 준다.
    proxies = [k for k in ("ALL_PROXY", "all_proxy") if os.environ.get(k)]
    if proxies:
        print(f"참고: 프록시 환경변수가 설정돼 있습니다 ({', '.join(proxies)})")
    raise SystemExit(main())
