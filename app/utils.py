"""Kichik yordamchi funksiyalar."""
from __future__ import annotations

from datetime import datetime, timezone


def money(value: int | float | None) -> str:
    """66000 -> '66 000' (so'm uchun chiroyli ko'rinish)."""
    if value is None:
        value = 0
    return f"{int(value):,}".replace(",", " ")


def now() -> datetime:
    """Vaqt zonasiz (naive) UTC vaqt — SQLite bilan mos."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def fmt_date(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y")
