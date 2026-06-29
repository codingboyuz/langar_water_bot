"""Avtomatik eslatmalar.

Mijoz `REMINDER_DAYS` (masalan 10,15,20,30) kun buyurtma bermasa, unga
«suvingiz tugayabdimi?» mazmunidagi xabar yuboriladi.

Ishga tushirish:  python -m app.reminders
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.admin.notify import send_text_to_client
from app.config import settings
from app.db import service as svc
from app.db.base import init_db
from app.i18n import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("reminders")


async def run_reminders() -> None:
    days = settings.reminder_days_list
    pairs = await svc.users_needing_reminder(days)
    log.info("Eslatma kerak bo'lgan mijozlar: %d", len(pairs))
    for user, day in pairs:
        text = t("reminder", user.lang).format(name=user.full_name.split()[0] if user.full_name else "")
        ok = await send_text_to_client(user.telegram_id, text)
        if ok:
            await svc.mark_reminded(user.id, day)
            log.info("Eslatma yuborildi: %s (%d kun)", user.phone, day)


async def run_purge() -> None:
    """Muddati o'tgan arxiv (yumshoq o'chirilgan) mijozlarni butunlay o'chiradi."""
    n = await svc.purge_expired_users()
    if n:
        log.info("Arxivdan butunlay o'chirildi: %d mijoz", n)


async def main() -> None:
    await init_db()
    scheduler = AsyncIOScheduler()
    # Har kuni soat 10:00 da tekshiradi (kerak bo'lsa o'zgartiring)
    scheduler.add_job(run_reminders, "cron", hour=10, minute=0)
    # Har kuni 03:00 da muddati o'tgan arxiv mijozlarni tozalaydi
    scheduler.add_job(run_purge, "cron", hour=3, minute=0)
    scheduler.start()
    log.info("Eslatma scheduler ishga tushdi ✅ (eslatma 10:00, arxiv tozalash 03:00)")

    # Ishga tushganda bir marta tekshiramiz
    await run_reminders()
    await run_purge()

    # Doimiy ishlash
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler to'xtatildi")
