"""Jarayon ichidagi oddiy hodisa shinasi (pub/sub) — SSE uchun.

Botlar va admin panel bitta event loop'da (run_all.py) ishlaganda, bu shina
yangi buyurtma / holat o'zgarishi haqida admin brauzerlariga (SSE orqali)
darhol xabar beradi — sahifani qayta yuklamasdan.

Eslatma: bu in-process mexanizm. Agar admin va botlar alohida jarayonlarda
ishlatilsa, SSE hodisalari o'tmaydi — bunday holatda admin sahifasidagi
zaxira interval yangilash ishlaydi (bir necha soniya kechikish bilan).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger("events")

# Har bir ulangan admin brauzeri uchun bitta navbat.
_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    """Yangi SSE ulanishi uchun navbat ochadi."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Ulanish yopilganda navbatni olib tashlaydi."""
    _subscribers.discard(q)


def publish(event: str, data: dict[str, Any] | None = None) -> None:
    """Hodisani barcha ulangan admin brauzerlariga yuboradi.

    Bloklamaydi: agar navbat to'lib qolgan bo'lsa, o'sha xabar tashlanadi
    (admin baribir zaxira yangilash orqali yangilanadi).
    """
    payload = json.dumps({"event": event, **(data or {})}, ensure_ascii=False)
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
        except Exception as e:  # hech qachon chaqiruvchini buzmasin
            log.debug("publish xato: %s", e)
