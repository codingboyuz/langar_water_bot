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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_columns()
    await _ensure_pricing()
    await _ensure_admin()


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
