"""Mijoz boti handlerlari (aiogram 3)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app import events
from app.config import REGION_BY_NAME, REGIONS, detect_region
from app.client_bot import keyboards as kb
from app.client_bot.states import NewOrder, Register, Settings
from app.courier_bot.common import CB_CLIENT_CONFIRM
from app.db import service as svc
from app.geocode import reverse_geocode
from app.i18n import (
    DEFAULT_LANG,
    LANG_BUTTONS,
    LANGS,
    status_text,
    t,
)
from app.utils import fmt_date, money

router = Router()


# --------------------------- yordamchilar ---------------------------

def _matches(text: str | None, key: str) -> bool:
    """Matn istalgan tildagi `key` tugmasiga mosmi?"""
    return bool(text) and any(text == t(key, lang) for lang in LANGS)


async def _lang_of(message: Message, state: FSMContext) -> str:
    data = await state.get_data()
    if data.get("lang"):
        return data["lang"]
    user = await svc.get_user_by_tg(message.from_user.id)
    return user.lang if user else DEFAULT_LANG


# --------------------------- /start ---------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await svc.get_user_by_tg(message.from_user.id)
    if user:
        await message.answer(t("menu_title", user.lang), reply_markup=kb.main_menu_kb(user.lang))
        return
    await message.answer(t("welcome", DEFAULT_LANG), reply_markup=kb.start_kb(DEFAULT_LANG))
    await state.set_state(Register.lang)


# --------------------------- Ro'yxatdan o'tish ---------------------------

@router.message(Register.lang)
async def reg_lang(message: Message, state: FSMContext):
    text = message.text or ""
    # START tugmasi bosilgan bo'lsa — til tanlashni ko'rsatamiz
    if _matches(text, "btn_start"):
        await message.answer(t("choose_lang", DEFAULT_LANG), reply_markup=kb.lang_kb())
        return
    # til tanlandi
    if text in LANG_BUTTONS:
        lang = LANG_BUTTONS[text]
        await state.update_data(lang=lang)
        # til klaviaturasini olib tashlaymiz, F.I.Sh matn ko'rinishida kiritiladi
        await message.answer(t("ask_fullname", lang), reply_markup=ReplyKeyboardRemove())
        await state.set_state(Register.full_name)
        return
    await message.answer(t("choose_lang", DEFAULT_LANG), reply_markup=kb.lang_kb())


@router.message(Register.full_name, F.text)
async def reg_full_name(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await state.update_data(full_name=message.text.strip())
    await message.answer(t("ask_phone", lang), reply_markup=kb.phone_kb(lang))
    await state.set_state(Register.phone)


@router.message(Register.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await state.update_data(phone=message.contact.phone_number)
    await message.answer(t("ask_extra_phone_q", lang), reply_markup=kb.yes_no_kb(lang))
    await state.set_state(Register.extra_phone_q)


@router.message(Register.phone)
async def reg_phone_invalid(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await message.answer(t("ask_phone", lang), reply_markup=kb.phone_kb(lang))


@router.message(Register.extra_phone_q)
async def reg_extra_q(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    if _matches(message.text, "btn_yes"):
        await message.answer(t("ask_extra_phone_input", lang), reply_markup=ReplyKeyboardRemove())
        await state.set_state(Register.extra_phone_input)
        return
    # yo'q
    await state.update_data(extra_phone="")
    await message.answer(t("ask_location", lang), reply_markup=kb.location_kb(lang))
    await state.set_state(Register.location)


@router.message(Register.extra_phone_input, F.text)
async def reg_extra_input(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await state.update_data(extra_phone=message.text.strip())
    await message.answer(t("ask_location", lang), reply_markup=kb.location_kb(lang))
    await state.set_state(Register.location)


@router.message(Register.location, F.location)
async def reg_location(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    lat = message.location.latitude
    lon = message.location.longitude
    address = await reverse_geocode(lat, lon) or f"{lat:.5f}, {lon:.5f}"
    await state.update_data(latitude=lat, longitude=lon, geo_address=address)
    await message.answer(t("detected_address", lang).format(address=address))
    await message.answer(t("ask_house", lang), reply_markup=ReplyKeyboardRemove())
    await state.set_state(Register.house)


@router.message(Register.location)
async def reg_location_invalid(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await message.answer(t("ask_location", lang), reply_markup=kb.location_kb(lang))


@router.message(Register.house, F.text)
async def reg_house(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    await state.update_data(house=message.text.strip())
    data = await state.get_data()

    # Hududni lokatsiya manzilidan avtomatik aniqlaymiz — alohida so'ramaymiz.
    region = detect_region(data.get("geo_address"))
    region_name = region.name if region else REGIONS[0].name
    await state.update_data(region=region_name)

    summary = t("confirm_register", lang).format(
        fullname=data["full_name"],
        phone=data["phone"],
        extra=data.get("extra_phone") or "—",
        address=data.get("geo_address") or "—",
        house=data.get("house") or "—",
        region=region_name,
    )
    await message.answer(summary, reply_markup=kb.confirm_edit_kb(lang))
    await state.set_state(Register.confirm)


@router.message(Register.confirm)
async def reg_confirm(message: Message, state: FSMContext):
    lang = await _lang_of(message, state)
    if _matches(message.text, "btn_edit"):
        await message.answer(t("ask_fullname", lang))
        await state.set_state(Register.full_name)
        return
    if _matches(message.text, "btn_confirm"):
        data = await state.get_data()
        await svc.create_user(
            {
                "telegram_id": message.from_user.id,
                "lang": lang,
                "full_name": data["full_name"],
                "phone": data["phone"],
                "extra_phone": data.get("extra_phone") or None,
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "geo_address": data.get("geo_address"),
                "house": data.get("house"),
                "region": data["region"],
            }
        )
        await state.clear()
        await message.answer(t("register_done", lang), reply_markup=kb.main_menu_kb(lang))
        return
    # tushunarsiz javob — tasdiqlash/qayta kiritish tugmalarini qayta ko'rsatamiz
    await message.answer(t("btn_confirm", lang), reply_markup=kb.confirm_edit_kb(lang))


# --------------------------- Sozlamalar (til) ---------------------------

@router.message(Settings.lang)
async def settings_lang(message: Message, state: FSMContext):
    if message.text in LANG_BUTTONS:
        lang = LANG_BUTTONS[message.text]
        await svc.update_user_lang(message.from_user.id, lang)
        await state.clear()
        await message.answer(t("menu_title", lang), reply_markup=kb.main_menu_kb(lang))
        return
    await message.answer(t("choose_lang", DEFAULT_LANG), reply_markup=kb.lang_kb())


# --------------------------- Yangi buyurtma ---------------------------

@router.message(NewOrder.location, F.location)
async def order_location(message: Message, state: FSMContext):
    """Yetkazish manzilini qabul qiladi (joriy yoki xaritadan istalgan joy)."""
    user = await svc.get_user_by_tg(message.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    lat = message.location.latitude
    lon = message.location.longitude
    address = await reverse_geocode(lat, lon) or f"{lat:.5f}, {lon:.5f}"
    await state.update_data(latitude=lat, longitude=lon, geo_address=address)

    region = detect_region(address)
    if region:
        await state.update_data(region=region.name)
        await message.answer(t("detected_address", lang).format(address=address))
        await message.answer(t("order_choose_count", lang), reply_markup=kb.count_kb(lang))
        await state.set_state(NewOrder.count)
    else:
        # hudud aniqlanmadi — qo'lda tanlanadi
        await message.answer(t("detected_address", lang).format(address=address))
        await message.answer(t("order_region_undetected", lang), reply_markup=kb.region_kb(lang))
        await state.set_state(NewOrder.region)


@router.message(NewOrder.location)
async def order_location_invalid(message: Message, state: FSMContext):
    user = await svc.get_user_by_tg(message.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    if _matches(message.text, "btn_cancel"):
        await state.clear()
        await message.answer(t("order_canceled", lang), reply_markup=kb.main_menu_kb(lang))
        return
    await message.answer(t("order_send_location", lang), reply_markup=kb.order_location_kb(lang))


@router.message(NewOrder.region, F.text)
async def order_region(message: Message, state: FSMContext):
    """Zaxira: hudud lokatsiyadan aniqlanmaganda qo'lda tanlash."""
    user = await svc.get_user_by_tg(message.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    if _matches(message.text, "btn_cancel"):
        await state.clear()
        await message.answer(t("order_canceled", lang), reply_markup=kb.main_menu_kb(lang))
        return
    if message.text not in REGION_BY_NAME:
        await message.answer(t("order_region_undetected", lang), reply_markup=kb.region_kb(lang))
        return
    await state.update_data(region=message.text)
    await message.answer(t("order_choose_count", lang), reply_markup=kb.count_kb(lang))
    await state.set_state(NewOrder.count)


@router.message(NewOrder.count, F.text)
async def order_count(message: Message, state: FSMContext):
    user = await svc.get_user_by_tg(message.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    if _matches(message.text, "btn_cancel"):
        await state.clear()
        await message.answer(t("order_canceled", lang), reply_markup=kb.main_menu_kb(lang))
        return
    text = message.text.strip()
    # qo'lda istalgan musbat butun son
    if not text.isdigit() or int(text) < 1:
        await message.answer(t("order_count_invalid", lang), reply_markup=kb.count_kb(lang))
        return
    count = int(text)
    data = await state.get_data()
    region = REGION_BY_NAME[data["region"]]
    total = region.price * count
    await state.update_data(count=count)
    summary = t("order_summary", lang).format(
        fullname=user.full_name,
        phone=user.phone,
        address=data.get("geo_address") or "—",
        region=region.name,
        count=count,
        price=money(region.price),
        total=money(total),
    )
    await message.answer(summary, reply_markup=kb.confirm_cancel_kb(lang))
    await state.set_state(NewOrder.confirm)


@router.message(NewOrder.confirm)
async def order_confirm(message: Message, state: FSMContext):
    user = await svc.get_user_by_tg(message.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    if _matches(message.text, "btn_confirm"):
        data = await state.get_data()
        order = await svc.create_order(
            user,
            data["region"],
            data["count"],
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            geo_address=data.get("geo_address"),
        )
        await state.clear()
        await message.answer(
            t("order_accepted", lang).format(order_id=order.id),
            reply_markup=kb.main_menu_kb(lang),
        )
        return
    await state.clear()
    await message.answer(t("order_canceled", lang), reply_markup=kb.main_menu_kb(lang))


# --------------------------- Buyurtmani qabul qilganni tasdiqlash ---------------------------

@router.callback_query(F.data.startswith(f"{CB_CLIENT_CONFIRM}:"))
async def cb_confirm_received(call: CallbackQuery):
    """Mijoz «Buyurtmani qabul qildim» tugmasini bosadi -> buyurtma yakunlanadi."""
    order_id = int(call.data.split(":")[1])
    user = await svc.get_user_by_tg(call.from_user.id)
    lang = user.lang if user else DEFAULT_LANG
    await svc.confirm_received(order_id)
    await call.answer()
    if call.message:
        try:
            await call.message.edit_text(t("client_order_completed", lang))
        except Exception:
            await call.message.answer(t("client_order_completed", lang))


# --------------------------- Asosiy menyu (holatsiz) ---------------------------

@router.message(StateFilter(None), F.text)
async def menu_router(message: Message, state: FSMContext):
    user = await svc.get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", DEFAULT_LANG))
        return
    lang = user.lang
    text = message.text

    if _matches(text, "menu_new_order"):
        await message.answer(t("order_send_location", lang), reply_markup=kb.order_location_kb(lang))
        await state.set_state(NewOrder.location)

    elif _matches(text, "menu_id"):
        await message.answer(t("your_id", lang).format(phone=user.phone))

    elif _matches(text, "menu_history"):
        await message.answer(await _history_text(user, lang))

    elif _matches(text, "menu_empty"):
        await message.answer(t("empty_bottles_info", lang).format(count=user.empty_bottles))

    elif _matches(text, "menu_bonus"):
        total = await svc.total_delivered_bottles(user.id)
        from app.config import CLIENT_BONUS_STEP
        remain = CLIENT_BONUS_STEP - (total % CLIENT_BONUS_STEP) if total else CLIENT_BONUS_STEP
        await message.answer(
            t("bonus_info", lang).format(total=total, step=CLIENT_BONUS_STEP, remain=remain)
        )

    elif _matches(text, "menu_settings"):
        await message.answer(t("choose_lang", lang), reply_markup=kb.lang_kb())
        await state.set_state(Settings.lang)

    else:
        # Menyu tugmasi emas — adminga (operatorga) chat xabari sifatida yuboramiz
        await svc.add_chat_message("client", user.id, "in", text)
        events.publish(
            "chat_message",
            {"kind": "client", "party_id": user.id, "name": user.full_name, "preview": text[:80]},
        )
        await message.answer(t("client_chat_sent", lang), reply_markup=kb.main_menu_kb(lang))


async def _history_text(user, lang: str) -> str:
    orders = await svc.get_user_orders(user.id)
    if not orders:
        return t("history_empty", lang)
    lines = [t("history_header", lang)]
    for o in orders:
        lines.append(
            f"#{o.id} • {fmt_date(o.created_at)}\n"
            f"   🌍 {o.region}\n"
            f"   💧 {o.count} ta — 💰 {money(o.total_price)} so'm\n"
            f"   {status_text(o.status, lang)}"
        )
    return "\n\n".join(lines)
