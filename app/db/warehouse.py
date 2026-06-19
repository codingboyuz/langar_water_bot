"""Ombor (sklad) service qatlami.

Kirim (partiya), avtomatik FIFO chiqim, qoldiq, harakatlar tarixi va
hisobotlar shu yerda. Barcha hisob-kitob (foyda, qoldiq, jami summa)
backendda — shu modulda — aniq hisoblanadi (frontendda emas).

Sotuv (Order) `delivered` bo'lganda `fifo_outbound` chaqiriladi: eng eski
partiyadan boshlab kerakli dona ombordan kamaytiriladi va har bir chiqim
`StockMovement` ga yoziladi. Foyda = (sotilgan narx − partiya tannarxi) × dona.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import extract, func, select

from app.db.base import SessionLocal
from app.db.models import Batch, Product, StockMovement
from app.utils import now


# ============================ MAHSULOT ============================

async def get_default_product() -> Product | None:
    """Sotuvda avtomatik chiqimga ishlatiladigan standart mahsulot."""
    async with SessionLocal() as s:
        res = await s.execute(
            select(Product).where(Product.is_default == True)  # noqa: E712
        )
        return res.scalars().first()


async def list_products() -> Sequence[Product]:
    async with SessionLocal() as s:
        res = await s.execute(select(Product).order_by(Product.id))
        return res.scalars().all()


# ============================ KIRIM (PARTIYA) ============================

async def _next_batch_no(s, received_at: datetime) -> str:
    """Partiya raqamini avtomatik yaratadi: 'P-YYMMDD-N' (kun ichidagi tartib)."""
    day_start = received_at.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    cnt = (
        await s.execute(
            select(func.count(Batch.id)).where(
                Batch.received_at >= day_start, Batch.received_at <= day_end
            )
        )
    ).scalar_one() or 0
    return f"P-{received_at:%y%m%d}-{cnt + 1}"


async def create_inbound(
    product_id: int,
    quantity: int,
    unit_cost: int,
    supplier: str | None = None,
    received_at: datetime | None = None,
    batch_no: str | None = None,
) -> Batch:
    """Omborga yangi partiya kirim qiladi.

    `total_cost` va `remaining` avtomatik to'ldiriladi. KIRIM harakati ham
    `StockMovement` ga yoziladi (audit/tarix uchun).
    """
    quantity = max(0, int(quantity))
    unit_cost = max(0, int(unit_cost))
    received_at = received_at or now()
    async with SessionLocal() as s:
        no = batch_no or await _next_batch_no(s, received_at)
        batch = Batch(
            product_id=product_id,
            batch_no=no,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=quantity * unit_cost,
            remaining=quantity,
            supplier=(supplier or None),
            received_at=received_at,
        )
        s.add(batch)
        await s.flush()  # batch.id kerak
        s.add(
            StockMovement(
                kind="in",
                product_id=product_id,
                batch_id=batch.id,
                quantity=quantity,
                unit_cost=unit_cost,
                unit_price=0,
                note=f"Kirim — partiya {no}",
                created_at=received_at,
            )
        )
        await s.commit()
        await s.refresh(batch)
        return batch


# ============================ CHIQIM (FIFO) ============================

async def _avg_cost(s, product_id: int) -> int:
    """Mahsulotning o'rtacha sotib olish narxi (kamomad chiqimi uchun fallback)."""
    row = (
        await s.execute(
            select(
                func.coalesce(func.sum(Batch.total_cost), 0),
                func.coalesce(func.sum(Batch.quantity), 0),
            ).where(Batch.product_id == product_id)
        )
    ).first()
    total_cost, total_qty = int(row[0] or 0), int(row[1] or 0)
    return round(total_cost / total_qty) if total_qty else 0


async def fifo_outbound(
    order_id: int,
    quantity: int,
    unit_price: int,
    product_id: int | None = None,
) -> dict | None:
    """Sotuv uchun ombordan FIFO bo'yicha chiqim qiladi.

    Eng eski partiyadan (received_at, keyin id bo'yicha) boshlab kerakli dona
    kamaytiriladi. Har bir partiyadan olingan qism alohida `StockMovement`
    (kind='out') bo'lib yoziladi — shunda har donaning tannarxi qaysi
    partiyadan kelgani aniq bo'ladi.

    Qoldiq yetmasa — bloklamaydi (suv allaqachon yetkazilgan): mavjudini
    chiqaradi, qolgan kamomadni `shortfall=True` harakat bilan belgilaydi.

    Bir buyurtma uchun ikki marta chiqim bo'lmasligi uchun idempotent.
    Qaytaradi: {qty, revenue, cogs, profit, shortfall} yoki None.
    """
    quantity = int(quantity or 0)
    if quantity <= 0:
        return None
    unit_price = max(0, int(unit_price or 0))

    async with SessionLocal() as s:
        # idempotentlik: shu buyurtma uchun chiqim allaqachon yozilganmi?
        already = (
            await s.execute(
                select(func.count(StockMovement.id)).where(
                    StockMovement.order_id == order_id, StockMovement.kind == "out"
                )
            )
        ).scalar_one()
        if already:
            return None

        if product_id is None:
            prod = (
                await s.execute(
                    select(Product).where(Product.is_default == True)  # noqa: E712
                )
            ).scalars().first()
            if prod is None:
                return None
            product_id = prod.id

        remaining_needed = quantity
        revenue = 0
        cogs = 0

        batches = (
            await s.execute(
                select(Batch)
                .where(Batch.product_id == product_id, Batch.remaining > 0)
                .order_by(Batch.received_at.asc(), Batch.id.asc())
            )
        ).scalars().all()

        for b in batches:
            if remaining_needed <= 0:
                break
            take = min(b.remaining, remaining_needed)
            b.remaining -= take
            remaining_needed -= take
            revenue += unit_price * take
            cogs += b.unit_cost * take
            s.add(
                StockMovement(
                    kind="out",
                    product_id=product_id,
                    batch_id=b.id,
                    order_id=order_id,
                    quantity=take,
                    unit_cost=b.unit_cost,
                    unit_price=unit_price,
                    note=f"Sotuv #{order_id} — partiya {b.batch_no}",
                )
            )

        shortfall_qty = remaining_needed
        if shortfall_qty > 0:
            # qoldiq yetmadi — kamomadni belgilab yozamiz (o'rtacha tannarx bilan)
            avg = await _avg_cost(s, product_id)
            revenue += unit_price * shortfall_qty
            cogs += avg * shortfall_qty
            s.add(
                StockMovement(
                    kind="out",
                    product_id=product_id,
                    batch_id=None,
                    order_id=order_id,
                    quantity=shortfall_qty,
                    unit_cost=avg,
                    unit_price=unit_price,
                    shortfall=True,
                    note=f"Sotuv #{order_id} — ombor qoldig'i yetmadi ({shortfall_qty} dona)",
                )
            )

        await s.commit()

    return {
        "qty": quantity,
        "revenue": revenue,
        "cogs": cogs,
        "profit": revenue - cogs,
        "shortfall": shortfall_qty,
    }


# ============================ QOLDIQ ============================

async def current_stock() -> dict:
    """Joriy ombor qoldig'i: har bir mahsulot bo'yicha dona, qiymat, o'rtacha tannarx."""
    async with SessionLocal() as s:
        products = (await s.execute(select(Product).order_by(Product.id))).scalars().all()
        rows = (
            await s.execute(
                select(
                    Batch.product_id,
                    func.coalesce(func.sum(Batch.remaining), 0),
                    func.coalesce(func.sum(Batch.remaining * Batch.unit_cost), 0),
                ).group_by(Batch.product_id)
            )
        ).all()
    by_pid = {int(r[0]): (int(r[1]), int(r[2])) for r in rows}

    items = []
    total_qty = 0
    total_value = 0
    for p in products:
        qty, value = by_pid.get(p.id, (0, 0))
        total_qty += qty
        total_value += value
        items.append(
            {
                "product_id": p.id,
                "name": p.name,
                "volume": p.volume,
                "qty": qty,
                "value": value,
                "avg_cost": round(value / qty) if qty else 0,
            }
        )
    return {"items": items, "total_qty": total_qty, "total_value": total_value}


async def list_batches(product_id: int | None = None) -> list[dict]:
    """Partiyalar ro'yxati (eng yangisi tepada)."""
    async with SessionLocal() as s:
        stmt = (
            select(Batch, Product.name)
            .join(Product, Product.id == Batch.product_id)
            .order_by(Batch.received_at.desc(), Batch.id.desc())
        )
        if product_id:
            stmt = stmt.where(Batch.product_id == product_id)
        rows = (await s.execute(stmt)).all()
    out = []
    for b, pname in rows:
        sold = b.quantity - b.remaining
        out.append(
            {
                "id": b.id,
                "batch_no": b.batch_no,
                "product": pname,
                "quantity": b.quantity,
                "remaining": b.remaining,
                "sold": sold,
                "unit_cost": b.unit_cost,
                "total_cost": b.total_cost,
                "remaining_value": b.remaining * b.unit_cost,
                "supplier": b.supplier,
                "received_at": b.received_at,
            }
        )
    return out


async def list_movements(limit: int = 200) -> list[dict]:
    """Kirim/chiqim harakatlari tarixi (eng yangisi tepada)."""
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(StockMovement, Product.name, Batch.batch_no)
                .join(Product, Product.id == StockMovement.product_id)
                .outerjoin(Batch, Batch.id == StockMovement.batch_id)
                .order_by(StockMovement.id.desc())
                .limit(limit)
            )
        ).all()
    out = []
    for m, pname, bno in rows:
        out.append(
            {
                "id": m.id,
                "kind": m.kind,  # 'in' | 'out'
                "product": pname,
                "batch_no": bno,
                "order_id": m.order_id,
                "quantity": m.quantity,
                "unit_cost": m.unit_cost,
                "unit_price": m.unit_price,
                "profit": (m.unit_price - m.unit_cost) * m.quantity if m.kind == "out" else 0,
                "shortfall": m.shortfall,
                "note": m.note,
                "created_at": m.created_at,
            }
        )
    return out


# ============================ HISOBOTLAR ============================

_MONTHS_UZ = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


async def monthly_report(year: int) -> list[dict]:
    """Berilgan yil uchun oylar kesimida hisobot (grafik uchun).

    Har oy: jami kirim (sotib olish summasi), sotuv summasi (daromad),
    sotilgan tovar tannarxi (COGS) va foyda/zarar (= daromad − tannarx).
    Foyda FIFO chiqim tannarxiga asoslanadi (oydagi haqiqiy sotuvlar bo'yicha).
    """
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)

    purchases = [0] * 12  # oylik kirim (xarajat)
    revenue = [0] * 12    # oylik daromad
    cogs = [0] * 12       # oylik tannarx
    sold = [0] * 12       # oylik sotilgan dona

    async with SessionLocal() as s:
        # kirim (partiya) — sotib olish summasi, received_at bo'yicha
        bt = (
            await s.execute(
                select(Batch.received_at, Batch.total_cost).where(
                    Batch.received_at >= start, Batch.received_at < end
                )
            )
        ).all()
        for received_at, total_cost in bt:
            purchases[received_at.month - 1] += int(total_cost or 0)

        # chiqim (sotuv) — daromad, tannarx, dona; created_at bo'yicha
        mv = (
            await s.execute(
                select(
                    StockMovement.created_at,
                    StockMovement.quantity,
                    StockMovement.unit_price,
                    StockMovement.unit_cost,
                ).where(
                    StockMovement.kind == "out",
                    StockMovement.created_at >= start,
                    StockMovement.created_at < end,
                )
            )
        ).all()
        for created_at, qty, up, uc in mv:
            i = created_at.month - 1
            qty = int(qty or 0)
            revenue[i] += int(up or 0) * qty
            cogs[i] += int(uc or 0) * qty
            sold[i] += qty

    out = []
    for i in range(12):
        out.append(
            {
                "month": i + 1,
                "label": _MONTHS_UZ[i],
                "purchases": purchases[i],
                "revenue": revenue[i],
                "cogs": cogs[i],
                "profit": revenue[i] - cogs[i],
                "sold": sold[i],
            }
        )
    return out


_MONTHS_SHORT = [
    "Yan", "Fev", "Mar", "Apr", "May", "Iyun",
    "Iyul", "Avg", "Sen", "Okt", "Noy", "Dek",
]


async def data_years() -> list[int]:
    """Sotuv bo'lgan yillar ro'yxati (yangi yil tepada). Bo'sh bo'lsa joriy yil."""
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(extract("year", StockMovement.created_at))
                .where(StockMovement.kind == "out")
                .distinct()
            )
        ).all()
    ys = sorted({int(r[0]) for r in rows}, reverse=True)
    return ys or [now().year]


async def profit_series(
    granularity: str = "day", year: int | None = None, month: int | None = None
) -> list[dict]:
    """Foyda/zarar vaqt qatori — kun/oy/yil kesimida (grafik uchun).

    `granularity`:
      - 'year'  — barcha yillar bo'yicha (yillik foyda)
      - 'month' — berilgan yil ichida 12 oy
      - 'day'   — kunma-kun. `month` berilsa o'sha oyning hamma kunlari (bo'sh=0);
                  berilmasa yil ichidagi ma'lumot oralig'i.
    Har element: {label, profit, revenue, cogs, sold}.
    """
    import calendar
    from collections import defaultdict
    from datetime import date, timedelta

    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    StockMovement.created_at,
                    StockMovement.quantity,
                    StockMovement.unit_price,
                    StockMovement.unit_cost,
                ).where(StockMovement.kind == "out")
            )
        ).all()

    agg: dict = defaultdict(lambda: [0, 0, 0, 0])  # profit, revenue, cogs, sold
    for created_at, qty, up, uc in rows:
        qty, up, uc = int(qty or 0), int(up or 0), int(uc or 0)
        if granularity in ("day", "month") and year and created_at.year != year:
            continue
        if granularity == "day" and month and created_at.month != month:
            continue
        if granularity == "year":
            key = created_at.year
        elif granularity == "day":
            key = created_at.date()
        else:
            key = created_at.month
        a = agg[key]
        a[0] += (up - uc) * qty
        a[1] += up * qty
        a[2] += uc * qty
        a[3] += qty

    def row(label, a):
        return {"label": label, "profit": a[0], "revenue": a[1], "cogs": a[2], "sold": a[3]}

    out: list[dict] = []
    if granularity == "year":
        for y in sorted(agg):
            out.append(row(str(y), agg[y]))
    elif granularity == "month":
        for m in range(1, 13):
            out.append(row(_MONTHS_SHORT[m - 1], agg.get(m, [0, 0, 0, 0])))
    elif granularity == "day" and month and year:
        # tanlangan oyning hamma kunlari (1..oxirgi kun), bo'sh kun = 0
        days = calendar.monthrange(year, month)[1]
        for dnum in range(1, days + 1):
            d = date(year, month, dnum)
            out.append(row(f"{dnum:02d}", agg.get(d, [0, 0, 0, 0])))
    elif granularity == "day" and year:  # butun yil — to'liq kalendar (1-yan..31-dek)
        d = date(year, 1, 1)
        endd = date(year, 12, 31)
        while d <= endd:
            out.append(row(d.strftime("%d.%m"), agg.get(d, [0, 0, 0, 0])))
            d += timedelta(days=1)
    else:  # day, yil berilmagan — ma'lumot oralig'i
        if agg:
            lo, hi = min(agg), max(agg)
            d = lo
            while d <= hi:
                out.append(row(d.strftime("%d.%m"), agg.get(d, [0, 0, 0, 0])))
                d += timedelta(days=1)
    return out


async def busiest_sales_year() -> int:
    """Eng ko'p sotuv (dona) bo'lgan yil — dashboard grafigi shu yilni ko'rsatadi.

    Hech qanday sotuv bo'lmasa joriy yil qaytadi.
    """
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    extract("year", StockMovement.created_at).label("y"),
                    func.sum(StockMovement.quantity),
                )
                .where(StockMovement.kind == "out")
                .group_by("y")
                .order_by(func.sum(StockMovement.quantity).desc())
            )
        ).all()
    return int(rows[0][0]) if rows else now().year


async def sales_breakdown() -> list[dict]:
    """Mahsulot turi kesimida sotuv hajmi va foyda (chiqimlar bo'yicha)."""
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    Product.id,
                    Product.name,
                    func.coalesce(func.sum(StockMovement.quantity), 0),
                    func.coalesce(
                        func.sum(StockMovement.quantity * StockMovement.unit_price), 0
                    ),
                    func.coalesce(
                        func.sum(StockMovement.quantity * StockMovement.unit_cost), 0
                    ),
                )
                .join(StockMovement, StockMovement.product_id == Product.id)
                .where(StockMovement.kind == "out")
                .group_by(Product.id)
                .order_by(func.coalesce(func.sum(StockMovement.quantity), 0).desc())
            )
        ).all()
    out = []
    for pid, name, qty, rev, cogs in rows:
        qty, rev, cogs = int(qty), int(rev), int(cogs)
        out.append(
            {
                "product_id": pid,
                "name": name,
                "qty": qty,
                "revenue": rev,
                "cogs": cogs,
                "profit": rev - cogs,
            }
        )
    return out


async def warehouse_summary() -> dict:
    """Qisqa xulosa (dashboard / Telegram uchun): qoldiq + joriy oy foydasi."""
    stock = await current_stock()
    today = now()
    months = await monthly_report(today.year)
    this_month = months[today.month - 1]
    year_profit = sum(m["profit"] for m in months)
    year_revenue = sum(m["revenue"] for m in months)
    return {
        "stock_qty": stock["total_qty"],
        "stock_value": stock["total_value"],
        "month_revenue": this_month["revenue"],
        "month_profit": this_month["profit"],
        "month_sold": this_month["sold"],
        "year_revenue": year_revenue,
        "year_profit": year_profit,
    }
