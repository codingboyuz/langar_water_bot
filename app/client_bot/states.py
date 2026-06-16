"""FSM holatlari (aiogram 3)."""
from aiogram.fsm.state import State, StatesGroup


class Register(StatesGroup):
    lang = State()
    full_name = State()
    phone = State()
    extra_phone_q = State()
    extra_phone_input = State()
    location = State()
    house = State()
    confirm = State()


class NewOrder(StatesGroup):
    location = State()   # yetkazish manzili (lokatsiya)
    region = State()     # zaxira: lokatsiyadan hudud aniqlanmasa qo'lda tanlanadi
    count = State()
    confirm = State()


class Settings(StatesGroup):
    lang = State()
