# 💧 Langar Water Bot

Suv yetkazib berish xizmati uchun **to'liq tizim**:

- 🤖 **Mijoz boti** — buyurtma qabul qiladi (3 til: o'zbek / rus / ingliz)
- 🚚 **Kuryer boti** — kuryerlarga buyurtma yuboradi
- 🌐 **Web admin panel** — nazorat, statistika, hisob-kitob

> Zamonaviy texnologiyalarda yozilgan: **aiogram 3**, **FastAPI**, **SQLAlchemy 2.0**.

---

## 📑 Mundarija
1. [Tezkor ishga tushirish (eng oson)](#-1-tezkor-ishga-tushirish-eng-oson)
2. [Parollar va kirish ma'lumotlari](#-2-parollar-va-kirish-malumotlari)
3. [Birinchi marta o'rnatish (qo'lda)](#-3-birinchi-marta-ornatish-qolda)
4. [Ishga tushirish usullari](#-4-ishga-tushirish-usullari)
5. [To'xtatish](#-5-toxtatish)
6. [Qanday foydalaniladi](#-6-qanday-foydalaniladi)
7. [Sozlamalar (narx, hudud, bonus)](#-7-sozlamalar-narx-hudud-bonus)
8. [PostgreSQL'ga o'tish](#-8-postgresqlga-otish)
9. [Tez-tez uchraydigan muammolar](#-9-tez-tez-uchraydigan-muammolar)

---

## 🚀 1. Tezkor ishga tushirish (eng oson)

Windows Explorer'da loyiha papkasini oching va **`start.bat`** faylini **ikki marta bosing**.

```
D:\Code\langar_water_bot\start.bat   ←  ikki marta bosing
```

Bu fayl avtomatik:
- virtual muhitni tekshiradi (yo'q bo'lsa — yaratadi va kutubxonalarni o'rnatadi);
- `.env` faylini tayyorlaydi;
- **mijoz boti + kuryer boti + admin panel + eslatmalar** — hammasini birga ishga tushiradi.

Ochilgan oynada quyidagicha ko'rinadi:
```
============================================
  LANGAR WATER BOT
  Admin panel: http://localhost:8000
  Toxtatish uchun: Ctrl + C
============================================
... Run polling for bot @langar_water_bot
... Run polling for bot @langar_curier_bot
... Uvicorn running on http://0.0.0.0:8000
```

✅ Tayyor. Admin panelni brauzerда oching: **http://localhost:8000**

> 💡 **Maslahat:** `start.bat` ni ish stoliga **yorliq (shortcut)** qilib chiqaring — bir bosishда ishga tushadi.

---

## 🔐 2. Parollar va kirish ma'lumotlari

### Admin panelга kirish
| | Qiymat |
|---|---|
| Manzil | **http://localhost:8000** |
| Login | **admin** |
| Parol | **admin123** |

> ⚠️ Parolni o'zgartirish uchun `.env` faylini oching va o'zgartiring:
> ```
> ADMIN_LOGIN=admin
> ADMIN_PASSWORD=admin123
> ```
> O'zgartirgandan keyin tizimni qayta ishga tushiring.
>
> **Eslatma:** parolni o'zgartirsangiz, eski admin bazada qoladi. Yangi parol faqat
> bo'sh bazada (yoki yangi login bilan) avtomatik yaratiladi. Mavjud admin parolini
> almashtirmoqchi bo'lsangiz, `langar.db` faylini o'chirib qayta ishga tushiring
> (diqqat: bu barcha ma'lumotni o'chiradi) yoki yangi `ADMIN_LOGIN` qo'ying.

### Telegram botlar
| Bot | Username |
|---|---|
| Mijoz boti | **@langar_water_bot** |
| Kuryer boti | **@langar_curier_bot** |

Tokenlar `.env` faylida saqlanadi (`CLIENT_BOT_TOKEN`, `COURIER_BOT_TOKEN`).

> 🔒 **Xavfsizlik:** tokenlar oshkor bo'lgan bo'lsa, [@BotFather](https://t.me/BotFather)
> da `/revoke` orqali yangilab oling va `.env` ga yangisini qo'ying.

---

## 🛠 3. Birinchi marta o'rnatish (qo'lda)

`start.bat` buni avtomatik bajaradi. Lekin qo'lda qilmoqchi bo'lsangiz:

```powershell
# 1. Loyiha papkasiga o'tish
cd D:\Code\langar_water_bot

# 2. Virtual muhit yaratish
python -m venv .venv

# 3. Faollashtirish
.\.venv\Scripts\Activate.ps1
#   Agar xato bo'lsa (scripts disabled), bir marta:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 4. Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 5. Sozlamalar faylini yaratish
copy .env.example .env
#   -> .env ichida tokenlar va admin parolini sozlang
```

**Talab:** Python 3.11+ (3.14 da sinaб ko'rilgan).

---

## ▶️ 4. Ishga tushirish usullari

### A) Hammasi birga — `start.bat` (tavsiya)
Ikki marta bosing yoki terminalда:
```powershell
.\start.bat
```

### B) Hammasi birga — Python orqali
```powershell
cd D:\Code\langar_water_bot
.\.venv\Scripts\python.exe run_all.py
```

### C) Alohida-alohida (ishlab chiqish uchun)
Har birini **alohida terminal oynasida** ishga tushiring:
```powershell
.\.venv\Scripts\python.exe -m app.client_bot.main     # mijoz boti
.\.venv\Scripts\python.exe -m app.courier_bot.main    # kuryer boti
.\.venv\Scripts\python.exe -m app.admin.main          # admin panel
.\.venv\Scripts\python.exe -m app.reminders           # eslatmalar
```

> Birinchi ishga tushganda `langar.db` bazasi avtomatik yaratiladi va admin qo'shiladi.

---

## ⏹ 5. To'xtatish

Ishlab turgan oynada **`Ctrl + C`** bosing.

`start.bat` orqali ochilgan oynada to'xtatish uchun ham `Ctrl + C`, keyin oynani yoping.

---

## 📖 6. Qanday foydalaniladi

### 👤 Mijoz
1. Telegramда [@langar_water_bot](https://t.me/langar_water_bot) ga `/start` yuboradi.
2. **START** → **til** tanlaydi (uz / ru / en).
3. Ro'yxatdan o'tadi: **F.I.Sh** → **telefon** (share contact) → **qo'shimcha raqam** (ixtiyoriy) → **lokatsiya** (share location — manzil avtomatik o'qiladi) → **uy** (masalan: 3-podyezd, 23-xonadon) → **hudud** → **tasdiqlash**.
4. Asosiy menyu:
   - 🆔 **ID raqam** — mijozning telefon raqami uning ID si
   - 📜 **Buyurtmalar tarixi** — sana, miqdor, summa, holat
   - 📦 **Bo'sh baklashkalar** — qancha bo'sh idish borligi
   - 🎁 **Bonuslar** — har 100 ta suvga bonus
   - 🛒 **Yangi buyurtma** — hudud → miqdor (2-5) → narx hisobi → tasdiq

### 🧑‍💼 Admin
1. **http://localhost:8000** → `admin` / `admin123`.
2. **📊 Dashboard** — jami/yangi/jarayonda/yetkazilgan buyurtmalar, tushum, suv soni, diagrammalar. **Har 5 soniyada avto-yangilanadi.**
3. **📦 Buyurtmalar** — yangi buyurtmaga kuryer tanlab **«Yuborish»** bosadi → kuryerga bot orqali avtomatik xabar boradi.
4. **🚚 Kuryerlar** — kuryer qo'shish/o'chirish (ism, telefon, hudud, Telegram ID).
5. **💵 Kuryer hisobi** — kunlik/haftalik/oylik/jami: yetkazgan suv, kuryer haqi, bonus, adminga topshiradigan summa.
6. **👥 Mijozlar & Bonus** — faol mijozlar reytingi va bonus eslatmalari (promokod berish kerak bo'lganlar).

### 🚚 Kuryer
1. [@langar_curier_bot](https://t.me/langar_curier_bot) ga `/start` yuboradi → **Telegram ID** chiqadi.
2. Bu ID ni admin **«Kuryerlar»** bo'limiga qo'shadi.
3. Endi buyurtmalar shu botga keladi. Har birida **«🚚 Jarayonda»** va **«✅ Yetkazildi»** tugmalari.
4. **Yetkazildi** bosilganда kiritadi: nechta suv yetkazildi, nechta bo'sh baklashka qaytarib olindi, mijozda nechta qoldi.

---

## ⚙️ 7. Sozlamalar (narx, hudud, bonus)

### Hududlar va narxlar — `app/config.py`
```python
REGIONS = [
    Region("toshkent", "Toshkent", price=22000, courier_rate=3000),
    Region("samarqand_ishtixon", "Samarqand (Ishtixon va Kattaqo'rg'on)", price=18000, courier_rate=2500),
    Region("navoi_xatirchi", "Navoi (Xatirchi)", price=19000, courier_rate=2500),
    Region("navoi_mirbozor", "Navoi (Mirbozor Narpay)", price=19000, courier_rate=2500),
]
```
- `price` — 1 dona suv narxi (so'm)
- `courier_rate` — kuryerга 1 dona yetkazgani uchun (so'm)

### Bonus chegaralari — `app/config.py`
```python
CLIENT_BONUS_STEP = 100          # mijoz har 100 ta suvда bonus
COURIER_DAILY_BONUS_STEP = 120   # kuryer kuniга 120 ta yetkazsa
COURIER_DAILY_BONUS_AMOUNT = 60000   # qo'shimcha bonus (so'm)
```

### Eslatma kunlari — `.env`
```
REMINDER_DAYS=10,15,20,30
```
Mijoz shu kunlar davomida buyurtma bermasa, unга «suvingiz tugayabdimi?» xabari yuboriladi (kunлик 10:00 da tekshiriladi).

### Manzilni avtomatik o'qish — `.env`
```
GOOGLE_MAPS_API_KEY=
```
Bo'sh qoldirsangiz — bepul **OpenStreetMap** ishlatiladi (kalit shart emas).
Google Maps kaliti qo'ysangiz — aniqroq manzil chiqadi.

---

## 🐘 8. PostgreSQL'ga o'tish

Kod allaqachon tayyor. Ikki qadam:

1. `requirements.txt` da `asyncpg` qatorini oching va o'rnating:
   ```
   asyncpg>=0.30.0
   ```
   ```powershell
   pip install -r requirements.txt
   ```
2. `.env` da bazaning manzilini o'zgartiring:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/langar
   ```

Modellar va so'rovlar **o'zgartirishsiz** ishlaydi. Tayyor.

---

## 🧯 9. Tez-tez uchraydigan muammolar

| Muammo | Yechim |
|---|---|
| `Activate.ps1 ... scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` ni bir marta bajaring |
| `python is not recognized` | Python o'rnatilmagan yoki PATH da yo'q. [python.org](https://python.org) dan o'rnating va «Add to PATH» belgilang |
| Admin panel ochilmayapti | Tizim ishlayotganini tekshiring; manzil aynan **http://localhost:8000** |
| Bot javob bermayapti | Token to'g'riligini (`.env`) va internetni tekshiring; bot bitta nusxada ishlashi kerak (ikkita joyda bir vaqtда emas) |
| Kuryerga xabar bormayapti | Kuryerning **Telegram ID** si admin panelда to'g'ri kiritilganini va kuryer botга `/start` bosganini tekshiring |
| Hammasini noldan boshlamoqchiman | Tizimni to'xtating va `langar.db` faylini o'chiring (⚠️ barcha ma'lumot o'chadi), keyin qayta ishga tushiring |

---

## 📂 Loyiha tuzilishi

```
langar_water_bot/
├─ start.bat             # ⭐ ikki marta bosib ishga tushirish
├─ run_all.py            # hammasini bitta buyruq bilan
├─ requirements.txt      # kutubxonalar ro'yxati
├─ .env                  # sozlamalar (tokenlar, parol) — maxfiy
├─ .env.example          # namuna sozlamalar
└─ app/
   ├─ config.py          # hududlar, narxlar, bonuslar
   ├─ i18n.py            # 3 til matnlari
   ├─ geocode.py         # lokatsiyadan manzil
   ├─ security.py        # parol heshlash
   ├─ reminders.py       # avtomatik eslatmalar
   ├─ db/                # modellar + biznes-mantiq
   ├─ client_bot/        # mijoz boti
   ├─ courier_bot/       # kuryer boti
   └─ admin/             # admin panel (FastAPI + sahifalar)
```

---

💧 **Langar Water Bot** — suv yetkazib berishni avtomatlashtirish tizimi.
