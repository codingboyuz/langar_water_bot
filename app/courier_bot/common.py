"""Kuryer boti uchun umumiy: buyurtma matni va inline tugmalar.

Bu yerdagi `order_caption` va callback formati admin panel tomonidan ham
ishlatiladi (admin xabarni shu bot orqali kuryerga yuboradi).
"""
from __future__ import annotations

from app.i18n import t
from app.utils import money

# callback_data formati: "<action>:<order_id>"
CB_PROCESS = "process"
CB_DELIVERED = "delivered"


def order_caption(order, user, lang: str = "uz") -> str:
    """Kuryerga yuboriladigan buyurtma matni (kuryer tilida).

    Manzil buyurtma uchun tanlangan joydan olinadi (har safar istalgan joy
    bo'lishi mumkin); bo'lmasa mijozning ro'yxatdagi manzili ishlatiladi.
    """
    lat = getattr(order, "latitude", None)
    lon = getattr(order, "longitude", None)
    address = getattr(order, "geo_address", None) or user.geo_address or "—"

    lines = [
        t("c_new_order", lang),
        "",
        f"{t('c_lbl_order', lang)}: #{order.id}",
        f"{t('c_lbl_client', lang)}: {user.full_name}",
        f"{t('c_lbl_phone', lang)}: {user.phone}",
    ]
    if user.extra_phone:
        lines.append(f"{t('c_lbl_extra', lang)}: {user.extra_phone}")
    lines += [
        f"{t('c_lbl_region', lang)}: {order.region}",
        f"{t('c_lbl_address', lang)}: {address}",
        f"{t('c_lbl_house', lang)}: {user.house or '—'}",
        f"{t('c_lbl_water', lang)}: {order.count} ta",
        f"{t('c_lbl_sum', lang)}: {money(order.total_price)} so'm",
    ]
    if lat is not None and lon is not None:
        lines.append(f"{t('c_lbl_maps', lang)}: https://maps.google.com/?q={lat},{lon}")
    return "\n".join(lines)


def order_keyboard(order_id: int, lang: str = "uz") -> dict:
    """Telegram Bot API uchun inline keyboard (raw dict — admin httpx bilan yuboradi)."""
    return {
        "inline_keyboard": [
            [
                {"text": t("c_btn_process", lang), "callback_data": f"{CB_PROCESS}:{order_id}"},
                {"text": t("c_btn_delivered", lang), "callback_data": f"{CB_DELIVERED}:{order_id}"},
            ]
        ]
    }
