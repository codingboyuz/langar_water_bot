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
    region = State()     # zaxira: ro'yxatdagi hudud noaniq bo'lsa qo'lda tanlanadi
    count = State()
    confirm = State()


class Settings(StatesGroup):
    menu = State()        # sozlamalar menyusi (til / lokatsiya)
    lang = State()
    location = State()    # lokatsiyani qo'yish / o'zgartirish


class Feedback(StatesGroup):
    text = State()        # talab va takliflar matni
