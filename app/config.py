"""Markazlashgan konfiguratsiya.

Barcha sozlamalar shu yerda. Hududlar, narxlar va kuryer stavkalarini
shu fayldan oson o'zgartirasiz.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Region:
    """Bitta hudud: nomi, suv narxi va kuryer stavkasi (1 dona uchun)."""
    key: str          # ichki kalit (DB'da saqlanadi)
    name: str         # foydalanuvchiga ko'rinadigan nom
    price: int        # 1 dona suv narxi (so'm)
    courier_rate: int # kuryerga 1 dona yetkazgani uchun (so'm)


# === Hududlar va narxlar (TZ bo'yicha) ===
# Narxni/stavkani o'zgartirish uchun shu ro'yxatni tahrirlang.
REGIONS: list[Region] = [
    Region("toshkent", "Toshkent", price=22000, courier_rate=3000),
    Region("samarqand_ishtixon", "Samarqand (Ishtixon va Kattaqo'rg'on)", price=18000, courier_rate=2500),
    Region("navoi_xatirchi", "Navoi (Xatirchi)", price=19000, courier_rate=2500),
    Region("navoi_mirbozor", "Navoi (Mirbozor Narpay)", price=19000, courier_rate=2500),
]

REGION_BY_KEY: dict[str, Region] = {r.key: r for r in REGIONS}
REGION_BY_NAME: dict[str, Region] = {r.name: r for r in REGIONS}

# === Kuryer ro'yxatdan o'tishda tanlaydigan hududlar ===
# O'zbekistonning barcha ma'muriy hududlari (viloyatlar + Toshkent shahri).
# Bu yetkazish/narx hududlaridan (REGIONS) alohida — kuryer qaysi hududda
# ishlashini ko'rsatish uchun.
COURIER_PROVINCES: list[str] = [
    "Toshkent",            # poytaxt (shahar)
    "Toshkent viloyati",
    "Andijon",
    "Buxoro",
    "Farg'ona",
    "Jizzax",
    "Namangan",
    "Navoiy",
    "Qashqadaryo",
    "Qoraqalpog'iston",
    "Samarqand",
    "Sirdaryo",
    "Surxondaryo",
    "Xorazm",
]

# Lokatsiya manzilidagi kalit so'zlardan hududni avtomatik aniqlash.
# Tartib muhim: aniqrog'i (tuman) umumiyidan (viloyat) oldin turadi.
_REGION_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("ishtixon", "kattaqo", "katta-qo", "иштихан", "иштихон", "катта"), "samarqand_ishtixon"),
    (("xatirchi", "хатирчи"), "navoi_xatirchi"),
    (("narpay", "mirbozor", "oqtosh", "нарпай", "мирбозор", "октош"), "navoi_mirbozor"),
    (("toshkent", "tashkent", "ташкент"), "toshkent"),
    (("samarqand", "samarkand", "самарканд"), "samarqand_ishtixon"),
    (("navoiy", "navoi", "навои", "навоий"), "navoi_xatirchi"),
]


def detect_region(address: str | None) -> Region | None:
    """Geokodlangan manzil matnidan hududni topadi (topilmasa None)."""
    if not address:
        return None
    low = address.lower()
    for keywords, key in _REGION_KEYWORDS:
        if any(k in low for k in keywords):
            return REGION_BY_KEY.get(key)
    return None

# Buyurtma uchun ruxsat etilgan suv miqdori oralig'i (TZ: 2-5)
MIN_BOTTLES = 2
MAX_BOTTLES = 5

# === Global narxlar (boshlang'ich qiymatlar) ===
# Narxlar barcha hududlar uchun bir xil. Admin paneldan tahrirlanadi
# (AppSetting: water_price / courier_rate / bottle_price). REGIONS ro'yxati
# faqat hudud NOMLARI va lokatsiyadan aniqlash uchun qoladi — narx uchun emas.
WATER_PRICE_DEFAULT = 22000    # 1 dona suv narxi (so'm)
COURIER_RATE_DEFAULT = 3000    # kuryerga 1 dona yetkazgani uchun (so'm)
BOTTLE_PRICE_DEFAULT = 0       # 1 dona baklashka shtrafi (qaytarilmasa) — admin kiritadi

# Arxivlangan (yumshoq o'chirilgan) mijoz shu kun ichida qaytmasa — avtomatik
# butunlay o'chadi. ~3 oy.
CLIENT_ARCHIVE_DAYS = 90

# Bonus chegaralari
CLIENT_BONUS_STEP = 100      # mijoz har 100 ta suvda bonus oladi
COURIER_DAILY_BONUS_STEP = 120   # kuryer kuniga 120 ta yetkazsa
COURIER_DAILY_BONUS_AMOUNT = 60000  # qo'shimcha bonus (so'm)


class Settings(BaseSettings):
    """`.env` fayldan o'qiladigan sozlamalar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    client_bot_token: str = "PUT_CLIENT_TOKEN_HERE"
    courier_bot_token: str = "PUT_COURIER_TOKEN_HERE"

    database_url: str = "sqlite+aiosqlite:///./langar.db"

    admin_login: str = "admin"
    admin_password: str = "admin123"
    admin_secret_key: str = "change-me"
    admin_host: str = "0.0.0.0"
    admin_port: int = 8000

    google_maps_api_key: str = ""

    reminder_days: str = "10,15,20,30"

    @property
    def reminder_days_list(self) -> list[int]:
        out = []
        for part in self.reminder_days.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
        return out or [10, 15, 20, 30]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
