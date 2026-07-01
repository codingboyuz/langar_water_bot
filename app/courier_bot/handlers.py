"""Kuryer boti handlerlari (aiogram 3)."""
from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app import events
from app.config import COURIER_PROVINCES, settings
from app.courier_bot.common import CB_DELIVERED, CB_PROCESS, client_confirm_keyboard
from app.db import service as svc
from app.geocode import resolve_text_location, reverse_geocode
from app.i18n import DEFAULT_LANG, LANG_BUTTONS, LANGS, t
from app.utils import fmt_date, money

router = Router()


# --------------------------- FSM holatlari ---------------------------

class Register(StatesGroup):
    lang = State()
    name = State()
    phone = State()
    region = State()
    location = State()


class Deliver(StatesGroup):
    count = State()
    empty_returned = State()
    empty_left = State()


class Feedback(StatesGroup):
    text = State()        # talab va takliflar matni


# --------------------------- klaviaturalar ---------------------------

def _lang_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for label in LANG_BUTTONS:
        kb.button(text=label)
    kb.adjust(len(LANG_BUTTONS))  # barchasi bitta qatorda
    return kb.as_markup(resize_keyboard=True)


def _phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_phone", lang), request_contact=True)]],
        resize_keyboard=True,
    )


def _location_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_location", lang), request_location=True)]],
        resize_keyboard=True,
    )


def _region_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for name in COURIER_PROVINCES:
        kb.button(text=name)
    kb.adjust(2)  # ikkitadan qator — ro'yxat ixcham ko'rinadi
    return kb.as_markup(resize_keyboard=True)


def _main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    """Ro'yxatdan o'tgandan keyin doimiy ko'rinadigan menyu: profil + takliflar."""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=t("c_menu_profile", lang)),
            KeyboardButton(text=t("c_menu_feedback", lang)),
        ]],
        resize_keyboard=True,
    )


def _feedback_cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    """Faqat bekor qilish tugmasi (taklif kiritishda)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_cancel", lang))]],
        resize_keyboard=True,
    )


# Menyu tugmalari har uch tilda — chat (catch-all) handleridan ajratish uchun
_PROFILE_LABELS = {t("c_menu_profile", lang) for lang in LANGS}
_FEEDBACK_LABELS = {t("c_menu_feedback", lang) for lang in LANGS}
_CANCEL_LABELS = {t("btn_cancel", lang) for lang in LANGS}


def _feedback_history_text(items, lang: str) -> str | None:
    """Kuryerning oldingi takliflari ro'yxati (bo'sh bo'lsa None)."""
    if not items:
        return None
    lines = [t("feedback_history_title", lang)]
    for f in items:
        lines.append(f"• {fmt_date(f.created_at)} — {f.text}")
    return "\n".join(lines)


async def _lang_of(tg_id: int, state: FSMContext) -> str:
    """Joriy til: avval FSM, keyin DB, bo'lmasa standart."""
    data = await state.get_data()
    if data.get("lang"):
        return data["lang"]
    courier = await svc.get_courier_by_tg(tg_id)
    return courier.lang if courier and courier.lang else DEFAULT_LANG


# --------------------------- /start va ro'yxatdan o'tish ---------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    courier = await svc.get_courier_by_tg(message.from_user.id)
    if courier and courier.name and courier.phone:
        lang = courier.lang or DEFAULT_LANG
        await message.answer(
            t("c_greet", lang).format(name=courier.name),
            reply_markup=_main_menu_kb(lang),
        )
        return
    # Ro'yxatdan o'tish — til tanlashdan boshlanadi
    await message.answer(t("c_welcome", DEFAULT_LANG))
    await message.answer(t("choose_lang", DEFAULT_LANG), reply_markup=_lang_kb())
    await state.set_state(Register.lang)


@router.message(Register.lang)
async def reg_lang(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in LANG_BUTTONS:
        await message.answer(t("choose_lang", DEFAULT_LANG), reply_markup=_lang_kb())
        return
    lang = LANG_BUTTONS[text]
    await state.update_data(lang=lang)
    await message.answer(t("c_ask_name", lang), reply_markup=ReplyKeyboardRemove())
    await state.set_state(Register.name)


@router.message(Register.name, F.text)
async def reg_name(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    await state.update_data(name=message.text.strip())
    await message.answer(t("ask_phone", lang), reply_markup=_phone_kb(lang))
    await state.set_state(Register.phone)


@router.message(Register.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    await state.update_data(phone=message.contact.phone_number)
    await message.answer(t("c_ask_region", lang), reply_markup=_region_kb())
    await state.set_state(Register.region)


@router.message(Register.phone)
async def reg_phone_invalid(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    await message.answer(t("ask_phone", lang), reply_markup=_phone_kb(lang))


@router.message(Register.region, F.text)
async def reg_region(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    if message.text not in COURIER_PROVINCES:
        await message.answer(t("c_ask_region", lang), reply_markup=_region_kb())
        return
    await state.update_data(region=message.text)
    await message.answer(t("ask_location", lang), reply_markup=_location_kb(lang))
    await state.set_state(Register.location)


async def _finish_courier_register(message: Message, state: FSMContext, lang: str,
                                   lat: float | None, lon: float | None, address: str | None):
    data = await state.get_data()
    courier = await svc.register_courier(
        telegram_id=message.from_user.id,
        name=data["name"],
        phone=data["phone"],
        region=data["region"],
        lang=lang,
        latitude=lat,
        longitude=lon,
        geo_address=address,
    )
    await state.clear()
    await message.answer(
        t("c_registered", lang).format(
            name=courier.name, phone=courier.phone, region=courier.region
        ),
        reply_markup=_main_menu_kb(lang),
    )


@router.message(Register.location, F.location)
async def reg_location(message: Message, state: FSMContext):
    """Telefondan yuborilgan lokatsiya."""
    lang = await _lang_of(message.from_user.id, state)
    lat = message.location.latitude
    lon = message.location.longitude
    address = await reverse_geocode(lat, lon) or f"{lat:.5f}, {lon:.5f}"
    await message.answer(t("detected_address", lang).format(address=address))
    await _finish_courier_register(message, state, lang, lat, lon, address)


@router.message(Register.location, F.text)
async def reg_location_text(message: Message, state: FSMContext):
    """Web/Desktop: xarita havolasi, koordinata yoki manzil matni."""
    lang = await _lang_of(message.from_user.id, state)
    resolved = await resolve_text_location(message.text)
    if not resolved:
        await message.answer(t("location_not_found", lang), reply_markup=_location_kb(lang))
        return
    lat, lon, address = resolved
    await message.answer(t("detected_address", lang).format(address=address))
    await _finish_courier_register(message, state, lang, lat, lon, address)


@router.message(Register.location)
async def reg_location_invalid(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    await message.answer(t("ask_location", lang), reply_markup=_location_kb(lang))


# --------------------------- buyurtmani bajarish ---------------------------

def _delivered_kb(order_id: int, lang: str) -> InlineKeyboardMarkup:
    """Kuryer 'Jarayonda' bosgandan keyin chiqadigan 'Yetkazildi' tugmasi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=t("c_btn_delivered", lang), callback_data=f"{CB_DELIVERED}:{order_id}"
            )]
        ]
    )


@router.callback_query(F.data.startswith(f"{CB_PROCESS}:"))
async def cb_process(call: CallbackQuery):
    order_id = int(call.data.split(":")[1])
    courier = await svc.get_courier_by_tg(call.from_user.id)
    lang = courier.lang if courier and courier.lang else DEFAULT_LANG
    await svc.set_order_process(order_id)
    await call.answer(t("c_taken", lang))
    if call.message:
        # "Jarayonda" tugmasi o'rniga endi "Yetkazildi" tugmasi chiqadi
        await call.message.edit_text(
            (call.message.text or "") + "\n\n" + t("c_status_process", lang),
            reply_markup=_delivered_kb(order_id, lang),
        )


@router.callback_query(F.data.startswith(f"{CB_DELIVERED}:"))
async def cb_delivered(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split(":")[1])
    courier = await svc.get_courier_by_tg(call.from_user.id)
    lang = courier.lang if courier and courier.lang else DEFAULT_LANG
    order = await svc.get_order(order_id)
    await call.answer()
    # Tugmani olib tashlaymiz — qayta bosib bo'lmasin (ma'lumot kiritish boshlandi)
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await state.update_data(order_id=order_id, lang=lang)
    default = order.count if order else ""
    await call.message.answer(t("c_ask_delivered_count", lang).format(default=default))
    await state.set_state(Deliver.count)


@router.message(Deliver.count, F.text)
async def deliver_count(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    if not message.text.isdigit():
        await message.answer(t("c_num_invalid", lang))
        return
    await state.update_data(delivered_count=int(message.text))
    await message.answer(t("c_ask_empty_returned", lang))
    await state.set_state(Deliver.empty_returned)


@router.message(Deliver.empty_returned, F.text)
async def deliver_returned(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    if not message.text.isdigit():
        await message.answer(t("c_num_invalid", lang))
        return
    await state.update_data(empty_returned=int(message.text))
    await message.answer(t("c_ask_empty_left", lang))
    await state.set_state(Deliver.empty_left)


@router.message(Deliver.empty_left, F.text)
async def deliver_left(message: Message, state: FSMContext):
    lang = await _lang_of(message.from_user.id, state)
    if not message.text.isdigit():
        await message.answer(t("c_num_invalid", lang))
        return
    data = await state.get_data()
    order = await svc.mark_delivered(
        order_id=data["order_id"],
        delivered_count=data["delivered_count"],
        empty_returned=data["empty_returned"],
        empty_left=int(message.text),
    )
    await state.clear()
    if order:
        await message.answer(
            t("c_delivered_summary", lang).format(
                id=order.id,
                dc=order.delivered_count,
                er=order.empty_returned,
                el=order.empty_left,
            )
            + "\n\n"
            + t("c_status_delivered_wait", lang)
        )
        # Mijozga tasdiqlash tugmasini yuboramiz (mijoz boti orqali)
        if order.user and order.user.telegram_id:
            await _notify_client_to_confirm(
                order.user.telegram_id, order.id, order.user.lang or DEFAULT_LANG
            )
    else:
        await message.answer(t("c_order_not_found", lang))


async def _notify_client_to_confirm(chat_id: int, order_id: int, lang: str) -> bool:
    """Mijoz botiga «Buyurtmani qabul qildim» tugmali xabar yuboradi.

    Kuryer va mijoz botlari alohida tokenlar — shu sabab Telegram Bot API ga
    to'g'ridan-to'g'ri (httpx) murojaat qilamiz.
    """
    url = f"https://api.telegram.org/bot{settings.client_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": t("client_delivered_confirm", lang).format(order_id=order_id),
        "parse_mode": "HTML",
        "reply_markup": client_confirm_keyboard(order_id, lang),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            return r.status_code == 200 and r.json().get("ok", False)
    except Exception:
        return False


# --------------------------- mening profilim ---------------------------

@router.message(StateFilter(None), F.text.in_(_PROFILE_LABELS))
async def show_profile(message: Message):
    """Kuryerga o'z profili va statistikasini ko'rsatadi (ish haqi, suv, buyurtmalar)."""
    courier = await svc.get_courier_by_tg(message.from_user.id)
    if not courier:
        await message.answer(t("c_welcome", DEFAULT_LANG))
        return
    lang = courier.lang or DEFAULT_LANG
    data = await svc.courier_detail(courier.id)
    if not data:
        return
    status = t("c_status_active" if courier.is_active else "c_status_inactive", lang)
    await message.answer(
        t("c_profile", lang).format(
            id=courier.id,
            name=courier.name,
            phone=courier.phone,
            region=courier.region,
            joined=fmt_date(courier.created_at),
            status=status,
            done=data["orders_done"],
            pending=data["pending_count"],
            bottles=data["bottles"],
            bottles_today=data["bottles_today"],
            rate=money(data["rate"]),
            salary=money(data["salary"]),
            salary_today=money(data["salary_today"]),
        ),
        reply_markup=_main_menu_kb(lang),
    )


# --------------------------- talab va takliflar ---------------------------

@router.message(StateFilter(None), F.text.in_(_FEEDBACK_LABELS))
async def feedback_open(message: Message, state: FSMContext):
    """Kuryer «Talab va takliflar» tugmasini bosdi — oldingilar + yangi so'rov."""
    courier = await svc.get_courier_by_tg(message.from_user.id)
    if not courier:
        await message.answer(t("c_welcome", DEFAULT_LANG))
        return
    lang = courier.lang or DEFAULT_LANG
    history = _feedback_history_text(
        await svc.list_party_feedback("courier", courier.id), lang
    )
    if history:
        await message.answer(history)
    await message.answer(t("feedback_ask", lang), reply_markup=_feedback_cancel_kb(lang))
    await state.set_state(Feedback.text)


@router.message(Feedback.text)
async def feedback_text(message: Message, state: FSMContext):
    courier = await svc.get_courier_by_tg(message.from_user.id)
    lang = courier.lang if courier and courier.lang else DEFAULT_LANG
    if message.text in _CANCEL_LABELS:
        await state.clear()
        await message.answer(t("c_greet", lang).format(name=courier.name if courier else ""),
                             reply_markup=_main_menu_kb(lang))
        return
    text = (message.text or "").strip()
    if not text or not courier:
        await message.answer(t("feedback_ask", lang), reply_markup=_feedback_cancel_kb(lang))
        return
    await svc.add_feedback("courier", courier.id, text)
    events.publish(
        "feedback",
        {"courier_id": courier.id, "name": courier.name, "preview": text[:80]},
    )
    await state.clear()
    await message.answer(t("feedback_sent", lang), reply_markup=_main_menu_kb(lang))


# --------------------------- admin bilan chat ---------------------------

@router.message(StateFilter(None), F.text)
async def courier_to_admin(message: Message):
    """Holatsiz (registratsiya/yetkazish jarayonidan tashqari) yozilgan matn —
    adminga yuboriladigan chat xabari sifatida saqlanadi."""
    if message.text.startswith("/"):
        return  # buyruqlar (masalan /start) chatga yozilmaydi
    courier = await svc.get_courier_by_tg(message.from_user.id)
    if not courier:
        # ro'yxatdan o'tmagan — avval /start
        await message.answer(t("c_welcome", DEFAULT_LANG))
        return
    lang = courier.lang or DEFAULT_LANG
    await svc.add_chat_message("courier", courier.id, "in", message.text)
    events.publish(
        "chat_message",
        {"kind": "courier", "party_id": courier.id, "name": courier.name, "preview": message.text[:80]},
    )
    await message.answer(t("c_chat_sent", lang))
