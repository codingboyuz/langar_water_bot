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
    await _ensure_warehouse()
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


async def _table_exists(conn, name: str) -> bool:
    from sqlalchemy import text

    if conn.dialect.name == "sqlite":
        res = await conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
        )
    else:
        res = await conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name=:n"), {"n": name}
        )
    return res.first() is not None


async def _drop_table_indexes(conn, table: str) -> None:
    """Jadvalga tegishli indekslarni o'chiradi.

    SQLite/Postgres'da jadval RENAME qilinganda indekslar eski nomi bilan
    ko'chadi — bu yangi jadval indekslari bilan nom to'qnashuviga olib keladi.
    Shu sabab eski indekslarni bo'shatamiz (nomlar qaytadan ishlatilsin).
    """
    from sqlalchemy import text

    if conn.dialect.name == "sqlite":
        res = await conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name=:t AND name NOT LIKE 'sqlite_%'"
            ),
            {"t": table},
        )
        names = [r[0] for r in res.fetchall()]
    else:
        res = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename=:t"), {"t": table}
        )
        names = [r[0] for r in res.fetchall()]
    for n in names:
        try:
            await conn.execute(text(f'DROP INDEX IF EXISTS "{n}"'))
        except Exception:
            pass


async def _migrate_chat_pre() -> None:
    """Eski chat sxemasi (courier_id, to_courier/from_courier) bo'lsa, jadvalni
    chetga surib qo'yamiz — yangisini create_all toza sxemada yaratadi.

    Eski indekslar nomi yangi jadval indekslari bilan to'qnashmasligi uchun
    chetga surilgan jadval indekslarini o'chiramiz (yarim ko'chgan holatni ham
    shu yo'l bilan tiklaymiz)."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        cols = await _chat_columns(conn)
        if cols and "party_kind" not in cols:
            await conn.execute(text("ALTER TABLE chat_messages RENAME TO chat_messages_old"))
        # chetga surilgan jadval (yangi yoki avvalgi muvaffaqiyatsiz urinishdan) —
        # indekslarini bo'shatamiz, aks holda create_all nom to'qnashuvida yiqiladi
        if await _table_exists(conn, "chat_messages_old"):
            await _drop_table_indexes(conn, "chat_messages_old")


async def _migrate_chat_post() -> None:
    """Eski yozishmalarni (chat_messages_old) yangi sxemaga ko'chiramiz."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        if not await _table_exists(conn, "chat_messages_old"):
            return
        insert_kw = "INSERT OR IGNORE" if conn.dialect.name == "sqlite" else "INSERT"
        await conn.execute(
            text(
                f"""
                {insert_kw} INTO chat_messages (id, party_kind, party_id, direction, text, is_read, created_at)
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
    """Global narxlarni boshlang'ich qiymatlar bilan to'ldiradi.

    Narxlar barcha hudud uchun bir xil — AppSetting kalitlarida saqlanadi
    (water_price / courier_rate / bottle_price). Faqat yo'q bo'lsa qo'shadi —
    mavjud (admin tahrirlagan) qiymatlarga tegmaydi.
    """
    from app.config import (
        BOTTLE_PRICE_DEFAULT,
        COURIER_RATE_DEFAULT,
        WATER_PRICE_DEFAULT,
    )
    from app.db.models import AppSetting

    defaults = {
        "water_price": WATER_PRICE_DEFAULT,
        "courier_rate": COURIER_RATE_DEFAULT,
        "bottle_price": BOTTLE_PRICE_DEFAULT,
    }
    async with SessionLocal() as s:
        for key, val in defaults.items():
            if await s.get(AppSetting, key) is None:
                s.add(AppSetting(key=key, value=str(val)))
        await s.commit()


async def _ensure_warehouse() -> None:
    """Ombor uchun standart mahsulotni (suv) bir marta qo'shadi.

    Sotuvda avtomatik chiqim shu `is_default=True` mahsulotning partiyalaridan
    bo'ladi. Allaqachon mavjud bo'lsa — tegmaymiz.
    """
    from sqlalchemy import select

    from app.db.models import Product

    async with SessionLocal() as s:
        exists = await s.execute(select(Product).where(Product.is_default == True))  # noqa: E712
        if exists.scalar_one_or_none() is None:
            s.add(Product(name="Suv (baklashka)", volume="19L", is_default=True))
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
        ("couriers", "latitude", "DOUBLE PRECISION"),
        ("couriers", "longitude", "DOUBLE PRECISION"),
        ("couriers", "geo_address", "TEXT"),
        ("users", "deleted_at", "DATETIME"),
        ("admins", "is_super", "BOOLEAN DEFAULT 0"),
        ("admins", "permissions", "VARCHAR(255) DEFAULT ''"),
        ("feedback", "party_kind", "VARCHAR(16) DEFAULT 'client'"),
        ("feedback", "courier_id", "INTEGER"),
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
        admin = res.scalar_one_or_none()
        if admin is None:
            session.add(
                Admin(
                    login=cfg.admin_login,
                    password_hash=hash_password(cfg.admin_password),
                    is_super=True,
                )
            )
            await session.commit()
        elif not admin.is_super:
            # .env dagi asosiy admin doimo super admin bo'lib qoladi
            admin.is_super = True
            await session.commit()
