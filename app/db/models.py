"""SQLAlchemy 2.0 modellari.

SQLite va PostgreSQL ikkalasida ham ishlaydigan turlar ishlatilgan
(BigInteger, DateTime, Boolean, Integer, String, Text).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.utils import now


class Base(DeclarativeBase):
    pass


class User(Base):
    """Mijoz. `phone` ayni paytda mijozning ID raqami hisoblanadi."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    lang: Mapped[str] = mapped_column(String(5), default="uz")
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(32), index=True)
    extra_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    geo_address: Mapped[str | None] = mapped_column(Text, nullable=True)  # geokodlash natijasi
    house: Mapped[str | None] = mapped_column(String(255), nullable=True)  # qo'lda: podyezd/xonadon
    region: Mapped[str] = mapped_column(String(128))  # tanlangan hudud nomi
    empty_bottles: Mapped[int] = mapped_column(Integer, default=0)  # bo'sh baklashka
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reminder_day: Mapped[int] = mapped_column(Integer, default=0)  # oxirgi yuborilgan eslatma chegarasi

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Courier(Base):
    __tablename__ = "couriers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(32))
    lang: Mapped[str] = mapped_column(String(5), default="uz")
    region: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    orders: Mapped[list["Order"]] = relationship(back_populates="courier")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("couriers.id"), nullable=True)

    region: Mapped[str] = mapped_column(String(128))
    count: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[int] = mapped_column(Integer)

    # Buyurtma uchun yetkazish manzili (har safar istalgan joy bo'lishi mumkin)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    geo_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # new -> process (kuryerga biriktirilgan) -> delivered -> canceled
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)

    # Yetkazilgandan keyin kuryer kiritadi:
    delivered_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    empty_returned: Mapped[int | None] = mapped_column(Integer, nullable=True)   # qaytarib olingan bo'sh
    empty_left: Mapped[int | None] = mapped_column(Integer, nullable=True)       # mijozda qolgan bo'sh

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="orders")
    courier: Mapped["Courier | None"] = relationship(back_populates="orders")


class ChatMessage(Base):
    """Admin <-> kuryer/mijoz yozishmasi (umumiy).

    `party_kind` — suhbatdosh turi: 'courier' (kuryer) yoki 'client' (mijoz).
    `party_id`   — o'sha kuryer (couriers.id) yoki mijoz (users.id) IDsi.
    `direction`  — 'out' (admin -> suhbatdosh) yoki 'in' (suhbatdosh -> admin).
    `is_read`    — admin suhbatdoshdan kelgan xabarni o'qidimi (badge uchun).
    """
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    party_kind: Mapped[str] = mapped_column(String(16), index=True)
    party_id: Mapped[int] = mapped_column(Integer, index=True)
    direction: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Pricing(Base):
    """Hudud bo'yicha narxlar — admin paneldan tahrirlanadi.

    Boshlang'ich qiymatlar config.REGIONS dan seed qilinadi (init_db).
    """
    __tablename__ = "pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    region_name: Mapped[str] = mapped_column(String(128))
    water_price: Mapped[int] = mapped_column(Integer)    # 1 dona suv narxi (so'm)
    courier_rate: Mapped[int] = mapped_column(Integer)   # kuryerga 1 dona uchun (so'm)


class AppSetting(Base):
    """Global sozlamalar (kalit-qiymat) — masalan baklashka narxi."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class BonusPromo(Base):
    """Mijoz bonusi — chegara oshganda admin uchun eslatma sifatida yaratiladi."""
    __tablename__ = "bonus_promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    threshold: Mapped[int] = mapped_column(Integer)  # masalan 100, 200, ...
    code: Mapped[str] = mapped_column(String(32))
    reward: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/sent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    user: Mapped["User"] = relationship()


# ============================ OMBOR (SKLAD) ============================

class Product(Base):
    """Ombordagi mahsulot (suv turi).

    Hozircha tizim bitta standart mahsulot — "Suv (baklashka)" — sotadi.
    `is_default=True` bo'lgan mahsulot sotuvda avtomatik chiqimga ishlatiladi.
    Kelajakda turli hajmlar (0.5L/1L/19L) qo'shilsa, shu jadval kengayadi.
    """
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    volume: Mapped[str | None] = mapped_column(String(32), nullable=True)  # masalan "19L"
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    batches: Mapped[list["Batch"]] = relationship(back_populates="product")


class Batch(Base):
    """Kirim partiyasi — omborga bir martalik kirim.

    Har bir partiya alohida sotib olish narxida bo'lishi mumkin. FIFO chiqim
    `received_at` (keyin `id`) bo'yicha eng eski partiyadan boshlanadi.
    `remaining` — partiyadan hali sotilmagan (qolgan) dona.
    """
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_no: Mapped[str] = mapped_column(String(32), index=True)  # partiya raqami
    quantity: Mapped[int] = mapped_column(Integer)            # kirim qilingan dona
    unit_cost: Mapped[int] = mapped_column(Integer)           # 1 dona sotib olish narxi (so'm)
    total_cost: Mapped[int] = mapped_column(Integer)          # = quantity * unit_cost
    remaining: Mapped[int] = mapped_column(Integer, index=True)  # qoldiq dona
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    product: Mapped["Product"] = relationship(back_populates="batches")


class StockMovement(Base):
    """Ombor harakati (audit/tarix): KIRIM ('in') yoki CHIQIM ('out').

    Chiqimda `unit_price` (sotilgan narx), `unit_cost` (partiya tannarxi) va
    `order_id` (qaysi buyurtma) yoziladi — foyda shu yerdan hisoblanadi.
    `batch_id` NULL bo'lsa — qoldiq yetmagan "kamomad" chiqimi (ogohlantirish).
    """
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)  # 'in' | 'out'
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[int] = mapped_column(Integer, default=0)   # dona tannarxi (so'm)
    unit_price: Mapped[int] = mapped_column(Integer, default=0)  # dona sotilgan narx (chiqim)
    shortfall: Mapped[bool] = mapped_column(Boolean, default=False)  # qoldiq yetmadi
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
