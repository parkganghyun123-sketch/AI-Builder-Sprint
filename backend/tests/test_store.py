"""
문서 이력 저장소 테스트.

⚠️ 실제 DB에 붙지 않는다. 메모리 구현과 접속 문자열 변환만 검증한다.
   Postgres 구현의 SQL은 Supabase 연결 후 수동으로 확인할 것
   (GET /health 의 store 가 "postgres" 로 보이면 표 생성까지 성공한 것이다).
"""

import asyncio

import pytest

from app.schemas import DocumentStatus, EntryPath
from app.store import (
    MemoryDocumentStore,
    normalize_database_url,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def store() -> MemoryDocumentStore:
    return MemoryDocumentStore()


# ============================================================
# 메모리 저장소
# ============================================================


def test_기록한_문서를_다시_읽을_수_있다(store):
    _run(
        store.remember(
            "DOC-1",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
        )
    )

    record = _run(store.get("DOC-1"))
    assert record is not None
    assert record["status"] is DocumentStatus.ON_GOING
    assert record["signed"] == 0
    assert record["total"] == 2  # 근로자 + 사업주
    assert record["entry_path"] is EntryPath.PHOTO


def test_없는_문서는_None_을_돌려준다(store):
    assert _run(store.get("없는문서")) is None
    assert _run(store.exists("없는문서")) is False


def test_개인정보를_저장하지_않는다(store):
    """
    ⚠️ 저장 대상은 문서 식별자와 진행 상태뿐이다.

    계약 조건·이름·이메일·시급을 남기면 그 순간부터 보관 기간과
    삭제 책임이 생긴다. 계약서 원본은 모두싸인이 보관하고,
    우리는 그것을 가리키는 표만 갖는다.
    """
    _run(
        store.remember(
            "DOC-2",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.MANUAL,
            title="근로계약서",
        )
    )

    record = _run(store.get("DOC-2"))
    assert set(record) == {
        "document_id",
        "status",
        "signed",
        "total",
        "entry_path",
        "title",
        "created_at",
        "updated_at",
    }


def test_진행도를_갱신한다(store):
    _run(
        store.remember(
            "DOC-3",
            status=DocumentStatus.ON_GOING,
            entry_path=EntryPath.PHOTO,
            title="근로계약서",
        )
    )
    _run(
        store.update_progress(
            "DOC-3", status=DocumentStatus.COMPLETED, signed=2, total=2
        )
    )

    record = _run(store.get("DOC-3"))
    assert record["status"] is DocumentStatus.COMPLETED
    assert record["signed"] == 2


def test_없는_문서_갱신은_조용히_넘어간다(store):
    """
    외부 문서(스파이크 스크립트 발송 등)의 웹훅이 들어올 수 있다.
    우리가 모르는 문서를 갱신하려 했다고 예외를 내면
    모두싸인에 500이 나가고 웹훅이 자동 비활성화될 수 있다.
    """
    _run(
        store.update_progress(
            "모르는문서", status=DocumentStatus.COMPLETED, signed=2, total=2
        )
    )
    assert _run(store.get("모르는문서")) is None


def test_같은_문서를_다시_기록하면_덮어쓴다(store):
    """재시도로 같은 문서가 두 번 들어올 수 있다. 500을 내지 않는다."""
    for status in (DocumentStatus.ON_PROCESSING, DocumentStatus.ON_GOING):
        _run(
            store.remember(
                "DOC-4",
                status=status,
                entry_path=EntryPath.PHOTO,
                title="근로계약서",
            )
        )

    assert _run(store.get("DOC-4"))["status"] is DocumentStatus.ON_GOING


# ============================================================
# 접속 문자열 변환
# ============================================================


@pytest.mark.parametrize(
    "given,expected",
    [
        # Supabase 대시보드가 주는 형태
        (
            "postgresql://user:pw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres",
            "postgresql+psycopg://user:pw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres",
        ),
        # 오래된 형태 (Heroku 등이 쓰던 스킴)
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # 이미 드라이버가 지정된 경우는 건드리지 않는다
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
    ],
)
def test_접속_문자열에_async_드라이버를_붙인다(given, expected):
    """
    SQLAlchemy 는 드라이버를 명시해야 async 엔진을 만든다.
    Supabase 는 드라이버 없는 문자열을 주므로 우리가 붙인다.
    """
    assert normalize_database_url(given) == expected
