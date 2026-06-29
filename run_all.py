"""Hammasini bitta buyruq bilan ishga tushirish:
   - mijoz boti
   - kuryer boti
   - admin panel (web)
   - eslatma scheduler

Ishga tushirish:  python run_all.py

Eslatma: ishlab chiqishda komponentlarni alohida ham ishga tushirsa bo'ladi
(README'ga qarang). Bu fayl barchasini bitta event loop'da yuritadi.
"""
from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.admin.main import app as admin_app
from app.client_bot.handlers import router as client_router
from app.config import settings
from app.courier_bot.handlers import router as courier_router
from app.db.base import init_db
from app.reminders import run_purge, run_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("run_all")


def _bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def main() -> None:
    await init_db()

    # --- Mijoz boti ---
    client_bot = _bot(settings.client_bot_token)
    client_dp = Dispatcher(storage=MemoryStorage())
    client_dp.include_router(client_router)
    await client_bot.delete_webhook(drop_pending_updates=True)

    # --- Kuryer boti ---
    courier_bot = _bot(settings.courier_bot_token)
    courier_dp = Dispatcher(storage=MemoryStorage())
    courier_dp.include_router(courier_router)
    await courier_bot.delete_webhook(drop_pending_updates=True)

    # --- Admin panel (web) ---
    config = uvicorn.Config(
        admin_app, host=settings.admin_host, port=settings.admin_port, log_level="info"
    )
    server = uvicorn.Server(config)

    # --- Eslatma scheduler ---
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_reminders, "cron", hour=10, minute=0)
    scheduler.add_job(run_purge, "cron", hour=3, minute=0)
    scheduler.start()

    log.info("Hammasi ishga tushdi ✅  Admin: http://%s:%s", settings.admin_host, settings.admin_port)

    await asyncio.gather(
        client_dp.start_polling(client_bot),
        courier_dp.start_polling(courier_bot),
        server.serve(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("To'xtatildi")
