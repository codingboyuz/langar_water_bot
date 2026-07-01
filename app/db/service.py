"""Ma'lumotlar bazasi bilan ishlovchi yordamchi funksiyalar (service layer).

Bu qatlam botlar va admin panel tomonidan birgalikda ishlatiladi, shunday
qilib biznes-mantiq bitta joyda turadi.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload

from app import events
from app.config import (
    BOTTLE_PRICE_DEFAULT,
    CLIENT_ARCHIVE_DAYS,
    CLIENT_BONUS_STEP,
    COURIER_RATE_DEFAULT,
    REGION_BY_NAME,
    WATER_PRICE_DEFAULT,
)
from app.db.base import SessionLocal
from app.db.models import (
    Admin,
    AppSetting,
    BonusPromo,
    ChatMessage,
    Courier,
    Feedback,
    Order,
    Penalty,
    StockMovement,
    User,
)
from app.security import hash_password, verify_password
from app.utils import now

# Buyurtma "jarayonda" deb hisoblanadigan holatlar (yangi va yakunlangan oralig'i):
#   assigned      — kuryerga biriktirildi, lekin kuryer hali qabul qilmadi
#   process       — kuryer "Jarayonda" tugmasini bosdi (qabul qildi)
#   await_confirm — kuryer "Yetkazildi" bosdi, mijoz tasdig'i kutilmoqda
ACTIVE_STATUSES = ("assigned", "process", "await_confirm")

# Chat: suhbatdosh shu vaqt ichida yozgan bo'lsa "onlayn" deb ko'rsatiladi.
# (Telegram bot API haqiqiy online holatni bermaydi — oxirgi faollik bo'yicha taxmin.)
CHAT_ONLINE_WINDOW = timedelta(minutes=3)


# ============================ MIJOZ (USER) ============================

async def get_user_by_tg(telegram_id: int) -> User | None:
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.telegram_id == telegram_id))
        return res.scalar_one_or_none()


async def get_user_by_id(user_id: int) -> User | None:
    async with SessionLocal() as s:
        return await s.get(User, user_id)


async def create_user(data: dict) -> User:
    async with SessionLocal() as s:
        user = User(**data)
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


async def update_user_lang(telegram_id: int, lang: str) -> None:
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        if user:
            user.lang = lang
            await s.commit()


async def update_user_location(
    telegram_id: int, latitude: float, longitude: float, geo_address: str | None
) -> None:
    """Mijoz Sozlamalardan lokatsiya/manzilini yangilaydi."""
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        if user:
            user.latitude = latitude
            user.longitude = longitude
            user.geo_address = geo_address
            await s.commit()


# ---- Yumshoq o'chirish (arxiv) / tiklash / butunlay o'chirish ----

async def soft_delete_user(user_id: int) -> None:
    """Mijozni arxivlaydi (yumshoq o'chirish). Ma'lumotlari saqlanadi —
    CLIENT_ARCHIVE_DAYS kun ichida qaytsa, profil tiklanadi."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if u and u.deleted_at is None:
            u.deleted_at = now()
            await s.commit()


async def restore_user(user_id: int) -> bool:
    """Arxivlangan mijozni qayta faollashtiradi. Tiklangan bo'lsa True."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if u and u.deleted_at is not None:
            u.deleted_at = None
            await s.commit()
            return True
        return False


async def restore_user_by_tg(telegram_id: int) -> bool:
    """Mijoz botga qaytganda (telegram_id bo'yicha) profilni tiklaydi."""
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.telegram_id == telegram_id))
        u = res.scalar_one_or_none()
        if u and u.deleted_at is not None:
            u.deleted_at = None
            await s.commit()
            return True
        return False


async def hard_delete_user(user_id: int) -> None:
    """Mijozni butunlay o'chiradi (qaytarib bo'lmaydi).

    Buyurtmalari ham o'chadi, lekin ombor harakatlari (StockMovement) saqlanib
    qoladi — moliyaviy hisobot (foyda/zarar) buzilmaydi; faqat `order_id` bog'i
    uziladi. Bonus va chat yozishmalari ham tozalanadi.
    """
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u:
            return
        order_ids = (
            await s.execute(select(Order.id).where(Order.user_id == user_id))
        ).scalars().all()
        if order_ids:
            # Ombor harakatlarini tarix uchun saqlaymiz — faqat bog'ni uzamiz
            await s.execute(
                StockMovement.__table__.update()
                .where(StockMovement.order_id.in_(order_ids))
                .values(order_id=None)
            )
            await s.execute(Order.__table__.delete().where(Order.user_id == user_id))
        await s.execute(BonusPromo.__table__.delete().where(BonusPromo.user_id == user_id))
        await s.execute(Penalty.__table__.delete().where(Penalty.user_id == user_id))
        await s.execute(Feedback.__table__.delete().where(Feedback.user_id == user_id))
        await s.execute(
            ChatMessage.__table__.delete().where(
                and_(ChatMessage.party_kind == "client", ChatMessage.party_id == user_id)
            )
        )
        await s.delete(u)
        await s.commit()


async def list_archived_clients() -> list[dict]:
    """Arxivlangan (yumshoq o'chirilgan) mijozlar — eng yangi avval."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(User).where(User.deleted_at.is_not(None)).order_by(User.deleted_at.desc())
        )
        users = res.scalars().all()
    out = []
    for u in users:
        purge_at = u.deleted_at + timedelta(days=CLIENT_ARCHIVE_DAYS)
        days_left = (purge_at - now()).days
        out.append(
            {
                "user_id": u.id,
                "name": u.full_name,
                "phone": u.phone,
                "region": u.region,
                "deleted_at": u.deleted_at,
                "purge_at": purge_at,
                "days_left": max(days_left, 0),
            }
        )
    return out


async def purge_expired_users() -> int:
    """CLIENT_ARCHIVE_DAYS kundan oshib ketgan arxiv mijozlarni butunlay
    o'chiradi. O'chirilganlar sonini qaytaradi (scheduler chaqiradi)."""
    cutoff = now() - timedelta(days=CLIENT_ARCHIVE_DAYS)
    async with SessionLocal() as s:
        res = await s.execute(
            select(User.id).where(
                and_(User.deleted_at.is_not(None), User.deleted_at < cutoff)
            )
        )
        ids = list(res.scalars().all())
    for uid in ids:
        await hard_delete_user(uid)
    return len(ids)


# ============================ BUYURTMA (ORDER) ============================

async def create_order(
    user: User,
    region_name: str,
    count: int,
    latitude: float | None = None,
    longitude: float | None = None,
    geo_address: str | None = None,
) -> Order:
    async with SessionLocal() as s:
        # narx barcha hududda bir xil — global sozlamadan olinadi
        unit_price = await _setting_int(s, "water_price", WATER_PRICE_DEFAULT)
        order = Order(
            user_id=user.id,
            region=region_name,
            count=count,
            unit_price=unit_price,
            total_price=unit_price * count,
            status="new",
            latitude=latitude,
            longitude=longitude,
            geo_address=geo_address,
        )
        s.add(order)
        # mijozning oxirgi buyurtma vaqtini yangilaymiz (eslatma uchun)
        db_user = await s.get(User, user.id)
        if db_user:
            db_user.last_order_at = now()
            db_user.last_reminder_day = 0
            db_user.deleted_at = None  # buyurtma berdi — arxivdan tiklanadi
        await s.commit()
        await s.refresh(order)
    # admin paneliga realtime xabar — yangi buyurtma keldi
    events.publish("order_new", {"order_id": order.id})
    return order


async def get_user_orders(user_id: int) -> Sequence[Order]:
    async with SessionLocal() as s:
        res = await s.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        )
        return res.scalars().all()


async def total_delivered_bottles(user_id: int) -> int:
    async with SessionLocal() as s:
        res = await s.execute(
            select(func.coalesce(func.sum(Order.delivered_count), 0)).where(
                Order.user_id == user_id, Order.status == "delivered"
            )
        )
        return int(res.scalar_one() or 0)


async def list_orders(status: str | None = None) -> Sequence[Order]:
    async with SessionLocal() as s:
        stmt = (
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.courier))
            .order_by(Order.created_at.desc())
        )
        if status == "process":
            # "Jarayonda" — yangi va yakunlangan oralig'idagi barcha holatlar
            stmt = stmt.where(Order.status.in_(ACTIVE_STATUSES))
        elif status:
            stmt = stmt.where(Order.status == status)
        res = await s.execute(stmt)
        return res.scalars().all()


async def get_order(order_id: int) -> Order | None:
    async with SessionLocal() as s:
        res = await s.execute(
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.courier))
            .where(Order.id == order_id)
        )
        return res.scalar_one_or_none()


async def assign_order(order_id: int, courier_id: int) -> Order | None:
    """Adminga: buyurtmani kuryerga biriktiradi -> status 'assigned'.

    Kuryer "Jarayonda" tugmasini bosmaguncha holat 'assigned' (qabul qilinmagan)
    bo'lib turadi.
    """
    async with SessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return None
        order.courier_id = courier_id
        order.status = "assigned"
        order.assigned_at = now()
        await s.commit()
    events.publish("order_update", {"order_id": order_id, "status": "assigned"})
    return await get_order(order_id)


async def set_order_process(order_id: int) -> None:
    """Kuryer 'Jarayonda' tugmasini bosganda (qabul qildi)."""
    async with SessionLocal() as s:
        order = await s.get(Order, order_id)
        if order:
            order.status = "process"
            await s.commit()
    events.publish("order_update", {"order_id": order_id, "status": "process"})


async def mark_delivered(
    order_id: int, delivered_count: int, empty_returned: int, empty_left: int
) -> Order | None:
    """Kuryer 'Yetkazildi' — suv/bo'sh baklashka hisobini yozadi.

    Holat 'await_confirm' bo'ladi: kuryer yetkazdi, ammo buyurtma mijoz
    tasdiqlamaguncha yakunlanmaydi (statistikaga 'delivered' bo'lib o'tmaydi).
    """
    async with SessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return None
        order.status = "await_confirm"
        order.delivered_count = delivered_count
        order.empty_returned = empty_returned
        order.empty_left = empty_left
        order.delivered_at = now()

        user = await s.get(User, order.user_id)
        if user:
            # mijozda qolgan bo'sh baklashka miqdorini yangilaymiz
            user.empty_bottles = empty_left
        await s.commit()
    events.publish("order_update", {"order_id": order_id, "status": "await_confirm"})
    return await get_order(order_id)


async def confirm_received(order_id: int) -> Order | None:
    """Mijoz 'Buyurtmani qabul qildim' tugmasini bosadi -> buyurtma yakunlanadi.

    Holat 'delivered' bo'ladi va shu paytdan boshlab statistikaga (tushum,
    suv, kuryer haqi, bonus) hisobga olinadi.
    """
    async with SessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order or order.status == "delivered":
            return None
        order.status = "delivered"
        if order.delivered_at is None:
            order.delivered_at = now()
        # ombor chiqimi uchun kerakli qiymatlar (sessiya yopilgandan keyin ham)
        sold_count = order.delivered_count if order.delivered_count is not None else order.count
        unit_price = order.unit_price
        await s.commit()
    # Ombordan FIFO chiqim: eng eski partiyadan kamaytiramiz, foyda yoziladi.
    # (suv allaqachon yetkazilgan — qoldiq yetmasa bloklamaydi, kamomad belgilanadi)
    await _warehouse_outbound(order_id, sold_count, unit_price)
    await _check_client_bonus(order_id)
    events.publish("order_update", {"order_id": order_id, "status": "delivered"})
    return await get_order(order_id)


async def _warehouse_outbound(order_id: int, count: int, unit_price: int) -> None:
    """Sotuv yakunlanganda ombordan FIFO chiqim (xatolik savdoni to'xtatmaydi)."""
    try:
        from app.db import warehouse as wh

        await wh.fifo_outbound(order_id, count, unit_price)
    except Exception:
        # ombor chiqimi savdoni buzmasin — log darajasida e'tiborsiz qoldiramiz
        pass


# ============================ BONUS ============================

async def _check_client_bonus(order_id: int) -> None:
    """Yetkazilgandan keyin: mijoz yangi 100-lik chegaradan o'tdimi?"""
    order = await get_order(order_id)
    if not order:
        return
    total = await total_delivered_bottles(order.user_id)
    reached = (total // CLIENT_BONUS_STEP) * CLIENT_BONUS_STEP
    if reached < CLIENT_BONUS_STEP:
        return
    async with SessionLocal() as s:
        exists = await s.execute(
            select(BonusPromo).where(
                BonusPromo.user_id == order.user_id, BonusPromo.threshold == reached
            )
        )
        if exists.scalar_one_or_none() is None:
            code = f"BONUS-{order.user_id}-{reached}"
            s.add(
                BonusPromo(
                    user_id=order.user_id,
                    threshold=reached,
                    code=code,
                    status="pending",
                )
            )
            await s.commit()


async def list_pending_bonuses() -> Sequence[BonusPromo]:
    async with SessionLocal() as s:
        res = await s.execute(
            select(BonusPromo)
            .options(selectinload(BonusPromo.user))
            .where(BonusPromo.status == "pending")
            .order_by(BonusPromo.created_at.desc())
        )
        return res.scalars().all()


async def mark_bonus_sent(bonus_id: int) -> None:
    async with SessionLocal() as s:
        b = await s.get(BonusPromo, bonus_id)
        if b:
            b.status = "sent"
            await s.commit()


# ============================ KURYER ============================

async def list_couriers(active_only: bool = False) -> Sequence[Courier]:
    async with SessionLocal() as s:
        stmt = select(Courier).order_by(Courier.name)
        if active_only:
            stmt = stmt.where(Courier.is_active == True)  # noqa: E712
        res = await s.execute(stmt)
        return res.scalars().all()


async def get_courier(courier_id: int) -> Courier | None:
    async with SessionLocal() as s:
        return await s.get(Courier, courier_id)


async def get_courier_by_tg(telegram_id: int) -> Courier | None:
    async with SessionLocal() as s:
        res = await s.execute(select(Courier).where(Courier.telegram_id == telegram_id))
        return res.scalar_one_or_none()


async def courier_detail(courier_id: int) -> dict | None:
    """Bitta kuryer bo'yicha to'liq dashboard ma'lumotlari.

    Profil, ish unumdorligi (KPI), ishlagan haqi, bajarilgan va bajarilishi
    kerak bo'lgan (marshrut tartibida) buyurtmalar.
    """
    from app.routing import order_route

    async with SessionLocal() as s:
        courier = await s.get(Courier, courier_id)
        if not courier:
            return None

        # kuryer stavkasi — global (barcha hududda bir xil)
        rate = await _setting_int(s, "courier_rate", COURIER_RATE_DEFAULT)

        res = await s.execute(
            select(Order)
            .options(selectinload(Order.user))
            .where(Order.courier_id == courier_id)
            .order_by(Order.created_at.desc())
        )
        orders = list(res.scalars().all())

    delivered = [o for o in orders if o.status == "delivered"]
    pending = [o for o in orders if o.status != "delivered"]

    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    bottles = sum(o.delivered_count or 0 for o in delivered)
    bottles_today = sum(
        (o.delivered_count or 0)
        for o in delivered
        if o.delivered_at and o.delivered_at >= today
    )
    collected = sum(o.total_price for o in delivered)

    return {
        "courier": courier,
        "rate": rate,
        "bottles": bottles,
        "bottles_today": bottles_today,
        "orders_done": len(delivered),
        "collected": collected,
        "salary": bottles * rate,
        "salary_today": bottles_today * rate,
        "delivered": delivered,
        "pending": order_route(pending),   # marshrut tartibida (yo'l-yo'lakay belgili)
        "pending_count": len(pending),
    }


async def register_courier(
    telegram_id: int,
    name: str,
    phone: str,
    region: str,
    lang: str,
    latitude: float | None = None,
    longitude: float | None = None,
    geo_address: str | None = None,
) -> Courier:
    """Kuryer bot orqali o'zi ro'yxatdan o'tadi.

    Agar shu Telegram ID bilan kuryer allaqachon mavjud bo'lsa (masalan, admin
    oldindan qo'shgan) — ma'lumotlarini yangilaymiz, yangisini yaratmaymiz.
    """
    async with SessionLocal() as s:
        res = await s.execute(select(Courier).where(Courier.telegram_id == telegram_id))
        c = res.scalar_one_or_none()
        if c is None:
            c = Courier(telegram_id=telegram_id)
            s.add(c)
        c.name = name
        c.phone = phone
        c.region = region
        c.lang = lang
        c.latitude = latitude
        c.longitude = longitude
        c.geo_address = geo_address
        c.is_active = True
        await s.commit()
        await s.refresh(c)
        return c


async def set_courier_active(courier_id: int, active: bool) -> None:
    """Kuryerni vaqtinchalik chetlashtirish / qayta faollashtirish.

    `is_active=False` bo'lsa kuryer buyurtma biriktirish ro'yxatida ko'rinmaydi,
    lekin hisob-kitob ma'lumotlari saqlanib qoladi.
    """
    async with SessionLocal() as s:
        c = await s.get(Courier, courier_id)
        if c:
            c.is_active = active
            await s.commit()


async def delete_courier(courier_id: int) -> None:
    """Kuryerni butunlay o'chiradi. Bog'liq buyurtmalardagi courier_id NULL bo'ladi."""
    async with SessionLocal() as s:
        c = await s.get(Courier, courier_id)
        if c:
            # bog'liq buyurtmalarni 'egasiz' qoldiramiz (FK NULL) — tarix o'chmaydi
            await s.execute(
                Order.__table__.update()
                .where(Order.courier_id == courier_id)
                .values(courier_id=None)
            )
            await s.delete(c)
            await s.commit()


# ============================ CHAT (admin <-> kuryer/mijoz) ============================

async def add_chat_message(party_kind: str, party_id: int, direction: str, text: str) -> ChatMessage:
    """Yozishma xabarini saqlaydi.

    party_kind: 'courier' yoki 'client'.
    direction:  'out' (admin yozdi) yoki 'in' (suhbatdosh yozdi).
    Adminning o'z xabari darhol 'o'qilgan' deb belgilanadi.
    """
    async with SessionLocal() as s:
        m = ChatMessage(
            party_kind=party_kind,
            party_id=party_id,
            direction=direction,
            text=text,
            is_read=(direction == "out"),
        )
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def get_chat_messages_after(
    party_kind: str, party_id: int, after_id: int = 0, limit: int = 200
) -> Sequence[ChatMessage]:
    """`after_id` dan keyingi yangi xabarlar (qo'shimcha yuklash / polling uchun)."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(ChatMessage)
            .where(
                ChatMessage.party_kind == party_kind,
                ChatMessage.party_id == party_id,
                ChatMessage.id > after_id,
            )
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
        return list(res.scalars().all())


async def mark_chat_read(party_kind: str, party_id: int) -> None:
    """Suhbatdoshdan kelgan o'qilmagan xabarlarni o'qilgan deb belgilaydi."""
    async with SessionLocal() as s:
        await s.execute(
            ChatMessage.__table__.update()
            .where(
                ChatMessage.party_kind == party_kind,
                ChatMessage.party_id == party_id,
                ChatMessage.direction == "in",
                ChatMessage.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        await s.commit()


async def chat_unread_total(party_kind: str | None = None) -> int:
    """Suhbatdoshlardan kelgan o'qilmagan xabarlar soni (sidebar/tab badge)."""
    conds = [ChatMessage.direction == "in", ChatMessage.is_read == False]  # noqa: E712
    if party_kind:
        conds.append(ChatMessage.party_kind == party_kind)
    async with SessionLocal() as s:
        res = await s.execute(select(func.count(ChatMessage.id)).where(*conds))
        return int(res.scalar_one() or 0)


async def chat_overview(party_kind: str) -> list[dict]:
    """Chat ro'yxati: har bir suhbatdosh + oxirgi xabar + o'qilmaganlar soni.

    'courier' — barcha kuryerlar; 'client' — faqat yozishmasi bor mijozlar.
    Xabari borlar tepada (oxirgi xabar vaqti bo'yicha).
    """
    async with SessionLocal() as s:
        # o'qilmaganlar soni (suhbatdosh bo'yicha)
        ures = await s.execute(
            select(ChatMessage.party_id, func.count(ChatMessage.id))
            .where(
                ChatMessage.party_kind == party_kind,
                ChatMessage.direction == "in",
                ChatMessage.is_read == False,  # noqa: E712
            )
            .group_by(ChatMessage.party_id)
        )
        unread = {pid: int(c) for pid, c in ures.all()}
        # har bir suhbatdoshning oxirgi xabari + oxirgi KIRUVCHI (undan kelgan) xabari
        msgs = list((await s.execute(
            select(ChatMessage)
            .where(ChatMessage.party_kind == party_kind)
            .order_by(ChatMessage.id.desc())
        )).scalars().all())
        last_by: dict[int, ChatMessage] = {}
        last_in_by: dict[int, ChatMessage] = {}
        for m in msgs:
            last_by.setdefault(m.party_id, m)
            if m.direction == "in":
                last_in_by.setdefault(m.party_id, m)

        if party_kind == "courier":
            rows = list((await s.execute(select(Courier).order_by(Courier.name))).scalars().all())
            parties = [
                {"id": c.id, "name": c.name, "phone": c.phone, "region": c.region, "tg": c.telegram_id}
                for c in rows
            ]
        else:
            # barcha mijozlar (kuryerlar kabi — yozishmasi bo'lmasa ham ro'yxatda turadi)
            rows = list((await s.execute(select(User).order_by(User.full_name))).scalars().all())
            parties = [
                {"id": u.id, "name": u.full_name, "phone": u.phone, "region": u.region, "tg": u.telegram_id}
                for u in rows
            ]

    cutoff = now() - CHAT_ONLINE_WINDOW
    items = []
    for p in parties:
        lm = last_by.get(p["id"])
        lm_in = last_in_by.get(p["id"])
        items.append({
            "party": p,
            "last_text": lm.text if lm else None,
            "last_at": lm.created_at if lm else None,
            "last_dir": lm.direction if lm else None,
            "last_in_at": lm_in.created_at if lm_in else None,
            "online": bool(lm_in and lm_in.created_at and lm_in.created_at >= cutoff),
            "unread": unread.get(p["id"], 0),
        })
    items.sort(key=lambda x: (x["last_at"] is None, -(x["last_at"].timestamp() if x["last_at"] else 0)))
    return items


# ============================ STATISTIKA ============================

async def dashboard_counts() -> dict:
    async with SessionLocal() as s:
        async def count(stmt):
            return int((await s.execute(stmt)).scalar_one() or 0)

        total = await count(select(func.count(Order.id)))
        new = await count(select(func.count(Order.id)).where(Order.status == "new"))
        process = await count(
            select(func.count(Order.id)).where(Order.status.in_(ACTIVE_STATUSES))
        )
        delivered = await count(select(func.count(Order.id)).where(Order.status == "delivered"))
        clients = await count(select(func.count(User.id)).where(User.deleted_at.is_(None)))
        couriers = await count(select(func.count(Courier.id)))
        revenue = int(
            (
                await s.execute(
                    select(func.coalesce(func.sum(Order.total_price), 0)).where(
                        Order.status == "delivered"
                    )
                )
            ).scalar_one()
            or 0
        )
        bottles = int(
            (
                await s.execute(
                    select(func.coalesce(func.sum(Order.delivered_count), 0)).where(
                        Order.status == "delivered"
                    )
                )
            ).scalar_one()
            or 0
        )
        # baklashka shtraflari — umumiy tushumga qo'shiladi
        penalties = int(
            (
                await s.execute(select(func.coalesce(func.sum(Penalty.total), 0)))
            ).scalar_one()
            or 0
        )
    return {
        "total": total,
        "new": new,
        "process": process,
        "delivered": delivered,
        "clients": clients,
        "couriers": couriers,
        "water_revenue": revenue,           # suv savdosidan tushum
        "penalties": penalties,             # baklashka shtraflari
        "revenue": revenue + penalties,     # umumiy tushum
        "bottles": bottles,
    }


async def orders_per_day(days: int = 14) -> list[dict]:
    """Oxirgi `days` kun bo'yicha suv harakati (chart uchun).

    Ikki qator qaytadi:
      - `delivered`: yetkazilgan suv (yetkazilgan sanasi bo'yicha)
      - `process`:   jarayondagi suv (buyurtma sanasi bo'yicha)
    Sanalar uzluksiz — buyurtma bo'lmagan kun ham 0 bilan ko'rinadi.
    """
    base = now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = base - timedelta(days=days - 1)
    async with SessionLocal() as s:
        # yetkazilgan — yetkazilgan sanasi va yetkazilgan dona bo'yicha
        dres = await s.execute(
            select(
                func.date(Order.delivered_at),
                func.coalesce(func.sum(Order.delivered_count), 0),
            )
            .where(Order.status == "delivered", Order.delivered_at >= start)
            .group_by(func.date(Order.delivered_at))
        )
        delivered = {str(r[0]): int(r[1]) for r in dres.all()}
        # jarayonda — buyurtma sanasi va buyurtma dona bo'yicha
        pres = await s.execute(
            select(
                func.date(Order.created_at),
                func.coalesce(func.sum(Order.count), 0),
            )
            .where(Order.status.in_(ACTIVE_STATUSES), Order.created_at >= start)
            .group_by(func.date(Order.created_at))
        )
        process = {str(r[0]): int(r[1]) for r in pres.all()}
    out: list[dict] = []
    for i in range(days - 1, -1, -1):
        day = (base - timedelta(days=i)).date().isoformat()
        dv = delivered.get(day, 0)
        pv = process.get(day, 0)
        out.append({
            "date": day,
            "delivered": dv,
            "process": pv,
        })
    return out


async def orders_by_region() -> list[dict]:
    """Hududlar bo'yicha buyurtmalar: yetkazilgan va jarayondagilarni qamrab oladi."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(Order.region, func.count(Order.id))
            .where(Order.status.in_(("delivered",) + ACTIVE_STATUSES))
            .group_by(Order.region)
        )
        rows = res.all()
    return [{"region": r[0], "count": int(r[1])} for r in rows]


async def top_clients(limit: int = 20) -> list[dict]:
    """Mijozlar reytingi — yetkazilgan suv miqdori bo'yicha.

    OUTER JOIN: hali biror marta yetkazib olmagan mijozlar ham (0 bilan)
    ro'yxatda ko'rinadi.
    """
    async with SessionLocal() as s:
        res = await s.execute(
            select(
                User.id,
                User.full_name,
                User.phone,
                User.region,
                func.coalesce(func.sum(Order.delivered_count), 0).label("bottles"),
                func.count(Order.id).label("orders"),
            )
            .outerjoin(
                Order,
                and_(Order.user_id == User.id, Order.status == "delivered"),
            )
            .where(User.deleted_at.is_(None))  # arxivlanganlar ko'rinmaydi
            .group_by(User.id)
            .order_by(func.coalesce(func.sum(Order.delivered_count), 0).desc())
            .limit(limit)
        )
        rows = res.all()
    ptotals = await penalty_totals_by_user()
    return [
        {
            "user_id": r[0],
            "name": r[1],
            "phone": r[2],
            "region": r[3],
            "bottles": int(r[4]),
            "orders": int(r[5]),
            "bonus_due": int(r[4]) >= CLIENT_BONUS_STEP,
            "penalty_total": ptotals.get(r[0], 0),
        }
        for r in rows
    ]


def _period_start(period: str) -> datetime | None:
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return today
    if period == "week":
        return today - timedelta(days=today.weekday())
    if period == "month":
        return today.replace(day=1)
    return None  # 'all'


async def courier_stats(period: str = "all") -> list[dict]:
    """Har bir kuryer bo'yicha: yetkazilgan suv soni va ish haqi.

    Ish haqi = yetkazilgan dona × global kuryer stavkasi (barcha hududda bir xil).
    """
    start = _period_start(period)
    # 'delivered' shartlari OUTER JOIN ON ichida — shunda yetkazmagan kuryer
    # ham ro'yxatda (0 bilan) qoladi.
    join_cond = [Order.courier_id == Courier.id, Order.status == "delivered"]
    if start is not None:
        join_cond.append(Order.delivered_at >= start)
    async with SessionLocal() as s:
        stmt = (
            select(
                Courier.id,
                Courier.name,
                Courier.phone,
                Courier.region,
                func.coalesce(func.sum(Order.delivered_count), 0).label("bottles"),
                func.count(Order.id).label("orders"),
                func.coalesce(func.sum(Order.total_price), 0).label("collected"),
                Courier.is_active,
            )
            .outerjoin(Order, and_(*join_cond))
            .group_by(Courier.id)
            .order_by(func.coalesce(func.sum(Order.delivered_count), 0).desc())
        )
        res = await s.execute(stmt)
        rows = res.all()
        # kuryer stavkasi — global (barcha hududda bir xil)
        rate = await _setting_int(s, "courier_rate", COURIER_RATE_DEFAULT)

    from app.config import COURIER_DAILY_BONUS_AMOUNT, COURIER_DAILY_BONUS_STEP

    out = []
    for r in rows:
        bottles = int(r[4])
        salary = bottles * rate
        bonus = (bottles // COURIER_DAILY_BONUS_STEP) * COURIER_DAILY_BONUS_AMOUNT if period == "day" else 0
        out.append(
            {
                "courier_id": r[0],
                "name": r[1],
                "phone": r[2],
                "region": r[3],
                "rate": rate,
                "bottles": bottles,
                "orders": int(r[5]),
                "collected": int(r[6]),  # mijozlardan yig'ilgan pul
                "salary": salary,        # kuryer haqi
                "bonus": bonus,
                "to_admin": int(r[6]) - salary - bonus,  # adminga topshiriladigan
                "is_active": bool(r[7]),
            }
        )
    return out


# ============================ NARXLAR (global) ============================
# Narxlar barcha hududda bir xil — AppSetting kalitlarida saqlanadi:
#   water_price   — 1 dona suv narxi
#   courier_rate  — kuryerga 1 dona uchun
#   bottle_price  — 1 dona baklashka shtrafi (qaytarilmasa)

async def _setting_int(s, key: str, default: int = 0) -> int:
    """Berilgan sessiyada AppSetting qiymatini butun son sifatida o'qiydi."""
    st = await s.get(AppSetting, key)
    try:
        return int(st.value) if st else default
    except (TypeError, ValueError):
        return default


async def get_pricing() -> dict:
    """Joriy global narxlar: {water_price, courier_rate, bottle_price}."""
    async with SessionLocal() as s:
        return {
            "water_price": await _setting_int(s, "water_price", WATER_PRICE_DEFAULT),
            "courier_rate": await _setting_int(s, "courier_rate", COURIER_RATE_DEFAULT),
            "bottle_price": await _setting_int(s, "bottle_price", BOTTLE_PRICE_DEFAULT),
        }


async def get_bottle_price() -> int:
    async with SessionLocal() as s:
        return await _setting_int(s, "bottle_price", BOTTLE_PRICE_DEFAULT)


async def update_pricing_global(
    water_price: int | None = None,
    courier_rate: int | None = None,
    bottle_price: int | None = None,
) -> None:
    """Global narxlarni yangilaydi (None bo'lganlarga tegmaydi)."""
    async with SessionLocal() as s:
        for key, val in (
            ("water_price", water_price),
            ("courier_rate", courier_rate),
            ("bottle_price", bottle_price),
        ):
            if val is None:
                continue
            v = str(max(0, int(val)))
            st = await s.get(AppSetting, key)
            if st is None:
                s.add(AppSetting(key=key, value=v))
            else:
                st.value = v
        await s.commit()


# ============================ SHTRAF (baklashka) ============================

async def add_penalty(user_id: int, count: int, note: str | None = None) -> Penalty | None:
    """Mijozga baklashka shtrafini qo'lda yozadi (faqat son kiritiladi).

    Narx joriy `bottle_price` dan olinadi — admin o'zgartira olmaydi.
    """
    try:
        count = int(count)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None
    async with SessionLocal() as s:
        user = await s.get(User, user_id)
        if not user:
            return None
        unit_price = await _setting_int(s, "bottle_price", BOTTLE_PRICE_DEFAULT)
        p = Penalty(
            user_id=user_id,
            count=count,
            unit_price=unit_price,
            total=count * unit_price,
            note=(note or "").strip() or None,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def user_penalty_total(user_id: int) -> int:
    async with SessionLocal() as s:
        return int(
            (
                await s.execute(
                    select(func.coalesce(func.sum(Penalty.total), 0)).where(
                        Penalty.user_id == user_id
                    )
                )
            ).scalar_one()
            or 0
        )


async def penalty_totals_by_user() -> dict[int, int]:
    """Har bir mijozning umumiy shtrafi: {user_id: total}."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(Penalty.user_id, func.coalesce(func.sum(Penalty.total), 0)).group_by(
                Penalty.user_id
            )
        )
        return {r[0]: int(r[1]) for r in res.all()}


async def total_penalties() -> int:
    """Barcha shtraflar jami (umumiy tushumga qo'shiladi)."""
    async with SessionLocal() as s:
        return int(
            (
                await s.execute(select(func.coalesce(func.sum(Penalty.total), 0)))
            ).scalar_one()
            or 0
        )


# ============================ ADMIN AUTH ============================

async def check_admin(login: str, password: str) -> Admin | None:
    async with SessionLocal() as s:
        res = await s.execute(select(Admin).where(Admin.login == login))
        admin = res.scalar_one_or_none()
        if admin and verify_password(password, admin.password_hash):
            return admin
        return None


# ---- Operatorlar (super admin boshqaradi) ----

def _clean_perms(sections: list[str] | None, allowed: set[str]) -> str:
    """Ruxsat etilgan bo'lim kalitlarini tartiblab, CSV qatorga aylantiradi."""
    if not sections:
        return ""
    seen = [s for s in dict.fromkeys(sections) if s in allowed]
    return ",".join(seen)


async def list_admins() -> Sequence[Admin]:
    async with SessionLocal() as s:
        res = await s.execute(select(Admin).order_by(Admin.is_super.desc(), Admin.login))
        return res.scalars().all()


async def get_admin(admin_id: int) -> Admin | None:
    async with SessionLocal() as s:
        return await s.get(Admin, admin_id)


async def create_operator(
    login: str, password: str, sections: list[str], allowed: set[str]
) -> Admin | None:
    """Yangi operator yaratadi (super admin emas). Login band bo'lsa — None."""
    login = (login or "").strip()
    password = password or ""
    if not login or len(password) < 4:
        return None
    async with SessionLocal() as s:
        exists = (
            await s.execute(select(Admin).where(Admin.login == login))
        ).scalar_one_or_none()
        if exists:
            return None
        admin = Admin(
            login=login,
            password_hash=hash_password(password),
            is_super=False,
            permissions=_clean_perms(sections, allowed),
        )
        s.add(admin)
        await s.commit()
        await s.refresh(admin)
        return admin


async def update_operator_permissions(
    admin_id: int, sections: list[str], allowed: set[str]
) -> bool:
    """Operatorning bo'lim ruxsatlarini yangilaydi (super adminga tegmaydi)."""
    async with SessionLocal() as s:
        admin = await s.get(Admin, admin_id)
        if not admin or admin.is_super:
            return False
        admin.permissions = _clean_perms(sections, allowed)
        await s.commit()
        return True


async def reset_admin_password(admin_id: int, password: str) -> bool:
    if not password or len(password) < 4:
        return False
    async with SessionLocal() as s:
        admin = await s.get(Admin, admin_id)
        if not admin:
            return False
        admin.password_hash = hash_password(password)
        await s.commit()
        return True


async def delete_operator(admin_id: int) -> bool:
    """Operatorni o'chiradi. Super adminni o'chirib bo'lmaydi."""
    async with SessionLocal() as s:
        admin = await s.get(Admin, admin_id)
        if not admin or admin.is_super:
            return False
        await s.delete(admin)
        await s.commit()
        return True


# ============================ TALAB VA TAKLIFLAR (FEEDBACK) ============================

async def add_feedback(party_kind: str, party_id: int, text: str) -> Feedback | None:
    """Talab/taklifni saqlaydi. `party_kind`: 'client' yoki 'courier'."""
    text = (text or "").strip()
    if not text:
        return None
    party_kind = party_kind if party_kind in ("client", "courier") else "client"
    async with SessionLocal() as s:
        fb = Feedback(
            party_kind=party_kind,
            user_id=party_id if party_kind == "client" else None,
            courier_id=party_id if party_kind == "courier" else None,
            text=text,
        )
        s.add(fb)
        await s.commit()
        await s.refresh(fb)
        return fb


async def list_feedback(limit: int = 200) -> list[dict]:
    """Fikrlar ro'yxati (yangi avval) — mijoz/kuryer ma'lumotlari bilan."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(Feedback)
            .options(selectinload(Feedback.user), selectinload(Feedback.courier))
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
        rows = res.scalars().all()
    out = []
    for f in rows:
        if f.party_kind == "courier":
            name = f.courier.name if f.courier else "—"
            phone = f.courier.phone if f.courier else "—"
        else:
            name = f.user.full_name if f.user else "—"
            phone = f.user.phone if f.user else "—"
        out.append(
            {
                "id": f.id,
                "text": f.text,
                "is_read": f.is_read,
                "created_at": f.created_at,
                "source": f.party_kind,  # 'client' | 'courier'
                "name": name,
                "phone": phone,
            }
        )
    return out


async def list_party_feedback(party_kind: str, party_id: int, limit: int = 10) -> list[Feedback]:
    """Bir mijoz/kuryerning o'z takliflari (botda ko'rsatish uchun) — yangi avval."""
    party_kind = party_kind if party_kind in ("client", "courier") else "client"
    col = Feedback.courier_id if party_kind == "courier" else Feedback.user_id
    async with SessionLocal() as s:
        res = await s.execute(
            select(Feedback)
            .where(Feedback.party_kind == party_kind, col == party_id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())


async def feedback_unread_count() -> int:
    async with SessionLocal() as s:
        return int(
            (
                await s.execute(
                    select(func.count(Feedback.id)).where(Feedback.is_read == False)  # noqa: E712
                )
            ).scalar_one()
            or 0
        )


async def mark_feedback_read(feedback_id: int) -> None:
    async with SessionLocal() as s:
        fb = await s.get(Feedback, feedback_id)
        if fb and not fb.is_read:
            fb.is_read = True
            await s.commit()


async def mark_all_feedback_read() -> None:
    async with SessionLocal() as s:
        await s.execute(
            Feedback.__table__.update().where(Feedback.is_read == False).values(is_read=True)  # noqa: E712
        )
        await s.commit()


# ============================ ESLATMALAR ============================

async def users_needing_reminder(reminder_days: list[int]) -> list[tuple[User, int]]:
    """Buyurtma bermay qo'ygan mijozlar uchun (user, kun) ro'yxati."""
    threshold = sorted(reminder_days)
    out: list[tuple[User, int]] = []
    current = now()
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.deleted_at.is_(None)))
        users = res.scalars().all()
        for u in users:
            ref = u.last_order_at or u.created_at
            if not ref:
                continue
            days_passed = (current - ref).days
            # eng katta o'tilgan chegarani topamiz
            due = None
            for d in threshold:
                if days_passed >= d:
                    due = d
            if due and u.last_reminder_day < due:
                out.append((u, due))
    return out


async def mark_reminded(user_id: int, day: int) -> None:
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if u:
            u.last_reminder_day = day
            await s.commit()
