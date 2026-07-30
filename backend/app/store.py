"""
계약 문서 이력 저장소 (C 담당)

--- 무엇을 저장하는가 ---

문서 식별자와 진행 상태**만** 저장한다.

  document_id  모두싸인 문서 ID
  status       DocumentStatus
  signed/total 서명 진행도
  entry_path   경로 A(사진) / B(직접 입력)
  title        문서 제목
  created_at / updated_at

계약 조건·이름·이메일·시급은 저장하지 않는다.
이력 조회에 필요하지 않고, 남기는 순간 보관 기간과 삭제 책임이 생긴다.
계약서 원본은 모두싸인이 보관하고, 우리는 그것을 가리키는 표만 갖는다.
(AGENTS.md: "API 키, 계약서 내용, 개인정보를 로그에 남기지 않습니다")

--- 왜 추상화하는가 ---

메모리 딕셔너리로 시작했다. 그래서 Railway가 재배포될 때마다 계약 이력이
사라졌고, README가 스스로 그 한계를 인정하고 있었다.

DATABASE_URL 이 있으면 Postgres(Supabase)를, 없으면 메모리를 쓴다.
DB를 붙이지 않은 개발자도 그대로 실행할 수 있어야 하고,
데모 중에 DB가 흔들려도 서비스가 죽어서는 안 된다.

⚠️ 어느 쪽을 쓰고 있는지는 GET /health 의 "store" 로 확인할 것.
   "memory" 로 보이는데 DATABASE_URL 을 넣었다고 생각한다면,
   그건 연결에 실패해 폴백한 상태다. 로그에 이유가 남는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Protocol

from app.config import settings
from app.schemas import DocumentStatus, EntryPath

log = logging.getLogger(__name__)

TABLE_NAME = "fairsign_documents"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    document_id TEXT PRIMARY KEY,
    status      TEXT        NOT NULL,
    signed      INTEGER     NOT NULL DEFAULT 0,
    total       INTEGER     NOT NULL DEFAULT 2,
    entry_path  TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# 마이그레이션 도구(Alembic)를 두지 않는다.
#
# 표가 하나이고 컬럼이 8개다. 대회 기간에 스키마를 바꿀 일이 생기면
# 위 DDL 을 고치고 새 컬럼은 ALTER TABLE 로 직접 추가하는 편이
# 마이그레이션 파일을 관리하는 비용보다 싸다.
# 대회 이후 스키마가 늘어나면 그때 Alembic 을 도입할 것.


class DocumentRecord(dict):
    """
    문서 한 건. dict 를 그대로 쓴다.

    ⚠️ 여기에 계약 조건이나 이름을 넣지 말 것.
       tests/test_api_gates.py 가 개인정보 미포함을 검사한다.
    """


class DocumentStore(Protocol):
    """저장소 인터페이스. 구현을 바꿔도 라우터는 그대로여야 한다."""

    backend: str

    async def remember(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        entry_path: EntryPath,
        title: str,
        total: int = 2,
    ) -> None: ...

    async def get(self, document_id: str) -> DocumentRecord | None: ...

    async def update_progress(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        signed: int,
        total: int,
    ) -> None: ...

    async def exists(self, document_id: str) -> bool: ...


# ============================================================
# 메모리 구현 — DB 없이도 실행되어야 한다
# ============================================================


class MemoryDocumentStore:
    """
    프로세스 메모리 저장소.

    ⚠️ 재시작하면 사라진다. 로컬 개발과 테스트용이다.
       배포 환경에서 이걸 쓰고 있으면 /health 의 store 가 "memory" 로 보인다.
    """

    backend = "memory"

    def __init__(self) -> None:
        self._rows: dict[str, DocumentRecord] = {}

    async def remember(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        entry_path: EntryPath,
        title: str,
        total: int = 2,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._rows[document_id] = DocumentRecord(
            document_id=document_id,
            status=status,
            signed=0,
            total=total,
            entry_path=entry_path,
            title=title,
            created_at=now,
            updated_at=now,
        )

    async def get(self, document_id: str) -> DocumentRecord | None:
        return self._rows.get(document_id)

    async def update_progress(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        signed: int,
        total: int,
    ) -> None:
        row = self._rows.get(document_id)
        if row is None:
            return
        row.update(
            status=status, signed=signed, total=total, updated_at=datetime.now(timezone.utc)
        )

    async def exists(self, document_id: str) -> bool:
        return document_id in self._rows

    # --- 테스트 편의 -----------------------------------------
    def clear(self) -> None:
        self._rows.clear()

    def snapshot(self) -> dict[str, DocumentRecord]:
        return dict(self._rows)


# ============================================================
# Postgres 구현 (Supabase)
# ============================================================


def normalize_database_url(url: str) -> str:
    """
    Supabase 가 주는 접속 문자열을 SQLAlchemy async 드라이버용으로 바꾼다.

    Supabase 대시보드는 `postgresql://...` 또는 `postgres://...` 를 준다.
    SQLAlchemy 는 드라이버를 명시해야 async 엔진을 만든다.
    psycopg 3 은 requirements 에 이미 있고 async 를 지원한다.

    ⚠️ 이미 `+psycopg` 가 붙어 있으면 그대로 둔다.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


class PostgresDocumentStore:
    """
    Supabase(Postgres) 저장소.

    ⚠️ Supabase 의 Transaction pooler(6543 포트)는 pgbouncer 를 거치므로
       prepared statement 를 쓸 수 없다. psycopg 에 prepare_threshold=0 을
       넘겨 매번 새로 파싱하게 한다. 이 옵션이 없으면
       "prepared statement ... already exists" 로 간헐 실패한다.

       Session pooler(5432)나 직접 연결에서는 이 옵션이 무해하다.
    """

    backend = "postgres"

    def __init__(self, engine) -> None:
        self._engine = engine

    @classmethod
    async def connect(cls, url: str) -> PostgresDocumentStore:
        """엔진을 만들고 표를 준비한다. 실패하면 예외를 그대로 올린다."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            normalize_database_url(url),
            pool_pre_ping=True,  # 유휴 연결이 끊겨 있으면 조용히 새로 맺는다
            pool_size=5,
            max_overflow=5,
            connect_args={"prepare_threshold": 0},
        )
        async with engine.begin() as conn:
            await conn.execute(text(_CREATE_TABLE))
        return cls(engine)

    async def remember(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        entry_path: EntryPath,
        title: str,
        total: int = 2,
    ) -> None:
        from sqlalchemy import text

        # 같은 문서를 두 번 발송하는 흐름은 없지만, 재시도로 들어올 수 있다.
        # 그때 500을 내지 않고 갱신한다.
        sql = text(
            f"""
            INSERT INTO {TABLE_NAME}
                (document_id, status, signed, total, entry_path, title)
            VALUES (:document_id, :status, 0, :total, :entry_path, :title)
            ON CONFLICT (document_id) DO UPDATE SET
                status = EXCLUDED.status,
                total = EXCLUDED.total,
                updated_at = NOW()
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                sql,
                {
                    "document_id": document_id,
                    "status": status.value,
                    "total": total,
                    "entry_path": entry_path.value,
                    "title": title,
                },
            )

    async def get(self, document_id: str) -> DocumentRecord | None:
        from sqlalchemy import text

        sql = text(
            f"SELECT document_id, status, signed, total, entry_path, title,"
            f" created_at, updated_at FROM {TABLE_NAME} WHERE document_id = :d"
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(sql, {"d": document_id})).mappings().first()

        if row is None:
            return None

        data = dict(row)
        data["status"] = DocumentStatus(data["status"])
        data["entry_path"] = EntryPath(data["entry_path"])
        return DocumentRecord(**data)

    async def update_progress(
        self,
        document_id: str,
        *,
        status: DocumentStatus,
        signed: int,
        total: int,
    ) -> None:
        from sqlalchemy import text

        sql = text(
            f"""
            UPDATE {TABLE_NAME}
               SET status = :status, signed = :signed, total = :total,
                   updated_at = NOW()
             WHERE document_id = :document_id
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                sql,
                {
                    "document_id": document_id,
                    "status": status.value,
                    "signed": signed,
                    "total": total,
                },
            )

    async def exists(self, document_id: str) -> bool:
        from sqlalchemy import text

        sql = text(f"SELECT 1 FROM {TABLE_NAME} WHERE document_id = :d")
        async with self._engine.connect() as conn:
            return (await conn.execute(sql, {"d": document_id})).first() is not None


# ============================================================
# 선택 — 앱이 실제로 쓰는 저장소
# ============================================================

# 기본값은 메모리다. DB 연결에 성공하면 startup 에서 교체된다.
#
# ⚠️ 모듈 최상단에서 DB 에 붙지 않는다. import 시점에 네트워크를 타면
#    테스트가 느려지고, DB 가 죽어 있을 때 앱이 아예 뜨지 않는다.
_active: DocumentStore = MemoryDocumentStore()


def get_store() -> DocumentStore:
    """
    지금 쓰고 있는 저장소.

    ⚠️ 호출할 때마다 조회한다. `from app.store import _active` 처럼
       값을 가져다 쓰면 init_store() 가 교체한 뒤에도 옛 객체를 붙들고 있다.
       (실제로 `from app.store import store` 로 썼다가 이 문제를 만났다)
    """
    return _active


def set_store(new_store: DocumentStore) -> None:
    """테스트에서 저장소를 갈아끼울 때 쓴다."""
    global _active
    _active = new_store


async def init_store() -> str:
    """
    DATABASE_URL 이 있으면 Postgres 로 전환한다. 반환값은 최종 backend 이름.

    ⚠️ 연결에 실패해도 예외를 올리지 않는다.
       DB 가 안 붙는다고 데모가 죽으면 안 된다. 메모리로 계속 가되,
       무엇이 왜 실패했는지 로그와 /health 에 드러낸다.
       조용히 폴백하는 것이 가장 나쁘다.
    """
    if not settings.database_url:
        log.warning(
            "DATABASE_URL 미설정 — 메모리 저장소를 사용합니다. "
            "재시작하면 계약 이력이 사라집니다."
        )
        return get_store().backend

    try:
        set_store(await PostgresDocumentStore.connect(settings.database_url))
    except Exception as error:
        # 접속 문자열에는 비밀번호가 들어 있다. 예외 원문을 로그에 남기지 않는다.
        log.error(
            "DATABASE_URL 이 설정됐지만 연결에 실패해 메모리로 폴백합니다: "
            "error_type=%s",
            type(error).__name__,
        )
        return get_store().backend

    log.info("Postgres 저장소 연결됨 (표: %s)", TABLE_NAME)
    return get_store().backend
