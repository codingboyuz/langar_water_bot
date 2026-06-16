"""Uch tilli matnlar: uz / ru / en.

Foydalanish:  t("welcome", lang)  ->  shu tildagi matn.
Formatlash:   t("order_total", lang).format(count=3, price=66000)
"""
from __future__ import annotations

DEFAULT_LANG = "uz"
LANGS = ("uz", "ru", "en")

# Til tanlash tugmalari uchun (matn -> kod)
LANG_BUTTONS = {
    "🇺🇿 O'zbekcha": "uz",
    "🇷🇺 Русский": "ru",
    "🇬🇧 English": "en",
}

TEXTS: dict[str, dict[str, str]] = {
    # --- Start / til ---
    "welcome": {
        "uz": "👋 Assalomu alaykum! Botimizga xush kelibsiz.\n\nSiz bu bot orqali suvga buyurtma berishingiz mumkin. 💧\n\nBoshlash uchun pastdagi tugmani bosing.",
        "ru": "👋 Здравствуйте! Добро пожаловать в наш бот.\n\nЧерез этот бот вы можете заказать воду. 💧\n\nНажмите кнопку ниже, чтобы начать.",
        "en": "👋 Hello! Welcome to our bot.\n\nYou can order water through this bot. 💧\n\nPress the button below to start.",
    },
    "btn_start": {"uz": "🚀 START", "ru": "🚀 СТАРТ", "en": "🚀 START"},
    "choose_lang": {
        "uz": "🌐 Tilni tanlang:",
        "ru": "🌐 Выберите язык:",
        "en": "🌐 Choose a language:",
    },
    # --- Ro'yxatdan o'tish ---
    "ask_fullname": {
        "uz": "👤 F.I.Sh. ni kiriting (masalan: Aliyev Vali Soliyevich):",
        "ru": "👤 Введите Ф.И.О. (например: Алиев Вали Солиевич):",
        "en": "👤 Enter your full name (e.g.: John William Smith):",
    },
    "ask_phone": {
        "uz": "📞 Telefon raqamingizni yuboring:",
        "ru": "📞 Отправьте свой номер телефона:",
        "en": "📞 Share your phone number:",
    },
    "btn_share_phone": {
        "uz": "📞 Telefon raqamni yuborish",
        "ru": "📞 Отправить номер",
        "en": "📞 Share phone number",
    },
    "ask_extra_phone_q": {
        "uz": "➕ Qo'shimcha raqam mavjudmi?",
        "ru": "➕ Есть ли дополнительный номер?",
        "en": "➕ Do you have an additional number?",
    },
    "ask_extra_phone_input": {
        "uz": "➕ Qo'shimcha raqamni kiriting:",
        "ru": "➕ Введите дополнительный номер:",
        "en": "➕ Enter the additional number:",
    },
    "ask_location": {
        "uz": "📍 Manzilingizni yuboring (lokatsiya):",
        "ru": "📍 Отправьте свою геолокацию:",
        "en": "📍 Share your location:",
    },
    "btn_share_location": {
        "uz": "📍 Lokatsiyani yuborish",
        "ru": "📍 Отправить геолокацию",
        "en": "📍 Share location",
    },
    "detected_address": {
        "uz": "🗺 Aniqlangan manzil: {address}",
        "ru": "🗺 Определённый адрес: {address}",
        "en": "🗺 Detected address: {address}",
    },
    "ask_house": {
        "uz": "🏠 Uy ma'lumotini kiriting (masalan: 3-podyezd, 23-xonadon):",
        "ru": "🏠 Введите данные дома (например: 3-подъезд, 23-квартира):",
        "en": "🏠 Enter apartment details (e.g.: entrance 3, apt 23):",
    },
    "ask_region": {
        "uz": "🌍 Hududingizni tanlang:",
        "ru": "🌍 Выберите ваш регион:",
        "en": "🌍 Choose your region:",
    },
    "confirm_register": {
        "uz": "🧾 Ma'lumotlaringizni tekshiring:\n\n👤 F.I.Sh.: {fullname}\n📞 Telefon: {phone}\n📞 Qo'shimcha: {extra}\n🗺 Manzil: {address}\n🏠 Uy: {house}\n🌍 Hudud: {region}\n\nMa'lumotlar to'g'rimi?",
        "ru": "🧾 Проверьте свои данные:\n\n👤 Ф.И.О.: {fullname}\n📞 Телефон: {phone}\n📞 Доп.: {extra}\n🗺 Адрес: {address}\n🏠 Дом: {house}\n🌍 Регион: {region}\n\nВсё верно?",
        "en": "🧾 Check your details:\n\n👤 Name: {fullname}\n📞 Phone: {phone}\n📞 Extra: {extra}\n🗺 Address: {address}\n🏠 Apt: {house}\n🌍 Region: {region}\n\nIs everything correct?",
    },
    "register_done": {
        "uz": "✅ Ro'yxatdan o'tish yakunlandi! Endi buyurtma berishingiz mumkin.",
        "ru": "✅ Регистрация завершена! Теперь вы можете заказать.",
        "en": "✅ Registration complete! You can now place an order.",
    },
    # --- Umumiy tugmalar ---
    "btn_yes": {"uz": "✅ Ha", "ru": "✅ Да", "en": "✅ Yes"},
    "btn_no": {"uz": "❌ Yo'q", "ru": "❌ Нет", "en": "❌ No"},
    "btn_edit": {"uz": "✏️ Qayta kiritish", "ru": "✏️ Изменить", "en": "✏️ Edit"},
    "btn_cancel": {"uz": "🚫 Bekor qilish", "ru": "🚫 Отмена", "en": "🚫 Cancel"},
    "btn_confirm": {"uz": "✅ Tasdiqlash", "ru": "✅ Подтвердить", "en": "✅ Confirm"},
    "btn_back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    # --- Asosiy menyu ---
    "menu_title": {
        "uz": "🏠 Asosiy menyu",
        "ru": "🏠 Главное меню",
        "en": "🏠 Main menu",
    },
    "menu_id": {"uz": "🆔 ID raqam", "ru": "🆔 ID номер", "en": "🆔 ID number"},
    "menu_history": {"uz": "📜 Buyurtmalar tarixi", "ru": "📜 История заказов", "en": "📜 Order history"},
    "menu_empty": {"uz": "📦 Bo'sh baklashkalar", "ru": "📦 Пустые баклажки", "en": "📦 Empty bottles"},
    "menu_bonus": {"uz": "🎁 Bonuslar", "ru": "🎁 Бонусы", "en": "🎁 Bonuses"},
    "menu_new_order": {"uz": "🛒 Yangi buyurtma", "ru": "🛒 Новый заказ", "en": "🛒 New order"},
    "menu_settings": {"uz": "⚙️ Til / Sozlamalar", "ru": "⚙️ Язык / Настройки", "en": "⚙️ Language / Settings"},
    # --- Menyu javoblari ---
    "your_id": {
        "uz": "🆔 Sizning ID raqamingiz (telefon): {phone}",
        "ru": "🆔 Ваш ID номер (телефон): {phone}",
        "en": "🆔 Your ID number (phone): {phone}",
    },
    "history_empty": {
        "uz": "📭 Siz hali buyurtma bermagansiz.",
        "ru": "📭 Вы ещё не делали заказов.",
        "en": "📭 You have no orders yet.",
    },
    "history_header": {
        "uz": "📜 Buyurtmalar tarixi:\n",
        "ru": "📜 История заказов:\n",
        "en": "📜 Order history:\n",
    },
    "empty_bottles_info": {
        "uz": "📦 Sizda hozir {count} ta bo'sh baklashka bor.\nKuryer kelganda qaytarib berishingiz mumkin.",
        "ru": "📦 У вас сейчас {count} пустых баклажек.\nВы можете вернуть их курьеру.",
        "en": "📦 You currently have {count} empty bottles.\nYou can return them to the courier.",
    },
    "bonus_info": {
        "uz": "🎁 Bonus tizimi\n\n💧 Jami olingan suv: {total} ta\n🎯 Maqsad: har {step} tada bonus\n📊 Keyingi bonusgacha: {remain} ta\n\nBonus to'planganda administrator siz bilan bog'lanadi.",
        "ru": "🎁 Бонусная система\n\n💧 Всего получено воды: {total} шт.\n🎯 Цель: бонус за каждые {step}\n📊 До следующего бонуса: {remain} шт.\n\nКогда бонус накопится, администратор свяжется с вами.",
        "en": "🎁 Bonus system\n\n💧 Total water received: {total}\n🎯 Goal: a bonus every {step}\n📊 Until next bonus: {remain}\n\nWhen a bonus is earned, the administrator will contact you.",
    },
    # --- Buyurtma ---
    "order_send_location": {
        "uz": "📍 Yetkazib berish manzilini yuboring (lokatsiya).\n\nHozirgi joyingizni yuborishingiz yoki 📎 (qisqich) → «Lokatsiya» orqali xaritada istalgan joyni belgilab yuborishingiz mumkin. Hudud manzildan avtomatik aniqlanadi.",
        "ru": "📍 Отправьте адрес доставки (геолокацию).\n\nМожно отправить текущее местоположение или через 📎 → «Геопозиция» выбрать любое место на карте. Регион определится автоматически.",
        "en": "📍 Send the delivery address (location).\n\nYou can send your current location or pick any place on the map via 📎 → «Location». The region is detected automatically.",
    },
    "order_region_undetected": {
        "uz": "🌍 Manzildan hudud aniqlanmadi. Iltimos, hududni tanlang:",
        "ru": "🌍 Не удалось определить регион по адресу. Пожалуйста, выберите регион:",
        "en": "🌍 Could not detect the region from the address. Please choose a region:",
    },
    "order_choose_region": {
        "uz": "🌍 Yetkazib berish hududini tanlang:",
        "ru": "🌍 Выберите регион доставки:",
        "en": "🌍 Choose the delivery region:",
    },
    "order_choose_count": {
        "uz": "💧 Nechta suv kerak? Sonni kiriting (masalan: 3):",
        "ru": "💧 Сколько воды нужно? Введите число (например: 3):",
        "en": "💧 How many bottles? Enter a number (e.g.: 3):",
    },
    "order_count_invalid": {
        "uz": "❗️ Iltimos, 1 dan katta butun son kiriting (masalan: 5):",
        "ru": "❗️ Введите целое число больше 0 (например: 5):",
        "en": "❗️ Please enter a whole number greater than 0 (e.g.: 5):",
    },
    "order_summary": {
        "uz": "🧾 Buyurtmani tasdiqlang:\n\n👤 {fullname}\n📞 {phone}\n📍 Manzil: {address}\n🌍 Hudud: {region}\n💧 Miqdor: {count} ta\n💰 Hisob: {count} × {price} = {total} so'm\n\nTasdiqlaysizmi?",
        "ru": "🧾 Подтвердите заказ:\n\n👤 {fullname}\n📞 {phone}\n📍 Адрес: {address}\n🌍 Регион: {region}\n💧 Количество: {count} шт.\n💰 Итого: {count} × {price} = {total} сум\n\nПодтверждаете?",
        "en": "🧾 Confirm your order:\n\n👤 {fullname}\n📞 {phone}\n📍 Address: {address}\n🌍 Region: {region}\n💧 Amount: {count} pcs\n💰 Total: {count} × {price} = {total} sum\n\nConfirm?",
    },
    "order_accepted": {
        "uz": "✅ Buyurtmangiz qabul qilindi!\n\n📦 Buyurtma raqami: #{order_id}\nTez orada kuryerlarimiz siz bilan bog'lanishadi. 🚚",
        "ru": "✅ Ваш заказ принят!\n\n📦 Номер заказа: #{order_id}\nСкоро наши курьеры свяжутся с вами. 🚚",
        "en": "✅ Your order has been accepted!\n\n📦 Order number: #{order_id}\nOur couriers will contact you soon. 🚚",
    },
    "order_canceled": {
        "uz": "🚫 Buyurtma bekor qilindi.",
        "ru": "🚫 Заказ отменён.",
        "en": "🚫 Order canceled.",
    },
    "not_registered": {
        "uz": "Iltimos, avval ro'yxatdan o'ting. /start ni bosing.",
        "ru": "Пожалуйста, сначала зарегистрируйтесь. Нажмите /start.",
        "en": "Please register first. Press /start.",
    },
    "reminder": {
        "uz": "💧 Salom, {name}! Suvingiz tugayabdimi?\n\n🛒 «Yangi buyurtma» tugmasi orqali yangi buyurtma berishingiz mumkin.",
        "ru": "💧 Здравствуйте, {name}! Вода заканчивается?\n\n🛒 Через кнопку «Новый заказ» вы можете оформить заказ.",
        "en": "💧 Hello, {name}! Running low on water?\n\n🛒 You can place a new order using the «New order» button.",
    },
    "status_new": {"uz": "🆕 Yangi", "ru": "🆕 Новый", "en": "🆕 New"},
    "status_process": {"uz": "🚚 Jarayonda", "ru": "🚚 В процессе", "en": "🚚 In progress"},
    "status_delivered": {"uz": "✅ Yetkazildi", "ru": "✅ Доставлен", "en": "✅ Delivered"},
    "status_canceled": {"uz": "🚫 Bekor", "ru": "🚫 Отменён", "en": "🚫 Canceled"},

    # ============================ KURYER BOTI ============================
    "c_welcome": {
        "uz": "🚚 Kuryer botiga xush kelibsiz!\n\nRo'yxatdan o'tish uchun avval tilni tanlang.",
        "ru": "🚚 Добро пожаловать в бот курьера!\n\nДля регистрации сначала выберите язык.",
        "en": "🚚 Welcome to the courier bot!\n\nTo register, first choose a language.",
    },
    "c_ask_name": {
        "uz": "👤 Ism va familiyangizni kiriting (masalan: Aliyev Vali):",
        "ru": "👤 Введите имя и фамилию (например: Алиев Вали):",
        "en": "👤 Enter your full name (e.g.: John Smith):",
    },
    "c_ask_region": {
        "uz": "🌍 Ishlaydigan hududingizni tanlang:",
        "ru": "🌍 Выберите регион, в котором работаете:",
        "en": "🌍 Choose the region you work in:",
    },
    "c_registered": {
        "uz": "✅ Tabriklaymiz, {name}! Ro'yxatdan o'tdingiz.\n\n📞 Telefon: {phone}\n🌍 Hudud: {region}\n\nEndi admin sizga buyurtma yo'naltirsa, xabar shu yerga keladi. 🚚",
        "ru": "✅ Поздравляем, {name}! Регистрация завершена.\n\n📞 Телефон: {phone}\n🌍 Регион: {region}\n\nТеперь, когда админ направит вам заказ, уведомление придёт сюда. 🚚",
        "en": "✅ Congratulations, {name}! Registration complete.\n\n📞 Phone: {phone}\n🌍 Region: {region}\n\nNow when an admin assigns you an order, the notification will arrive here. 🚚",
    },
    "c_greet": {
        "uz": "🚚 Salom, {name}!\nKuryer boti faol. Yangi buyurtmalar shu yerda ko'rinadi.",
        "ru": "🚚 Здравствуйте, {name}!\nБот курьера активен. Новые заказы появятся здесь.",
        "en": "🚚 Hello, {name}!\nThe courier bot is active. New orders will appear here.",
    },
    # --- Buyurtma xabari (caption) ---
    "c_new_order": {"uz": "🚚 <b>Yangi buyurtma</b>", "ru": "🚚 <b>Новый заказ</b>", "en": "🚚 <b>New order</b>"},
    "c_lbl_order": {"uz": "📦 Buyurtma", "ru": "📦 Заказ", "en": "📦 Order"},
    "c_lbl_client": {"uz": "👤 Mijoz", "ru": "👤 Клиент", "en": "👤 Client"},
    "c_lbl_phone": {"uz": "📞 Tel", "ru": "📞 Тел", "en": "📞 Phone"},
    "c_lbl_extra": {"uz": "📞 Qo'shimcha", "ru": "📞 Доп.", "en": "📞 Extra"},
    "c_lbl_region": {"uz": "🌍 Hudud", "ru": "🌍 Регион", "en": "🌍 Region"},
    "c_lbl_address": {"uz": "📍 Manzil", "ru": "📍 Адрес", "en": "📍 Address"},
    "c_lbl_house": {"uz": "🏠 Uy", "ru": "🏠 Дом", "en": "🏠 Apt"},
    "c_lbl_water": {"uz": "💧 Suv", "ru": "💧 Вода", "en": "💧 Water"},
    "c_lbl_sum": {"uz": "💰 Summa", "ru": "💰 Сумма", "en": "💰 Total"},
    "c_lbl_maps": {"uz": "🗺 Xaritada", "ru": "🗺 На карте", "en": "🗺 On map"},
    "c_btn_process": {"uz": "🚚 Jarayonda", "ru": "🚚 В процессе", "en": "🚚 In progress"},
    "c_btn_delivered": {"uz": "✅ Yetkazildi", "ru": "✅ Доставлено", "en": "✅ Delivered"},
    # --- Buyurtmani bajarish ---
    "c_taken": {
        "uz": "Buyurtma jarayonga olindi ✅",
        "ru": "Заказ взят в работу ✅",
        "en": "Order taken ✅",
    },
    "c_status_process": {
        "uz": "🚚 <b>Holat: Jarayonda</b>",
        "ru": "🚚 <b>Статус: В процессе</b>",
        "en": "🚚 <b>Status: In progress</b>",
    },
    "c_ask_delivered_count": {
        "uz": "✅ Yetkazildi.\n\n💧 Nechta suv yetkazdingiz? (masalan: {default})",
        "ru": "✅ Доставлено.\n\n💧 Сколько воды вы доставили? (например: {default})",
        "en": "✅ Delivered.\n\n💧 How many bottles did you deliver? (e.g.: {default})",
    },
    "c_ask_empty_returned": {
        "uz": "📦 Nechta bo'sh baklashka qaytarib oldingiz?",
        "ru": "📦 Сколько пустых баклажек вы забрали?",
        "en": "📦 How many empty bottles did you take back?",
    },
    "c_ask_empty_left": {
        "uz": "📦 Mijozda nechta bo'sh baklashka qoldi?",
        "ru": "📦 Сколько пустых баклажек осталось у клиента?",
        "en": "📦 How many empty bottles are left with the client?",
    },
    "c_num_invalid": {
        "uz": "Iltimos, son kiriting (masalan: 3)",
        "ru": "Пожалуйста, введите число (например: 3)",
        "en": "Please enter a number (e.g.: 3)",
    },
    "c_delivered_summary": {
        "uz": "✅ <b>Buyurtma yetkazildi!</b>\n\n📦 Buyurtma: #{id}\n💧 Yetkazilgan: {dc} ta\n📦 Qaytarilgan bo'sh: {er} ta\n📦 Mijozda qolgan: {el} ta\n\nRahmat! 🙌",
        "ru": "✅ <b>Заказ доставлен!</b>\n\n📦 Заказ: #{id}\n💧 Доставлено: {dc} шт.\n📦 Возвращено пустых: {er} шт.\n📦 Осталось у клиента: {el} шт.\n\nСпасибо! 🙌",
        "en": "✅ <b>Order delivered!</b>\n\n📦 Order: #{id}\n💧 Delivered: {dc}\n📦 Empty returned: {er}\n📦 Left with client: {el}\n\nThank you! 🙌",
    },
    "c_order_not_found": {
        "uz": "Buyurtma topilmadi.",
        "ru": "Заказ не найден.",
        "en": "Order not found.",
    },
}


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    entry = TEXTS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get(DEFAULT_LANG, key))


def status_text(status: str, lang: str = DEFAULT_LANG) -> str:
    return t(f"status_{status}", lang)
