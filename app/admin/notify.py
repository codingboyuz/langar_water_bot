"""Admin paneldan kuryer/mijoz botiga xabar yuborish (Telegram Bot API)."""
from __future__ import annotations

import httpx

from app.config import settings
from app.courier_bot.common import order_caption, order_keyboard


async def send_order_to_courier(chat_id: int, order, user, lang: str = "uz") -> bool:
    """Buyurtmani kuryerga inline tugmalar bilan yuboradi (kuryer tilida)."""
    url = f"https://api.telegram.org/bot{settings.courier_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": order_caption(order, user, lang),
        "parse_mode": "HTML",
        "reply_markup": order_keyboard(order.id, lang),
    }
    return await _post(url, payload)


async def send_text_to_client(chat_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{settings.client_bot_token}/sendMessage"
    return await _post(url, {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


async def send_text_to_courier(chat_id: int, text: str) -> bool:
    """Admin chatidan kuryerga oddiy matn yuboradi (parse_mode'siz — xavfsiz)."""
    url = f"https://api.telegram.org/bot{settings.courier_bot_token}/sendMessage"
    return await _post(url, {"chat_id": chat_id, "text": text})


async def get_telegram_chat(chat_id: int) -> dict | None:
    """Kuryerning Telegram profilini oladi (getChat).

    Ism, username, bio va h.k. qaytaradi. Kuryer botni /start qilgan bo'lsa
    ishlaydi. Tarmoq xatosi/token yo'qligida None qaytadi.
    """
    url = f"https://api.telegram.org/bot{settings.courier_bot_token}/getChat"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"chat_id": chat_id})
            data = r.json()
            if data.get("ok"):
                return data.get("result")
    except Exception:
        return None
    return None


async def _post(url: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            return r.status_code == 200 and r.json().get("ok", False)
    except Exception:
        return False
