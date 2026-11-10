import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")

DB_HOST = os.getenv("MYSQLHOST", "localhost")
DB_PORT = int(os.getenv("MYSQLPORT", "3306") or "3306")
DB_USER = os.getenv("MYSQLUSER", "root")
DB_PASSWORD = os.getenv("MYSQLPASSWORD", "")
DB_NAME = os.getenv("MYSQLDATABASE", "railway")

BANK_RATE = 0.02  # سود روزانه ۲٪
MAX_PER_KEY = 5
TRANSFER_FEE_RATE = 0.01
TRANSFER_FEE_MIN = 1_000_000
COMMISSION_RATE = 0.10

# ═══════════ پرداخت درآمد ═══════════
# پرداخت خودکار هر ۱ ساعت
HOURLY_PAYOUT_INTERVAL = 3600  # ثانیه
# حداکثر زمان انباشته‌شده در پرداخت خودکار (ثانیه) - برای جلوگیری از پرداخت زیاد هنگام ری‌استارت
HOURLY_PAYOUT_MAX_CATCHUP = 86400  # نهایتاً ۱ روز

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
BASE_XP_KABAREH = 20
BASE_XP_WITHDRAW_INCOME = 15

# ═══════════ قالب‌های ماموریت ═══════════
# نوع ماموریت‌ها برای فیلتر هوشمند:
#   buy_property → اگر کاربر تمام ملک‌ها را خریده، فیلتر می‌شود
#   buy_worker   → اگر کاربر تمام کارگرها را خریده، فیلتر می‌شود
#   kabareh      → اگر کاربر کاباره را باز نکرده، فیلتر می‌شود
MISSION_TEMPLATES = {
    # ─── سنگ کاغذ قیچی ───
    "play_rps_1":     {"desc": "۱ بازی سنگ کاغذ قیچی انجام بده", "type": "play_rps", "target": 1, "xp": 100},
    "play_rps_3":     {"desc": "۳ بازی سنگ کاغذ قیچی انجام بده", "type": "play_rps", "target": 3, "xp": 300},
    "play_rps_5":     {"desc": "۵ بازی سنگ کاغذ قیچی انجام بده", "type": "play_rps", "target": 5, "xp": 450},
    "win_rps_1":      {"desc": "۱ بازی سنگ کاغذ قیچی ببر", "type": "win_rps", "target": 1, "xp": 200},
    "win_rps_3":      {"desc": "۳ بازی سنگ کاغذ قیچی ببر", "type": "win_rps", "target": 3, "xp": 500},
    # ─── دوز ───
    "play_ttt_1":     {"desc": "۱ بازی دوز انجام بده", "type": "play_ttt", "target": 1, "xp": 100},
    "play_ttt_3":     {"desc": "۳ بازی دوز انجام بده", "type": "play_ttt", "target": 3, "xp": 300},
    "play_ttt_5":     {"desc": "۵ بازی دوز انجام بده", "type": "play_ttt", "target": 5, "xp": 450},
    "win_ttt_1":      {"desc": "۱ بازی دوز ببر", "type": "win_ttt", "target": 1, "xp": 250},
    "win_ttt_3":      {"desc": "۳ بازی دوز ببر", "type": "win_ttt", "target": 3, "xp": 600},
    # ─── کوییز ───
    "play_quiz_1":    {"desc": "۱ کوییز بازی کن", "type": "play_quiz", "target": 1, "xp": 100},
    "play_quiz_3":    {"desc": "۳ کوییز بازی کن", "type": "play_quiz", "target": 3, "xp": 300},
    "win_quiz_1":     {"desc": "۱ کوییز ببر", "type": "win_quiz", "target": 1, "xp": 300},
    "win_quiz_3":     {"desc": "۳ کوییز ببر", "type": "win_quiz", "target": 3, "xp": 700},
    # ─── پنالتی ───
    "play_penalty_1": {"desc": "۱ پنالتی بزن", "type": "play_penalty", "target": 1, "xp": 100},
    "play_penalty_3": {"desc": "۳ پنالتی بزن", "type": "play_penalty", "target": 3, "xp": 300},
    "win_penalty_1":  {"desc": "۱ پنالتی گل کن", "type": "win_penalty", "target": 1, "xp": 200},
    "win_penalty_3":  {"desc": "۳ پنالتی گل کن", "type": "win_penalty", "target": 3, "xp": 500},
    # ─── کازینو ───
    "play_casino_1":  {"desc": "۱ بازی کازینو انجام بده", "type": "play_casino", "target": 1, "xp": 100},
    "play_casino_3":  {"desc": "۳ بازی کازینو انجام بده", "type": "play_casino", "target": 3, "xp": 300},
    "play_casino_5":  {"desc": "۵ بازی کازینو انجام بده", "type": "play_casino", "target": 5, "xp": 450},
    "play_casino_10": {"desc": "۱۰ بازی کازینو انجام بده", "type": "play_casino", "target": 10, "xp": 600},
    "play_casino_15": {"desc": "۱۵ بازی کازینو انجام بده", "type": "play_casino", "target": 15, "xp": 800},
    "win_casino_3":   {"desc": "۳ بازی کازینو ببر", "type": "win_casino", "target": 3, "xp": 500},
    "win_casino_5":   {"desc": "۵ بازی کازینو ببر", "type": "win_casino", "target": 5, "xp": 800},
    # ─── بازی‌های عمومی ───
    "play_games_5":   {"desc": "۵ بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 5, "xp": 400},
    "play_games_10":  {"desc": "۱۰ بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 10, "xp": 500},
    "play_games_15":  {"desc": "۱۵ بازی (هر نوعی) انجام بده", "type": "play_any_game", "target": 15, "xp": 700},
    "win_games_3":    {"desc": "۳ بازی (هر نوعی) ببر", "type": "win_any_game", "target": 3, "xp": 500},
    "win_games_5":    {"desc": "۵ بازی (هر نوعی) ببر", "type": "win_any_game", "target": 5, "xp": 800},
    # ─── خرید دارایی ───
    "buy_property_1": {"desc": "۱ ملک بخر", "type": "buy_property", "target": 1, "xp": 250},
    "buy_property_3": {"desc": "۳ ملک بخر", "type": "buy_property", "target": 3, "xp": 500},
    "buy_worker_1":   {"desc": "۱ کارگر استخدام کن", "type": "buy_worker", "target": 1, "xp": 250},
    "buy_worker_3":   {"desc": "۳ کارگر استخدام کن", "type": "buy_worker", "target": 3, "xp": 500},
    # ─── بانک ───
    "deposit_100k":   {"desc": "۱۰۰٬۰۰۰ زرکوین به بانک واریز کن", "type": "deposit_bank", "target": 100000, "xp": 150},
    "deposit_500k":   {"desc": "۵۰۰٬۰۰۰ زرکوین به بانک واریز کن", "type": "deposit_bank", "target": 500000, "xp": 400},
    "deposit_1m":     {"desc": "۱٬۰۰۰٬۰۰۰ زرکوین به بانک واریز کن", "type": "deposit_bank", "target": 1000000, "xp": 600},
    # ─── انتقال ───
    "transfer_1":     {"desc": "۱ انتقال زرکوین انجام بده", "type": "transfer", "target": 1, "xp": 200},
    "transfer_3":     {"desc": "۳ انتقال زرکوین انجام بده", "type": "transfer", "target": 3, "xp": 400},
    # ─── زر ───
    "zar_collect_3":  {"desc": "۳ بار کلمه زر رو بفرست", "type": "zar_collect", "target": 3, "xp": 250},
    "zar_collect_5":  {"desc": "۵ بار کلمه زر رو بفرست", "type": "zar_collect", "target": 5, "xp": 400},
    "zar_collect_10": {"desc": "۱۰ بار کلمه زر رو بفرست", "type": "zar_collect", "target": 10, "xp": 600},
    # ─── کاباره ───
    "kabareh_1":      {"desc": "۱ بار به کاباره برو", "type": "kabareh", "target": 1, "xp": 300},
    # ─── برداشت درآمد ───
    "withdraw_income_1": {"desc": "۱ بار درآمد ملک/کارگر رو برداشت کن", "type": "withdraw_income", "target": 1, "xp": 200},
    "withdraw_income_3": {"desc": "۳ بار درآمد ملک/کارگر رو برداشت کن", "type": "withdraw_income", "target": 3, "xp": 400},
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
    # ─── ۶ ملک جدید (هر کدوم ۸۵۰٬۰۰۰ افزایش) ───
    "electronics": {"name": "فروشگاه لوازم الکترونیکی", "price": 4_850_000, "income": 1_212_500, "emoji": "📺"},
    "jewelry":     {"name": "جواهرفروشی", "price": 5_700_000, "income": 1_425_000, "emoji": "💍"},
    "car_dealer":  {"name": "نمایشگاه ماشین", "price": 6_550_000, "income": 1_637_500, "emoji": "🚗"},
    "restaurant":  {"name": "رستوران", "price": 7_400_000, "income": 1_850_000, "emoji": "🍽️"},
    "hotel":       {"name": "هتل", "price": 8_250_000, "income": 2_062_500, "emoji": "🏨"},
    "mall":        {"name": "مجتمع تجاری", "price": 9_100_000, "income": 2_275_000, "emoji": "🏬"},
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
    # ─── ۴ کارگر جدید (هر کدوم ۶۰۰٬۰۰۰ افزایش) ───
    "chef":       {"name": "سرپرست آشپزخانه", "price": 4_100_000, "income": 1_025_000, "emoji": "👨‍🍳"},
    "architect":  {"name": "معمار", "price": 4_700_000, "income": 1_175_000, "emoji": "📐"},
    "scientist":  {"name": "دانشمند", "price": 5_300_000, "income": 1_325_000, "emoji": "🔬"},
    "astronaut":  {"name": "فضانورد", "price": 5_900_000, "income": 1_475_000, "emoji": "🚀"},
}

GAMES = {
    "rps":     {"name": "سنگ کاغذ قیچی", "emoji": "✊", "min": 1000, "players": 2, "mult": 1.5},
    "ttt":     {"name": "دوز", "emoji": "❌", "min": 1000, "players": 2, "mult": 1.7},
    "quiz":    {"name": "کوییز", "emoji": "🧠", "min": 1000, "players": 2, "mult": 1.8},
    "penalty": {"name": "پنالتی", "emoji": "⚽", "min": 1000, "players": 1, "mult": 2.0},
}

CASINO_GAMES = {
    "slots":   {"name": "اسلات", "emoji": "🎰", "min": 10_000},
    "dice":    {"name": "تاس", "emoji": "🎲", "min": 10_000},
    "coin":    {"name": "شیر یا خط", "emoji": "🪙", "min": 10_000},
    "card":    {"name": "کارت شانس", "emoji": "🃏", "min": 10_000},
    "roulette": {"name": "رولت", "emoji": "🎡", "min": 10_000},
    "mines":   {"name": "مین‌یاب", "emoji": "💣", "min": 10_000},
    "wheel":   {"name": "چرخ شانس", "emoji": "🎯", "min": 10_000},
}

# رولت: قرمز (۱٬۳٬۵٬...,۳۵) | مشکی (۲٬۴٬۶٬...,۳۶) | صفر سبز
ROULETTE_RED = {1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35}
# مین‌یاب: ۵ در، ۳ جواهر، ۲ مین
MINES_GEMS = 3
MINES_TOTAL = 5
# چرخ شانس: ۶ قسمت
WHEEL_SEGMENTS = 6

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "7️⃣", "⭐"]
CARD_SUITS = {"hearts": "♥️", "diamonds": "♦️", "spades": "♠️", "clubs": "♣️"}
CARD_SUITS_FA = {"hearts": "دل", "diamonds": "خشت", "spades": "پیک", "clubs": "گشنیز"}

HELP_TEXT = (
    "📚 <b>راهنما</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "⭐ <b>لول</b>: هر لول نیاز به 2^level × 1000 XP\n"
    "🎯 <b>ماموریت‌ها</b>: هر روز ۶ ماموریت جدید\n"
    "💰 <b>زر</b>: هر ۵ دقیقه زرکوین رایگان بر اساس لول\n"
    "🎭 <b>کاباره</b>: با ۲۵M بازش کن | روزی یکبار\n"
    "🏦 <b>بانک</b>: سود روزانه ۲٪ (هر ساعت واریز می‌شود)\n"
    "🏠 <b>ملک‌ها</b>: حداکثر ۵ از هر نوع (سود ۲۵٪)\n"
    "👷 <b>کارگرها</b>: حداکثر ۵ از هر نوع (سود ۲۵٪)\n"
    "💸 <b>برداشت درآمد</b>: در بخش ملک/کارگر، درآمد انباشته‌شده رو دستی برداشت کن\n"
    "🎮 <b>بازی‌ها</b>: حداقل ۱٬۰۰۰ | کارمزد ۱۰٪ (سنگ کاغذ قیچی، دوز، کوییز، پنالتی)\n"
    "🎰 <b>کازینو</b>: حداقل ۱۰٬۰۰۰ (اسلات، تاس، شیر یا خط، کارت، رولت، مین‌یاب، چرخ شانس)\n"
    "💸 <b>انتقال</b>: بالای ۱M کارمزد ۱٪\n"
    "🔒 <b>منو</b>: هر کاربر فقط می‌تونه از منوی خودش استفاده کنه"
)
