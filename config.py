import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")

DB_HOST = os.getenv("MYSQLHOST", "localhost")
DB_PORT = int(os.getenv("MYSQLPORT", "3306") or "3306")
DB_USER = os.getenv("MYSQLUSER", "root")
DB_PASSWORD = os.getenv("MYSQLPASSWORD", "")
DB_NAME = os.getenv("MYSQLDATABASE", "railway")

BANK_RATE = 0.02
MAX_PER_KEY = 5
TRANSFER_FEE_RATE = 0.01
TRANSFER_FEE_MIN = 1_000_000
COMMISSION_RATE = 0.10

PROPERTIES = {
    "supermarket": {"name": "سوپرمارکت", "price": 500_000, "income": 125_000, "emoji": "🛒"},
    "fruit":       {"name": "میوه‌فروشی", "price": 800_000, "income": 200_000, "emoji": "🍎"},
    "butcher":     {"name": "قصابی", "price": 1_000_000, "income": 250_000, "emoji": "🥩"},
    "pharmacy":    {"name": "داروخانه", "price": 1_800_000, "income": 450_000, "emoji": "💊"},
    "barber":      {"name": "آرایشگاه", "price": 2_200_000, "income": 550_000, "emoji": "💈"},
    "clothing":    {"name": "فروشگاه پوشاک", "price": 3_000_000, "income": 750_000, "emoji": "👕"},
    "bookstore":   {"name": "کتاب‌فروشی", "price": 3_500_000, "income": 875_000, "emoji": "📚"},
    "mobile":      {"name": "موبایل‌فروشی", "price": 4_000_000, "income": 1_000_000, "emoji": "📱"},
}

WORKERS = {
    "teacher":   {"name": "معلم", "price": 300_000, "income": 75_000, "emoji": "👨‍🏫"},
    "doctor":    {"name": "پزشک", "price": 500_000, "income": 125_000, "emoji": "👨‍⚕️"},
    "driver":    {"name": "راننده", "price": 800_000, "income": 200_000, "emoji": "🚕"},
    "developer": {"name": "برنامه‌نویس", "price": 1_200_000, "income": 300_000, "emoji": "👨‍💻"},
    "ai_expert": {"name": "متخصص هوش مصنوعی", "price": 2_000_000, "income": 500_000, "emoji": "🤖"},
    "pilot":     {"name": "خلبان", "price": 2_600_000, "income": 650_000, "emoji": "✈️"},
    "surgeon":   {"name": "جراح", "price": 3_000_000, "income": 750_000, "emoji": "🩺"},
    "ceo":       {"name": "مدیرعامل", "price": 3_500_000, "income": 875_000, "emoji": "💼"},
}

GAMES = {
    "rps":     {"name": "سنگ کاغذ قیچی", "emoji": "✊", "min": 1000, "players": 2, "mult": 1.5},
    "ttt":     {"name": "دوز", "emoji": "❌", "min": 1000, "players": 2, "mult": 1.7},
    "quiz":    {"name": "کوییز", "emoji": "🧠", "min": 1000, "players": 2, "mult": 1.8},
    "penalty": {"name": "پنالتی", "emoji": "⚽", "min": 1000, "players": 1, "mult": 2.0},
}

CASINO_GAMES = {
    "slots": {"name": "اسلات", "emoji": "🎰", "min": 10_000},
    "dice":  {"name": "تاس", "emoji": "🎲", "min": 10_000},
    "coin":  {"name": "شیر یا خط", "emoji": "🪙", "min": 10_000},
    "card":  {"name": "کارت شانس", "emoji": "🃏", "min": 10_000},
}

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "7️⃣", "⭐"]
CARD_SUITS = {"hearts": "♥️", "diamonds": "♦️", "spades": "♠️", "clubs": "♣️"}
CARD_SUITS_FA = {"hearts": "دل", "diamonds": "خشت", "spades": "پیک", "clubs": "گشنیز"}

HELP_TEXT = (
    "📚 <b>راهنمای زرکوین بات</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🪙 <b>زرکوین چیه؟</b>\n"
    "واحد پول بازی، قابل کسب از طریق خرید ملک، استخدام کارگر، سود بانکی و برد در بازی‌ها.\n\n"
    "🎯 <b>دستورات</b>\n"
    "• <code>زربات</code> — باز کردن منوی اصلی\n"
    "• <code>زر بازی</code> — رفتن به بخش بازی‌ها\n"
    "• <code>/start</code> یا <code>/menu</code> — منوی اصلی\n\n"
    "🏦 <b>بانک</b>\n"
    "سود روزانه 2% که هر شب ساعت 00:00 واریز میشه.\n"
    "شماره کارت اختصاصی بر اساس آیدی عددی.\n\n"
    "🏠 <b>ملک‌ها</b> (حداکثر 5 عدد از هر نوع - سود 25%)\n"
    "🛒 500K→125K | 🍎 800K→200K | 🥩 1M→250K | 💊 1.8M→450K\n"
    "💈 2.2M→550K | 👕 3M→750K | 📚 3.5M→875K | 📱 4M→1M\n\n"
    "👷 <b>کارگرها</b> (حداکثر 5 عدد از هر نوع - سود 25%)\n"
    "👨‍🏫 300K→75K | 👨‍⚕️ 500K→125K | 🚕 800K→200K\n"
    "👨‍💻 1.2M→300K | 🤖 2M→500K | ✈️ 2.6M→650K\n"
    "🩺 3M→750K | 💼 3.5M→875K\n\n"
    "🎮 <b>بازی‌ها</b> (حداقل 1,000 زرکوین)\n"
    "✊ سنگ کاغذ قیچی (1.5x) | ❌ دوز (1.7x)\n"
    "🧠 کوییز (1.8x) | ⚽ پنالتی (2x)\n\n"
    "🎰 <b>کازینو</b> (حداقل 10,000 زرکوین)\n"
    "🎰 اسلات (تا 15x) | 🎲 تاس (دقیق 3x / زوج‌فرد 1.5x)\n"
    "🪙 شیر یا خط (2x) | 🃏 کارت شانس (4x)\n\n"
    "💵 <b>کارمزد بات</b>: 10% از هر برد\n"
    "💸 <b>انتقال</b>: با شماره کارت. بالای 1M، 1% کارمزد.\n\n"
    "👑 <b>اهدا از طرف مالک</b>\n"
    "مالک با ریپلای روی پیام کسی بنویسه:\n"
    "<code>انتقال زرکوین 5000</code>"
)
