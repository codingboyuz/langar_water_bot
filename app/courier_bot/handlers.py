"""Kuryer boti handlerlari (aiogram 3)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.config import COURIER_PROVINCES
from app.courier_bot.common import CB_DELIVERED, CB_PROCESS
from app.db import service as svc
from app.i18n import DEFAULT_LANG, LANG_BUTTONS, t

router = Router()


# --------------------------- FSM holatlari ---------------------------

class Register(StatesGroup):
    lang = State()
    name = State()
    phone = State()
    region = State()


class Deliver(StatesGroup):
    count = State()
    empty_returned = State()
    empty_left = State()


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


def _region_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for name in COURIER_PROVINCES:
        kb.button(text=name)
    kb.adjust(2)  # ikkitadan qator — ro'yxat ixcham ko'rinadi
    return kb.as_markup(resize_keyboard=True)


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
        await message.answer(
            t("c_greet", courier.lang or DEFAULT_LANG).format(name=courier.name),
            reply_markup=ReplyKeyboardRemove(),
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
    data = await state.get_data()
    courier = await svc.register_courier(
        telegram_id=message.from_user.id,
        name=data["name"],
        phone=data["phone"],
        region=message.text,
        lang=lang,
    )
    await state.clear()
    await message.answer(
        t("c_registered", lang).format(
            name=courier.name, phone=courier.phone, region=courier.region
        ),
        reply_markup=ReplyKeyboardRemove(),
    )


# --------------------------- buyurtmani bajarish ---------------------------

@router.callback_query(F.data.startswith(f"{CB_PROCESS}:"))
async def cb_process(call: CallbackQuery):
    order_id = int(call.data.split(":")[1])
    courier = await svc.get_courier_by_tg(call.from_user.id)
    lang = courier.lang if courier and courier.lang else DEFAULT_LANG
    await svc.set_order_process(order_id)
    await call.answer(t("c_taken", lang))
    if call.message:
        await call.message.edit_text(
            (call.message.text or "") + "\n\n" + t("c_status_process", lang)
        )


@router.callback_query(F.data.startswith(f"{CB_DELIVERED}:"))
async def cb_delivered(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split(":")[1])
    courier = await svc.get_courier_by_tg(call.from_user.id)
    lang = courier.lang if courier and courier.lang else DEFAULT_LANG
    order = await svc.get_order(order_id)
    await call.answer()
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
        )
    else:
        await message.answer(t("c_order_not_found", lang))
