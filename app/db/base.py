"""Async engine va sessiya fabrikasi.

`DATABASE_URL` orqali SQLite yoki PostgreSQL'ga ulanadi:
  sqlite+aiosqlite:///./langar.db
  postgresql+asyncpg://user:pass@host:5432/db
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.models import Base

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Jadvallarni yaratadi (agar mavjud bo'lmasa) va admin'ni qo'shadi."""
    await _migrate_chat_pre()      # eski chat sxemasini chetga suramiz
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_chat_post()     # eski yozishmalarni yangi sxemaga ko'chiramiz
    await _ensure_columns()
    await _ensure_pricing()
    await _ensure_admin()


async def _chat_columns(conn) -> list[str]:
    """`chat_messages` jadvali ustunlari (bo'lmasa — bo'sh)."""
    from sqlalchemy import text

    if conn.dialect.name == "sqlite":
        res = await conn.execute(text("PRAGMA table_info('chat_messages')"))
        return [row[1] for row in res.fetchall()]
    res = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='chat_messages'"
        )
    )
    return [row[0] for row in res.fetchall()]


async def _migrate_chat_pre() -> None:
    """Eski chat sxemasi (courier_id, to_courier/from_courier) bo'lsa, jadvalni
    chetga surib qo'yamiz — yangisini create_all toza sxemada yaratadi."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        cols = await _chat_columns(conn)
        if cols and "party_kind" not in cols:
            await conn.execute(text("ALTER TABLE chat_messages RENAME TO chat_messages_old"))


async def _migrate_chat_post() -> None:
    """Eski yozishmalarni (chat_messages_old) yangi sxemaga ko'chiramiz."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            res = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages_old'")
            )
        else:
            res = await conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name='chat_messages_old'")
            )
        if res.first() is None:
            return
        await conn.execute(
            text(
                """
                INSERT INTO chat_messages (id, party_kind, party_id, direction, text, is_read, created_at)
                SELECT id, 'courier', courier_id,
                       CASE direction
                            WHEN 'to_courier'   THEN 'out'
                            WHEN 'from_courier' THEN 'in'
                            ELSE direction END,
                       text, is_read, created_at
                FROM chat_messages_old
                """
            )
        )
        await conn.execute(text("DROP TABLE chat_messages_old"))


async def _ensure_pricing() -> None:
    """Narxlarni boshlang'ich qiymatlar bilan to'ldiradi (config.REGIONS dan).

    Faqat yo'q bo'lsa qo'shadi — mavjud (admin tahrirlagan) narxlarga tegmaydi.
    """
    from sqlalchemy import select

    from app.config import REGIONS
    from app.db.models import AppSetting, Pricing

    async with SessionLocal() as s:
        for r in REGIONS:
            exists = await s.execute(select(Pricing).where(Pricing.region_key == r.key))
            if exists.scalar_one_or_none() is None:
                s.add(
                    Pricing(
                        region_key=r.key,
                        region_name=r.name,
                        water_price=r.price,
                        courier_rate=r.courier_rate,
                    )
                )
        if await s.get(AppSetting, "bottle_price") is None:
            s.add(AppSetting(key="bottle_price", value="0"))
        await s.commit()


async def _ensure_columns() -> None:
    """Eski bazaga yangi ustunlarni qo'shadi (yengil migratsiya).

    `create_all` mavjud jadvalga ustun qo'shmaydi, shuning uchun yetishmayotgan
    ustunlarni qo'lda ALTER qilamiz (xato bo'lsa — e'tiborsiz qoldiramiz).
    """
    from sqlalchemy import text

    # (jadval, ustun, ta'rif)
    migrations = [
        ("couriers", "lang", "VARCHAR(5) DEFAULT 'uz'"),
    ]
    async with engine.begin() as conn:
        for table, column, ddl in migrations:
            try:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                )
            except Exception:
                # ustun allaqachon mavjud — davom etamiz
                pass


async def _ensure_admin() -> None:
    from sqlalchemy import select

    from app.config import settings as cfg
    from app.db.models import Admin
    from app.security import hash_password

    async with SessionLocal() as session:
        res = await session.execute(select(Admin).where(Admin.login == cfg.admin_login))
        if res.scalar_one_or_none() is None:
            session.add(
                Admin(login=cfg.admin_login, password_hash=hash_password(cfg.admin_password))
            )
            await session.commit()
