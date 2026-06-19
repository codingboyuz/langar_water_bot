"""Admin panel — FastAPI.

Ishga tushirish:  python -m app.admin.main
                  (yoki: uvicorn app.admin.main:app --reload)
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import events
from app.config import settings
from app.db import service as svc
from app.db import warehouse as wh
from app.db.base import init_db
from app.admin.notify import send_order_to_courier, send_text_to_client, send_text_to_courier
from app.utils import fmt_dt, fmt_date, money, now

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Langar Water — Admin")
app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
# Jinja yordamchilari
templates.env.filters["money"] = money
templates.env.filters["dt"] = fmt_dt
templates.env.filters["date"] = fmt_date

static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def _startup():
    await init_db()


# --------------------------- auth ---------------------------

def _authed(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("/dashboard" if _authed(request) else "/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _authed(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, login: str = Form(...), password: str = Form(...)):
    admin = await svc.check_admin(login, password)
    if not admin:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Login yoki parol noto'g'ri"}
        )
    request.session["admin"] = admin.id
    request.session["login"] = admin.login
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# --------------------------- dashboard ---------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _authed(request):
        return _redirect_login()
    counts = await svc.dashboard_counts()
    fin_year = await wh.busiest_sales_year()
    fin_series = await wh.profit_series("day", fin_year, None)  # standart: kunlik (butun yil)
    fin_year_months = await wh.profit_series("month", fin_year)  # yillik jami uchun
    fin_years = await wh.data_years()
    stock = await wh.current_stock()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "page": "dashboard",
            "counts": counts,
            "fin_year": fin_year,
            "fin_years": fin_years,
            "fin_series": json.dumps(fin_series),
            "stock_qty": stock["total_qty"],
            "stock_value": stock["total_value"],
            "year_sold": sum(m["sold"] for m in fin_year_months),
            "year_profit": sum(m["profit"] for m in fin_year_months),
        },
    )


@app.get("/api/stats")
async def api_stats(request: Request):
    if not _authed(request):
        return {"error": "unauth"}
    counts = await svc.dashboard_counts()
    return {
        "counts": counts,
        "per_day": await svc.orders_per_day(14),
        "by_region": await svc.orders_by_region(),
    }


# --------------------------- realtime (SSE) ---------------------------

@app.get("/events")
async def events_stream(request: Request):
    """Server-Sent Events: yangi buyurtma / holat o'zgarishini darhol yetkazadi.

    Brauzer `EventSource('/events')` orqali ulanadi va sahifani qayta
    yuklamasdan yangilanadi (base.html dagi skript ishlatadi).
    """
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    queue = events.subscribe()

    async def gen():
        try:
            # ulanish ochilganini bildiramiz
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # ulanishni tirik saqlash uchun izoh-qator
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------- orders ---------------------------

@app.get("/orders", response_class=HTMLResponse)
async def orders(request: Request, status: str | None = None):
    if not _authed(request):
        return _redirect_login()
    valid_status = {"new", "assigned", "process", "await_confirm", "delivered"}
    order_list = await svc.list_orders(status if status in valid_status else None)
    couriers = await svc.list_couriers(active_only=True)
    return templates.TemplateResponse(
        request,
        "orders.html",
        {
            "page": "orders",
            "orders": order_list,
            "couriers": couriers,
            "status": status or "all",
        },
    )


@app.post("/assign")
async def assign(request: Request, order_id: int = Form(...), courier_id: int = Form(...)):
    if not _authed(request):
        return _redirect_login()
    back = request.headers.get("referer", "/orders")
    sep = "&" if "?" in back else "?"

    src = await svc.get_order(order_id)
    courier = await svc.get_courier(courier_id)
    # Hudud mosligi: kuryer faqat o'z hududidagi buyurtmani oladi
    if not src or not courier or not courier.is_active or courier.region != src.region:
        return RedirectResponse(f"{back}{sep}assigned=0", status_code=302)

    order = await svc.assign_order(order_id, courier_id)
    sent = False
    if order and courier.telegram_id:
        sent = await send_order_to_courier(
            courier.telegram_id, order, order.user, getattr(courier, "lang", "uz") or "uz"
        )
    return RedirectResponse(f"{back}{sep}assigned={'1' if sent else '0'}", status_code=302)


# --------------------------- couriers (hisob-kitob) ---------------------------
# Kuryerlar bot orqali ro'yxatdan o'tadi — qo'lda qo'shish/o'chirish bo'limi olib tashlandi.
# Bu yerda faqat hisob-kitob (stats) va kuryer profili (detail) qoladi.

@app.get("/couriers/stats", response_class=HTMLResponse)
async def couriers_stats(request: Request, period: str = "day"):
    if not _authed(request):
        return _redirect_login()
    if period not in {"day", "week", "month", "all"}:
        period = "day"
    stats = await svc.courier_stats(period)
    return templates.TemplateResponse(
        request,
        "courier_stats.html",
        {
            "page": "courier_stats",
            "stats": stats,
            "period": period,
        },
    )


@app.post("/couriers/toggle")
async def couriers_toggle(request: Request, courier_id: int = Form(...), active: int = Form(...)):
    """Kuryerni vaqtinchalik chetlashtirish (active=0) yoki qayta faollashtirish (active=1)."""
    if not _authed(request):
        return _redirect_login()
    await svc.set_courier_active(courier_id, bool(active))
    back = request.headers.get("referer", "/couriers/stats")
    return RedirectResponse(back, status_code=302)


@app.post("/couriers/delete")
async def couriers_delete(request: Request, courier_id: int = Form(...)):
    """Kuryerni butunlay o'chiradi."""
    if not _authed(request):
        return _redirect_login()
    await svc.delete_courier(courier_id)
    back = request.headers.get("referer", "/couriers/stats")
    return RedirectResponse(back, status_code=302)


@app.get("/couriers/{courier_id:int}", response_class=HTMLResponse)
async def courier_detail_page(request: Request, courier_id: int):
    if not _authed(request):
        return _redirect_login()
    detail = await svc.courier_detail(courier_id)
    if not detail:
        return RedirectResponse("/couriers/stats", status_code=302)
    tg = None
    if detail["courier"].telegram_id:
        from app.admin.notify import get_telegram_chat
        tg = await get_telegram_chat(detail["courier"].telegram_id)
    return templates.TemplateResponse(
        request,
        "courier_detail.html",
        {"page": "courier_stats", "d": detail, "tg": tg},
    )


# --------------------------- chat (admin <-> kuryer/mijoz) ---------------------------

CHAT_KINDS = {"courier", "client"}


async def _chat_party(kind: str, party_id: int) -> dict | None:
    """Suhbatdosh ma'lumotini normallashtirib qaytaradi (kuryer yoki mijoz)."""
    if kind == "courier":
        c = await svc.get_courier(party_id)
        if not c:
            return None
        return {"id": c.id, "name": c.name, "phone": c.phone, "region": c.region, "tg": c.telegram_id}
    if kind == "client":
        u = await svc.get_user_by_id(party_id)
        if not u:
            return None
        return {"id": u.id, "name": u.full_name, "phone": u.phone, "region": u.region, "tg": u.telegram_id}
    return None


def _msg_json(m) -> dict:
    return {
        "id": m.id,
        "dir": m.direction,
        "text": m.text,
        "time": m.created_at.strftime("%H:%M"),
        "day": m.created_at.strftime("%Y-%m-%d"),
    }


@app.get("/chat", response_class=HTMLResponse)
async def chat_root():
    return RedirectResponse("/chat/courier", status_code=302)


async def _chat_page(request: Request, kind: str, selected_id: int | None):
    """Ikki panelli (SPA) chat sahifasi: chap — ro'yxat, o'ng — suhbat.

    To'liq sahifa faqat bir marta yuklanadi; suhbatlar AJAX bilan almashadi,
    shu sababli har chatga kirganda qayta «rebuild» bo'lmaydi.
    """
    return templates.TemplateResponse(
        request,
        "chat_list.html",
        {
            "page": "chat",
            "kind": kind,
            "selected_id": selected_id,
            "chats": await svc.chat_overview(kind),
            "courier_unread": await svc.chat_unread_total("courier"),
            "client_unread": await svc.chat_unread_total("client"),
        },
    )


@app.get("/chat/{kind}", response_class=HTMLResponse)
async def chat_list(request: Request, kind: str):
    if not _authed(request):
        return _redirect_login()
    if kind not in CHAT_KINDS:
        return RedirectResponse("/chat/courier", status_code=302)
    return await _chat_page(request, kind, None)


@app.get("/chat/{kind}/{party_id:int}", response_class=HTMLResponse)
async def chat_detail(request: Request, kind: str, party_id: int):
    if not _authed(request):
        return _redirect_login()
    if kind not in CHAT_KINDS:
        return RedirectResponse("/chat/courier", status_code=302)
    if not await _chat_party(kind, party_id):
        return RedirectResponse(f"/chat/{kind}", status_code=302)
    return await _chat_page(request, kind, party_id)


@app.get("/chat/{kind}/overview")
async def chat_overview_api(request: Request, kind: str):
    """Chap paneldagi ro'yxatni arzon yangilash uchun JSON (butun sahifani emas)."""
    if not _authed(request):
        return {"error": "unauth"}
    if kind not in CHAT_KINDS:
        return {"chats": []}
    items = await svc.chat_overview(kind)
    return {
        "chats": [
            {
                "id": it["party"]["id"],
                "name": it["party"]["name"],
                "phone": it["party"]["phone"],
                "region": it["party"]["region"],
                "tg": bool(it["party"]["tg"]),
                "last_text": it["last_text"],
                "last_dir": it["last_dir"],
                "last_at": fmt_dt(it["last_at"]) if it["last_at"] else None,
                "last_in_at": fmt_dt(it["last_in_at"]) if it["last_in_at"] else None,
                "online": it["online"],
                "unread": it["unread"],
            }
            for it in items
        ]
    }


@app.get("/chat/{kind}/{party_id:int}/messages")
async def chat_messages_api(request: Request, kind: str, party_id: int, after: int = 0):
    """`after` id'dan keyingi xabarlar. Yangi xabarlar o'qilgan deb belgilanadi."""
    if not _authed(request):
        return {"error": "unauth"}
    if kind not in CHAT_KINDS:
        return {"messages": []}
    msgs = await svc.get_chat_messages_after(kind, party_id, after)
    if any(m.direction == "in" for m in msgs):
        await svc.mark_chat_read(kind, party_id)
    return {"messages": [_msg_json(m) for m in msgs]}


@app.post("/chat/{kind}/{party_id:int}/send")
async def chat_send(request: Request, kind: str, party_id: int, text: str = Form(...)):
    if not _authed(request):
        return {"error": "unauth"}
    text = (text or "").strip()
    party = await _chat_party(kind, party_id) if kind in CHAT_KINDS else None
    if not (party and text):
        return {"ok": False}
    m = await svc.add_chat_message(kind, party_id, "out", text)
    delivered = False
    if party["tg"]:
        if kind == "courier":
            delivered = await send_text_to_courier(party["tg"], text)
        else:
            delivered = await send_text_to_client(party["tg"], text)
    events.publish(
        "chat_message",
        {"kind": kind, "party_id": party_id, "name": party["name"]},
    )
    return {"ok": True, "delivered": delivered, "message": _msg_json(m)}


@app.get("/api/chat/unread")
async def api_chat_unread(request: Request):
    if not _authed(request):
        return {"error": "unauth"}
    return {
        "unread": await svc.chat_unread_total(),
        "courier": await svc.chat_unread_total("courier"),
        "client": await svc.chat_unread_total("client"),
    }


# --------------------------- narxlar (pricing) ---------------------------

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    if not _authed(request):
        return _redirect_login()
    saved = request.query_params.get("saved") == "1"
    return templates.TemplateResponse(
        request,
        "pricing.html",
        {
            "page": "pricing",
            "pricing": await svc.list_pricing(),
            "bottle_price": await svc.get_bottle_price(),
            "saved": saved,
        },
    )


@app.post("/pricing/save")
async def pricing_save(request: Request):
    if not _authed(request):
        return _redirect_login()
    form = await request.form()

    def _int(v) -> int | None:
        try:
            return int(str(v).replace(" ", "").strip())
        except (TypeError, ValueError):
            return None

    prices: dict[str, dict[str, int]] = {}
    for key, val in form.items():
        if key.startswith("water_"):
            iv = _int(val)
            if iv is not None:
                prices.setdefault(key[6:], {})["water_price"] = iv
        elif key.startswith("rate_"):
            iv = _int(val)
            if iv is not None:
                prices.setdefault(key[5:], {})["courier_rate"] = iv

    bottle = _int(form.get("bottle_price"))
    await svc.update_pricing(prices, bottle_price=bottle)
    return RedirectResponse("/pricing?saved=1", status_code=302)


# --------------------------- clients & bonuses ---------------------------

@app.get("/clients", response_class=HTMLResponse)
async def clients(request: Request):
    if not _authed(request):
        return _redirect_login()
    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "page": "clients",
            "clients": await svc.top_clients(50),
            "bonuses": await svc.list_pending_bonuses(),
        },
    )


@app.post("/bonus/sent")
async def bonus_sent(request: Request, bonus_id: int = Form(...)):
    if not _authed(request):
        return _redirect_login()
    await svc.mark_bonus_sent(bonus_id)
    return RedirectResponse("/clients", status_code=302)


# --------------------------- ombor (sklad) ---------------------------

@app.get("/warehouse", response_class=HTMLResponse)
async def warehouse_page(request: Request):
    if not _authed(request):
        return _redirect_login()
    added = request.query_params.get("added") == "1"
    return templates.TemplateResponse(
        request,
        "warehouse.html",
        {
            "page": "warehouse",
            "stock": await wh.current_stock(),
            "batches": await wh.list_batches(),
            "movements": await wh.list_movements(100),
            "products": await wh.list_products(),
            "today": now().strftime("%Y-%m-%d"),
            "added": added,
        },
    )


@app.post("/warehouse/inbound")
async def warehouse_inbound(request: Request):
    """Yangi partiya kirim qilish (forma yoki JSON)."""
    if not _authed(request):
        return _redirect_login()
    form = await request.form()

    def _int(v) -> int:
        try:
            return int(str(v).replace(" ", "").strip())
        except (TypeError, ValueError):
            return 0

    product_id = _int(form.get("product_id"))
    quantity = _int(form.get("quantity"))
    unit_cost = _int(form.get("unit_cost"))
    supplier = (str(form.get("supplier") or "").strip()) or None

    received_at = None
    raw_date = str(form.get("received_at") or "").strip()
    if raw_date:
        from datetime import datetime as _dt
        try:
            received_at = _dt.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            received_at = None

    if product_id and quantity > 0 and unit_cost >= 0:
        await wh.create_inbound(
            product_id=product_id,
            quantity=quantity,
            unit_cost=unit_cost,
            supplier=supplier,
            received_at=received_at,
        )
    return RedirectResponse("/warehouse?added=1", status_code=302)


@app.get("/warehouse/reports", response_class=HTMLResponse)
async def warehouse_reports_page(request: Request, year: int | None = None):
    if not _authed(request):
        return _redirect_login()
    year = year or now().year
    return templates.TemplateResponse(
        request,
        "warehouse_reports.html",
        {
            "page": "warehouse",
            "year": year,
            "years": list(range(now().year, now().year - 5, -1)),
            "monthly": json.dumps(await wh.monthly_report(year)),
            "breakdown": json.dumps(await wh.sales_breakdown()),
            "summary": await wh.warehouse_summary(),
        },
    )


@app.get("/api/warehouse/stock")
async def api_wh_stock(request: Request):
    if not _authed(request):
        return {"error": "unauth"}
    return await wh.current_stock()


@app.get("/api/warehouse/batches")
async def api_wh_batches(request: Request, product_id: int | None = None):
    if not _authed(request):
        return {"error": "unauth"}
    return {"batches": _jsonify(await wh.list_batches(product_id))}


@app.get("/api/warehouse/movements")
async def api_wh_movements(request: Request, limit: int = 200):
    if not _authed(request):
        return {"error": "unauth"}
    return {"movements": _jsonify(await wh.list_movements(limit))}


@app.get("/api/warehouse/reports/monthly")
async def api_wh_monthly(request: Request, year: int | None = None):
    if not _authed(request):
        return {"error": "unauth"}
    year = year or now().year
    return {"year": year, "months": await wh.monthly_report(year)}


@app.get("/api/warehouse/analytics/sales-breakdown")
async def api_wh_breakdown(request: Request):
    if not _authed(request):
        return {"error": "unauth"}
    return {"breakdown": await wh.sales_breakdown()}


@app.get("/api/warehouse/profit-series")
async def api_wh_profit_series(
    request: Request,
    granularity: str = "day",
    year: int | None = None,
    month: int | None = None,
):
    """Foyda/zarar vaqt qatori — kun/oy/yil kesimida (dashboard grafigi)."""
    if not _authed(request):
        return {"error": "unauth"}
    if granularity not in {"day", "month", "year"}:
        granularity = "day"
    if granularity != "year" and year is None:
        year = await wh.busiest_sales_year()
    if not month:  # 0 yoki None -> butun yil
        month = None
    return {
        "granularity": granularity,
        "year": year,
        "month": month,
        "series": await wh.profit_series(granularity, year, month),
    }


def _jsonify(rows: list[dict]) -> list[dict]:
    """`datetime` maydonlarni JSON uchun stringga aylantiradi."""
    from datetime import datetime as _dt

    out = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, _dt):
                d[k] = fmt_dt(v)
        out.append(d)
    return out


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.admin_host, port=settings.admin_port)


if __name__ == "__main__":
    run()
