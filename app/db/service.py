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
from app.config import CLIENT_BONUS_STEP, REGION_BY_NAME
from app.db.base import SessionLocal
from app.db.models import (
    Admin,
    AppSetting,
    BonusPromo,
    ChatMessage,
    Courier,
    Order,
    Pricing,
    User,
)
from app.security import verify_password
from app.utils import now

# Buyurtma "jarayonda" deb hisoblanadigan holatlar (yangi va yakunlangan oralig'i):
#   assigned      — kuryerga biriktirildi, lekin kuryer hali qabul qilmadi
#   process       — kuryer "Jarayonda" tugmasini bosdi (qabul qildi)
#   await_confirm — kuryer "Yetkazildi" bosdi, mijoz tasdig'i kutilmoqda
ACTIVE_STATUSES = ("assigned", "process", "await_confirm")


# ============================ MIJOZ (USER) ============================

async def get_user_by_tg(telegram_id: int) -> User | None:
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.telegram_id == telegram_id))
        return res.scalar_one_or_none()


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
        # narx avval DB (admin tahrirlagan) dan, bo'lmasa config dan olinadi
        pricing = (
            await s.execute(select(Pricing).where(Pricing.region_name == region_name))
        ).scalar_one_or_none()
        if pricing:
            unit_price = pricing.water_price
        else:
            region = REGION_BY_NAME.get(region_name)
            unit_price = region.price if region else 0
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
        await s.commit()
    await _check_client_bonus(order_id)
    events.publish("order_update", {"order_id": order_id, "status": "delivered"})
    return await get_order(order_id)


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
    from app.config import REGION_BY_NAME
    from app.routing import order_route

    async with SessionLocal() as s:
        courier = await s.get(Courier, courier_id)
        if not courier:
            return None

        # kuryer stavkasi (DB narxidan, bo'lmasa config)
        pr = (
            await s.execute(select(Pricing).where(Pricing.region_name == courier.region))
        ).scalar_one_or_none()
        if pr:
            rate = pr.courier_rate
        else:
            region = REGION_BY_NAME.get(courier.region)
            rate = region.courier_rate if region else 2500

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


async def add_courier(
    name: str,
    phone: str,
    region: str,
    telegram_id: int | None,
    lang: str = "uz",
) -> Courier:
    async with SessionLocal() as s:
        c = Courier(
            name=name,
            phone=phone,
            region=region,
            telegram_id=telegram_id,
            lang=lang,
        )
        s.add(c)
        await s.commit()
        await s.refresh(c)
        return c


async def register_courier(
    telegram_id: int, name: str, phone: str, region: str, lang: str
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


# ============================ CHAT (admin <-> kuryer) ============================

async def add_chat_message(courier_id: int, direction: str, text: str) -> ChatMessage:
    """Yozishma xabarini saqlaydi.

    direction: 'to_courier' (admin yozdi) yoki 'from_courier' (kuryer yozdi).
    Adminning o'z xabari darhol 'o'qilgan' deb belgilanadi.
    """
    async with SessionLocal() as s:
        m = ChatMessage(
            courier_id=courier_id,
            direction=direction,
            text=text,
            is_read=(direction == "to_courier"),
        )
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def get_chat_messages(courier_id: int, limit: int = 300) -> Sequence[ChatMessage]:
    """Bitta kuryer bilan yozishma (vaqt bo'yicha — eskidan yangiga)."""
    async with SessionLocal() as s:
        # oxirgi `limit` ta xabarni olamiz, keyin xronologik tartibga keltiramiz
        res = await s.execute(
            select(ChatMessage)
            .where(ChatMessage.courier_id == courier_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        rows = list(res.scalars().all())
    rows.reverse()
    return rows


async def get_chat_messages_after(
    courier_id: int, after_id: int = 0, limit: int = 200
) -> Sequence[ChatMessage]:
    """`after_id` dan keyingi yangi xabarlar (qo'shimcha yuklash / polling uchun)."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(ChatMessage)
            .where(ChatMessage.courier_id == courier_id, ChatMessage.id > after_id)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
        return list(res.scalars().all())


async def mark_chat_read(courier_id: int) -> None:
    """Kuryerdan kelgan o'qilmagan xabarlarni o'qilgan deb belgilaydi."""
    async with SessionLocal() as s:
        await s.execute(
            ChatMessage.__table__.update()
            .where(
                ChatMessage.courier_id == courier_id,
                ChatMessage.direction == "from_courier",
                ChatMessage.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        await s.commit()


async def chat_unread_total() -> int:
    """Barcha kuryerlardan kelgan o'qilmagan xabarlar soni (sidebar badge)."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.direction == "from_courier",
                ChatMessage.is_read == False,  # noqa: E712
            )
        )
        return int(res.scalar_one() or 0)


async def chat_overview() -> list[dict]:
    """Chat ro'yxati: har bir kuryer + oxirgi xabar + o'qilmaganlar soni.

    Xabari borlar tepada (oxirgi xabar vaqti bo'yicha), keyin qolganlar.
    """
    async with SessionLocal() as s:
        couriers = list((await s.execute(select(Courier).order_by(Courier.name))).scalars().all())
        # o'qilmaganlar soni (kuryer bo'yicha)
        ures = await s.execute(
            select(ChatMessage.courier_id, func.count(ChatMessage.id))
            .where(
                ChatMessage.direction == "from_courier",
                ChatMessage.is_read == False,  # noqa: E712
            )
            .group_by(ChatMessage.courier_id)
        )
        unread = {cid: int(c) for cid, c in ures.all()}
        # har bir kuryerning oxirgi xabari
        lres = await s.execute(
            select(ChatMessage).order_by(ChatMessage.created_at.desc())
        )
        last_by: dict[int, ChatMessage] = {}
        for m in lres.scalars().all():
            last_by.setdefault(m.courier_id, m)

    items = []
    for c in couriers:
        lm = last_by.get(c.id)
        items.append({
            "courier": c,
            "last_text": lm.text if lm else None,
            "last_at": lm.created_at if lm else None,
            "last_dir": lm.direction if lm else None,
            "unread": unread.get(c.id, 0),
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
        clients = await count(select(func.count(User.id)))
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
    return {
        "total": total,
        "new": new,
        "process": process,
        "delivered": delivered,
        "clients": clients,
        "couriers": couriers,
        "revenue": revenue,
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
            "bottles": dv,  # orqaga moslik (eski kalit)
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
            .group_by(User.id)
            .order_by(func.coalesce(func.sum(Order.delivered_count), 0).desc())
            .limit(limit)
        )
        rows = res.all()
    return [
        {
            "user_id": r[0],
            "name": r[1],
            "phone": r[2],
            "region": r[3],
            "bottles": int(r[4]),
            "orders": int(r[5]),
            "bonus_due": int(r[4]) >= CLIENT_BONUS_STEP,
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

    Ish haqi = sum(delivered_count * region.courier_rate).
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
        # kuryer stavkasi DB narxidan (admin tahrirlagan)
        pricing_rows = (await s.execute(select(Pricing))).scalars().all()
        rate_by_name = {p.region_name: p.courier_rate for p in pricing_rows}

    from app.config import (
        COURIER_DAILY_BONUS_AMOUNT,
        COURIER_DAILY_BONUS_STEP,
        REGION_BY_NAME,
    )

    out = []
    for r in rows:
        if r[3] in rate_by_name:
            rate = rate_by_name[r[3]]
        else:
            region = REGION_BY_NAME.get(r[3])
            rate = region.courier_rate if region else 2500
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


# ============================ NARXLAR ============================

async def list_pricing() -> Sequence[Pricing]:
    async with SessionLocal() as s:
        res = await s.execute(select(Pricing).order_by(Pricing.id))
        return res.scalars().all()


async def get_bottle_price() -> int:
    async with SessionLocal() as s:
        st = await s.get(AppSetting, "bottle_price")
        try:
            return int(st.value) if st else 0
        except (TypeError, ValueError):
            return 0


async def update_pricing(prices: dict[str, dict[str, int]], bottle_price: int | None = None) -> None:
    """Narxlarni yangilaydi.

    prices: {region_key: {"water_price": int, "courier_rate": int}}
    """
    async with SessionLocal() as s:
        rows = (await s.execute(select(Pricing))).scalars().all()
        for p in rows:
            upd = prices.get(p.region_key)
            if not upd:
                continue
            if "water_price" in upd:
                p.water_price = max(0, int(upd["water_price"]))
            if "courier_rate" in upd:
                p.courier_rate = max(0, int(upd["courier_rate"]))
        if bottle_price is not None:
            st = await s.get(AppSetting, "bottle_price")
            if st is None:
                st = AppSetting(key="bottle_price", value=str(max(0, bottle_price)))
                s.add(st)
            else:
                st.value = str(max(0, bottle_price))
        await s.commit()


# ============================ ADMIN AUTH ============================

async def check_admin(login: str, password: str) -> Admin | None:
    async with SessionLocal() as s:
        res = await s.execute(select(Admin).where(Admin.login == login))
        admin = res.scalar_one_or_none()
        if admin and verify_password(password, admin.password_hash):
            return admin
        return None


# ============================ ESLATMALAR ============================

async def users_needing_reminder(reminder_days: list[int]) -> list[tuple[User, int]]:
    """Buyurtma bermay qo'ygan mijozlar uchun (user, kun) ro'yxati."""
    threshold = sorted(reminder_days)
    out: list[tuple[User, int]] = []
    current = now()
    async with SessionLocal() as s:
        res = await s.execute(select(User))
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
