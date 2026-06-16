"""Mijoz boti uchun klaviaturalar."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.config import REGIONS
from app.i18n import LANG_BUTTONS, t


def start_kb(lang: str = "uz") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("btn_start", lang))
    return kb.as_markup(resize_keyboard=True)


def lang_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for label in LANG_BUTTONS:
        kb.button(text=label)
    kb.adjust(len(LANG_BUTTONS))  # barchasi bitta qatorda
    return kb.as_markup(resize_keyboard=True)


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_phone", lang), request_contact=True)]],
        resize_keyboard=True,
    )


def yes_no_kb(lang: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("btn_yes", lang))
    kb.button(text=t("btn_no", lang))
    return kb.as_markup(resize_keyboard=True)


def location_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_location", lang), request_location=True)]],
        resize_keyboard=True,
    )


def region_kb(lang: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for r in REGIONS:
        kb.button(text=r.name)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def confirm_edit_kb(lang: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("btn_confirm", lang))
    kb.button(text=t("btn_edit", lang))
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def confirm_cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("btn_confirm", lang))
    kb.button(text=t("btn_cancel", lang))
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def order_location_kb(lang: str) -> ReplyKeyboardMarkup:
    """Buyurtma manzili: joriy lokatsiya tugmasi + bekor qilish.
    (Istalgan joyni 📎 → Lokatsiya orqali ham yuborsa bo'ladi.)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("btn_share_location", lang), request_location=True)],
            [KeyboardButton(text=t("btn_cancel", lang))],
        ],
        resize_keyboard=True,
    )


def count_kb(lang: str) -> ReplyKeyboardMarkup:
    """Son qo'lda kiritiladi — faqat bekor qilish tugmasi qoladi."""
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("btn_cancel", lang))
    return kb.as_markup(resize_keyboard=True)


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=t("menu_new_order", lang))
    kb.button(text=t("menu_history", lang))
    kb.button(text=t("menu_id", lang))
    kb.button(text=t("menu_empty", lang))
    kb.button(text=t("menu_bonus", lang))
    kb.button(text=t("menu_settings", lang))
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)
