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

# ═══════════ کاباره زر ═══════════
KABAREH_UNLOCK_COST = 25_000_000
KABAREH_COOLDOWN_HOURS = 24
KABAREH_GIRLS = {
    "fox":    {"name": "خانم روباه",   "emoji": "🦊", "price": 2_000_000},
    "angela": {"name": "خانم آنجلا",   "emoji": "👱‍♀️", "price": 3_000_000},
    "lana":   {"name": "خانم لانا",    "emoji": "👩", "price": 4_000_000},
    "alexis": {"name": "خانم الکسیس",  "emoji": "👩‍🦰", "price": 5_000_000},
    "eden":   {"name": "خانم اِدِن",   "emoji": "👸", "price": 6_000_000},
}
KABAREH_BABY_COST = 1_000_000
KABAREH_BABY_XP = 2000

# ═══════════ جوین اجباری ═══════════
REQUIRED_CHANNELS = [
    {"name": "کانال ربات زر", "id": "@zarbotchanel", "url": "https://t.me/zarbotchanel"},
    {"name": "کانال زر ۲", "id": "@zarchanel2", "url": "https://t.me/zarchanel2"},
]

REQUIRED_GROUP = {
    "name": "گروه پشتیبانی زر",
    "id": None,  # ← بعد از دیدن لاگ‌ها، آیدی عددی مثل -1001234567890 اینجا بذار
    "url": "https://t.me/+PZ6RRCYv5TtjMjRk",
}

# ═══════════ لول و ماموریت ═══════════
DAILY_MISSION_COUNT = 6
ZAR_COOLDOWN_SECONDS = 300

BASE_XP_PLAY_GAME = 15
BASE_XP_WIN_GAME = 30
BASE_XP_BUY_ASSET = 40
BASE_XP_DEPOSIT_10K = 10
BASE_XP_TRANSFER = 20
BASE_XP_ZAR = 10

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
    "play_games_10":  {"desc": "10 بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 10, "xp": 500},
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
    "📚 <b>راهنما</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "⭐ <b>لول</b>: هر لول نیاز به 2^level × 1000 XP\n"
    "🎯 <b>ماموریت‌ها</b>: هر روز 6 ماموریت جدید\n"
    "💰 <b>زر</b>: هر 5 دقیقه زرکوین رایگان بر اساس لول\n"
    "🎭 <b>کاباره</b>: با 25M بازش کن | روزی یکبار\n"
    "🏦 <b>بانک</b>: سود روزانه 2% ساعت 00:00\n"
    "🏠 <b>ملک‌ها</b>: حداکثر 5 از هر نوع (سود 25%)\n"
    "👷 <b>کارگرها</b>: حداکثر 5 از هر نوع (سود 25%)\n"
    "🎮 <b>بازی‌ها</b>: حداقل 1,000 | کارمزد 10%\n"
    "🎰 <b>کازینو</b>: حداقل 10,000\n"
    "💸 <b>انتقال</b>: بالای 1M کارمزد 1%"
)
