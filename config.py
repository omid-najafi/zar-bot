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

# ═══════════ سیستم لول و ماموریت ═══════════
DAILY_MISSION_COUNT = 6
ZAR_COOLDOWN_SECONDS = 300  # 5 دقیقه

# XP پایه برای کارهای روزانه
BASE_XP_PLAY_GAME = 15
BASE_XP_WIN_GAME = 30
BASE_XP_BUY_ASSET = 40
BASE_XP_DEPOSIT_10K = 10  # هر 10,000 واریز
BASE_XP_TRANSFER = 20
BASE_XP_ZAR = 10

# ═══════════ قالب‌های ماموریت ═══════════
# هر ماموریت کمتر از 500 XP دارد
MISSION_TEMPLATES = {
    "play_rps_1":     {"desc": "1 بازی سنگ کاغذ قیچی انجام بده", "type": "play_rps", "target": 1, "xp": 100},
    "play_rps_3":     {"desc": "3 بازی سنگ کاغذ قیچی انجام بده", "type": "play_rps", "target": 3, "xp": 300},
    "win_rps_1":      {"desc": "1 بازی سنگ کاغذ قیچی ببر", "type": "win_rps", "target": 1, "xp": 200},
    "play_ttt_1":     {"desc": "1 بازی دوز انجام بده", "type": "play_ttt", "target": 1, "xp": 100},
    "play_ttt_3":     {"desc": "3 بازی دوز انجام بده", "type": "play_ttt", "target": 3, "xp": 300},
    "win_ttt_1":      {"desc": "1 بازی دوز ببر", "type": "win_ttt", "target": 1, "xp": 250},
    "play_quiz_1":    {"desc": "1 کوییز بازی کن", "type": "play_quiz", "target": 1, "xp": 100},
    "win_quiz_1":     {"desc": "1 کوییز ببر", "type": "win_quiz", "target": 1, "xp": 300},
    "play_penalty_1": {"desc": "1 پنالتی بزن", "type": "play_penalty", "target": 1, "xp": 100},
    "win_penalty_1":  {"desc": "1 پنالتی گل کن", "type": "win_penalty", "target": 1, "xp": 200},
    "play_casino_1":  {"desc": "1 بازی کازینو انجام بده", "type": "play_casino", "target": 1, "xp": 100},
    "play_casino_3":  {"desc": "3 بازی کازینو انجام بده", "type": "play_casino", "target": 3, "xp": 300},
    "play_casino_5":  {"desc": "5 بازی کازینو انجام بده", "type": "play_casino", "target": 5, "xp": 450},
    "buy_property_1": {"desc": "1 ملک بخر", "type": "buy_property", "target": 1, "xp": 250},
    "buy_worker_1":   {"desc": "1 کارگر استخدام کن", "type": "buy_worker", "target": 1, "xp": 250},
    "deposit_100k":   {"desc": "100,000 زرکوین به بانک واریز کن", "type": "deposit_bank", "target": 100000, "xp": 150},
    "deposit_500k":   {"desc": "500,000 زرکوین به بانک واریز کن", "type": "deposit_bank", "target": 500000, "xp": 400},
    "transfer_1":     {"desc": "1 انتقال زرکوین انجام بده", "type": "transfer", "target": 1, "xp": 200},
    "zar_collect_3":  {"desc": "3 بار کلمه زر رو بفرست", "type": "zar_collect", "target": 3, "xp": 250},
    "zar_collect_5":  {"desc": "5 بار کلمه زر رو بفرست", "type": "zar_collect", "target": 5, "xp": 400},
    "play_games_5":   {"desc": "5 بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 5, "xp": 400},
    "play_games_10":  {"desc": "10 بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 10, "xp": 500 if False else 450},
}

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
    "⭐ <b>لول و XP</b>\n"
    "با انجام ماموریت‌ها و بازی‌ها XP می‌گیری و لولت بالا میره.\n"
    "برای لول بعدی به <code>2^level × 1000</code> XP نیاز داری.\n\n"
    "🎯 <b>ماموریت‌های روزانه</b>\n"
    "هر روز 6 ماموریت رندوم برات انتخاب می‌شه.\n"
    "هر ماموریت زیر 500 XP جایزه داره.\n\n"
    "🌾 <b>دستور زر</b>\n"
    "کلمه <code>زر</code> رو بفرست تا زرکوین رایگان بگیری.\n"
    "هر 5 دقیقه یک بار.\n"
    "مقدار جایزه بر اساس لولت:\n"
    "لول 1: 100-200 | لول 2: 200-300 | لول 3: 300-400 و...\n\n"
    "🎯 <b>دستورات</b>\n"
    "• <code>زربات</code> — منوی اصلی\n"
    "• <code>زر بازی</code> — بازی‌ها\n"
    "• <code>زر</code> — دریافت زرکوین رایگان\n"
    "• <code>/start</code> یا <code>/menu</code> — منوی اصلی\n\n"
    "🏦 <b>بانک</b>\n"
    "سود روزانه 2% که هر شب ساعت 00:00 واریز میشه.\n\n"
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
