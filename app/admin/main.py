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
from app.db.base import init_db
from app.admin.notify import send_order_to_courier, send_text_to_client, send_text_to_courier
from app.utils import fmt_dt, fmt_date, money

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
    per_day = await svc.orders_per_day(14)
    by_region = await svc.orders_by_region()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "page": "dashboard",
            "counts": counts,
            "per_day": json.dumps(per_day),
            "by_region": json.dumps(by_region),
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


# --------------------------- chat (admin <-> kuryer) ---------------------------

@app.get("/chat", response_class=HTMLResponse)
async def chat_list(request: Request):
    if not _authed(request):
        return _redirect_login()
    return templates.TemplateResponse(
        request,
        "chat_list.html",
        {"page": "chat", "chats": await svc.chat_overview()},
    )


@app.get("/chat/{courier_id:int}", response_class=HTMLResponse)
async def chat_detail(request: Request, courier_id: int):
    if not _authed(request):
        return _redirect_login()
    courier = await svc.get_courier(courier_id)
    if not courier:
        return RedirectResponse("/chat", status_code=302)
    messages = await svc.get_chat_messages(courier_id)
    await svc.mark_chat_read(courier_id)  # ochilganda o'qilgan deb belgilanadi
    return templates.TemplateResponse(
        request,
        "chat_detail.html",
        {"page": "chat", "courier": courier, "messages": messages},
    )


@app.post("/chat/{courier_id:int}/send")
async def chat_send(request: Request, courier_id: int, text: str = Form(...)):
    if not _authed(request):
        return _redirect_login()
    text = (text or "").strip()
    courier = await svc.get_courier(courier_id)
    if courier and text:
        await svc.add_chat_message(courier_id, "to_courier", text)
        if courier.telegram_id:
            await send_text_to_courier(courier.telegram_id, text)
        events.publish("chat_message", {"courier_id": courier_id})
    return RedirectResponse(f"/chat/{courier_id}", status_code=302)


@app.get("/api/chat/unread")
async def api_chat_unread(request: Request):
    if not _authed(request):
        return {"error": "unauth"}
    return {"unread": await svc.chat_unread_total()}


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


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.admin_host, port=settings.admin_port)


if __name__ == "__main__":
    run()
