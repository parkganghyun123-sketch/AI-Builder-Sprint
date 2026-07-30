"""
사용자 저장소 (C 담당)

--- 무엇을 저장하는가 ---

  user_id      우리 내부 ID (kakao:<회원번호>)
  provider     "kakao"
  nickname     화면 인사말용. 없을 수 있다
  role         WORKER | EMPLOYER
  created_at / last_login_at

⚠️ 이메일·전화번호·생년월일을 저장하지 않는다. 카카오에서 받지도 않는다.
   필요하지 않은 개인정보는 받지 않는 것이 가장 확실한 보호다.

⚠️ 계약 조건은 여기에도, documents 표에도 저장하지 않는다.
   우리가 갖는 것은 "누가 어떤 문서를 만들었는가"라는 연결뿐이고,
   계약서 원본은 모두싸인이 보관한다.

저장소 선택 방식은 app/store.py 와 같다. DATABASE_URL 이 있으면 Postgres,
없으면 메모리. 어느 쪽인지는 GET /health 의 store 로 확인한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum

from app.store import get_engine

log = logging.getLogger(__name__)

TABLE_NAME = "fairsign_users"

CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    user_id       TEXT PRIMARY KEY,
    provider      TEXT        NOT NULL,
    nickname      TEXT        NOT NULL DEFAULT '',
    role          TEXT        NOT NULL DEFAULT 'WORKER',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


class UserRole(str, Enum):
    """
    사용자가 스스로 고른 역할. 화면 흐름을 정할 뿐 권한이 아니다.

    ⚠️ 역할로 권한을 나누지 않는다. 사업주라고 남의 계약서를 볼 수 있으면
       안 되고, 근로자라고 계약서를 못 만들 이유도 없다.
       접근 통제는 문서 소유자(owner_id)로만 한다.
    """

    WORKER = "WORKER"
    EMPLOYER = "EMPLOYER"


# 메모리 저장소. DATABASE_URL 이 없을 때 쓴다.
_memory: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def kakao_user_id(kakao_id: str) -> str:
    """
    내부 사용자 ID.

    제공자를 접두사로 둔다. 나중에 애플·구글 로그인이 붙어도
    회원번호가 겹쳐 다른 사람이 같은 계정이 되는 일이 없다.
    """
    return f"kakao:{kakao_id}"


async def ensure_table() -> None:
    engine = get_engine()
    if engine is None:
        return
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text(CREATE_TABLE))


async def upsert(
    user_id: str,
    *,
    provider: str,
    nickname: str,
    default_role: UserRole = UserRole.WORKER,
) -> dict:
    """
    로그인할 때마다 호출한다. 처음이면 만들고, 아니면 접속 시각만 갱신한다.

    ⚠️ 재로그인 시 role 을 default_role 로 덮어쓰지 않는다.
       사용자가 화면에서 바꾼 역할이 로그인할 때마다 되돌아가면
       "왜 자꾸 초기화되지" 가 된다.
    """
    engine = get_engine()

    if engine is None:
        row = _memory.get(user_id)
        if row is None:
            row = {
                "user_id": user_id,
                "provider": provider,
                "nickname": nickname,
                "role": default_role.value,
                "created_at": _now(),
            }
            _memory[user_id] = row
        else:
            row["nickname"] = nickname or row["nickname"]
        row["last_login_at"] = _now()
        return dict(row)

    from sqlalchemy import text

    sql = text(
        f"""
        INSERT INTO {TABLE_NAME} (user_id, provider, nickname, role)
        VALUES (:user_id, :provider, :nickname, :role)
        ON CONFLICT (user_id) DO UPDATE SET
            nickname = COALESCE(NULLIF(EXCLUDED.nickname, ''), {TABLE_NAME}.nickname),
            last_login_at = NOW()
        RETURNING user_id, provider, nickname, role, created_at, last_login_at
        """
    )
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                sql,
                {
                    "user_id": user_id,
                    "provider": provider,
                    "nickname": nickname,
                    "role": default_role.value,
                },
            )
        ).mappings().first()
    return dict(row)


async def get(user_id: str) -> dict | None:
    engine = get_engine()

    if engine is None:
        row = _memory.get(user_id)
        return dict(row) if row else None

    from sqlalchemy import text

    sql = text(
        f"SELECT user_id, provider, nickname, role, created_at, last_login_at"
        f" FROM {TABLE_NAME} WHERE user_id = :user_id"
    )
    async with engine.connect() as conn:
        row = (await conn.execute(sql, {"user_id": user_id})).mappings().first()
    return dict(row) if row else None


async def set_role(user_id: str, role: UserRole) -> None:
    engine = get_engine()

    if engine is None:
        if user_id in _memory:
            _memory[user_id]["role"] = role.value
        return

    from sqlalchemy import text

    sql = text(f"UPDATE {TABLE_NAME} SET role = :role WHERE user_id = :user_id")
    async with engine.begin() as conn:
        await conn.execute(sql, {"role": role.value, "user_id": user_id})


def clear_memory() -> None:
    """테스트용."""
    _memory.clear()
