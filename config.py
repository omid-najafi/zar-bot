import os

# ═══════════ بارگذاری فایل .env (برای VPS) ═══════════
# این فایل اگر وجود داشته باشد، متغیرهای محیطی رو از اون می‌خونه
# روی Railway متغیرها مستقیم تنظیم می‌شن و فایل .env وجود نداره
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv نصب نبود — از متغیرهای محیطی استفاده کن

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")

# ═══════════ تنظیمات دیتابیس ═══════════
# پشتیبانی از هر دو سبک نام‌گذاری:
#   - VPS:     DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
#   - Railway: MYSQLHOST, MYSQLPORT, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE
DB_HOST = os.getenv("DB_HOST") or os.getenv("MYSQLHOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT") or os.getenv("MYSQLPORT", "3306") or "3306")
DB_USER = os.getenv("DB_USER") or os.getenv("MYSQLUSER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("MYSQLPASSWORD", "")
DB_NAME = os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE", "zarbot")

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
    "id": -1004403374673,  # ← بعد از دیدن لاگ‌ها، آیدی عددی مثل -1001234567890 اینجا بذار
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
    "supermarket": {"name": "سوپرمارکت", "price": 500_000, "income": 175_000, "emoji": "🛒"},
    "fruit":       {"name": "میوه‌فروشی", "price": 800_000, "income": 280_000, "emoji": "🍎"},
    "butcher":     {"name": "قصابی", "price": 1_000_000, "income": 350_000, "emoji": "🥩"},
    "pharmacy":    {"name": "داروخانه", "price": 1_800_000, "income": 630_000, "emoji": "💊"},
    "barber":      {"name": "آرایشگاه", "price": 2_200_000, "income": 770_000, "emoji": "💈"},
    "clothing":    {"name": "فروشگاه پوشاک", "price": 3_000_000, "income": 1_050_000, "emoji": "👕"},
    "bookstore":   {"name": "کتاب‌فروشی", "price": 3_500_000, "income": 1_225_000, "emoji": "📚"},
    "mobile":      {"name": "موبایل‌فروشی", "price": 4_000_000, "income": 1_400_000, "emoji": "📱"},
    # ─── ۶ ملک جدید (هر کدوم ۸۵۰٬۰۰۰ افزایش) ───
    "electronics": {"name": "فروشگاه لوازم الکترونیکی", "price": 4_850_000, "income": 1_697_500, "emoji": "📺"},
    "jewelry":     {"name": "جواهرفروشی", "price": 5_700_000, "income": 1_995_000, "emoji": "💍"},
    "car_dealer":  {"name": "نمایشگاه ماشین", "price": 6_550_000, "income": 2_292_500, "emoji": "🚗"},
    "restaurant":  {"name": "رستوران", "price": 7_400_000, "income": 2_590_000, "emoji": "🍽️"},
    "hotel":       {"name": "هتل", "price": 8_250_000, "income": 2_887_500, "emoji": "🏨"},
    "mall":        {"name": "مجتمع تجاری", "price": 9_100_000, "income": 3_185_000, "emoji": "🏬"},
}

WORKERS = {
    "teacher":   {"name": "معلم", "price": 300_000, "income": 105_000, "emoji": "👨‍🏫"},
    "doctor":    {"name": "پزشک", "price": 500_000, "income": 175_000, "emoji": "👨‍⚕️"},
    "driver":    {"name": "راننده", "price": 800_000, "income": 280_000, "emoji": "🚕"},
    "developer": {"name": "برنامه‌نویس", "price": 1_200_000, "income": 420_000, "emoji": "👨‍💻"},
    "ai_expert": {"name": "متخصص هوش مصنوعی", "price": 2_000_000, "income": 700_000, "emoji": "🤖"},
    "pilot":     {"name": "خلبان", "price": 2_600_000, "income": 910_000, "emoji": "✈️"},
    "surgeon":   {"name": "جراح", "price": 3_000_000, "income": 1_050_000, "emoji": "🩺"},
    "ceo":       {"name": "مدیرعامل", "price": 3_500_000, "income": 1_225_000, "emoji": "💼"},
    # ─── ۴ کارگر جدید (هر کدوم ۶۰۰٬۰۰۰ افزایش) ───
    "chef":       {"name": "سرپرست آشپزخانه", "price": 4_100_000, "income": 1_435_000, "emoji": "👨‍🍳"},
    "architect":  {"name": "معمار", "price": 4_700_000, "income": 1_645_000, "emoji": "📐"},
    "scientist":  {"name": "دانشمند", "price": 5_300_000, "income": 1_855_000, "emoji": "🔬"},
    "astronaut":  {"name": "فضانورد", "price": 5_900_000, "income": 2_065_000, "emoji": "🚀"},
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

# ═══════════ شرط ورود به کاباره ═══════════
KABAREH_MIN_LEVEL = 4  # کاربر باید حداقل لول ۴ باشه تا بتونه وارد کاباره بشه

# ═══════════ شرط لول برای لانچرهای پیشرفته ═══════════
# این ۴ لانچر نیاز به لول ۲۰ دارند
LAUNCHER_MIN_LEVEL = 20
LAUNCHER_LEVEL_LOCKED = {"missile_launcher", "b2_bomber", "mc130_transport", "drone_launcher", "f35_fighter"}

# ═══════════ بازار سیاه ═══════════
# آیتم‌های بازار سیاه با ایموجی‌های اختصاصی
# type: "launcher" (وسیله شلیک) | "projectile" (مهمات) | "defense" (دفاعی)
BLACKMARKET_ITEMS = {
    # ─── وسایل شلیک (launcher) ───
    "missile_launcher": {
        "name": "لانچر موشک", "emoji": "🚀", "price": 40_000_000,
        "type": "launcher", "launches": ["cruise_missile", "ballistic_missile", "hypersonic_missile"]
    },
    "b2_bomber": {
        "name": "بمب افکن B-2", "emoji": "✈️", "price": 50_000_000,
        "type": "launcher", "launches": ["nuclear_bomb"]
    },
    "mc130_transport": {
        "name": "هواپیمای ترابری MC-130", "emoji": "🛩️", "price": 60_000_000,
        "type": "launcher", "launches": ["gbu43_bomb"]
    },
    "f35_fighter": {
        "name": "هواپیمای F-35", "emoji": "✈️", "price": 30_000_000,
        "type": "launcher", "launches": ["gbu12_bomb"]
    },
    "drone_launcher": {
        "name": "لانچر پهباد", "emoji": "🛸", "price": 12_000_000,
        "type": "launcher", "launches": ["shahed131_drone", "mq9_drone"]
    },
    # ─── مهمات (projectile) ───
    "cruise_missile": {
        "name": "موشک کروز", "emoji": "🚀", "price": 20_000_000,
        "type": "projectile", "damage": 0.20, "command": "شلیک موشک کروز",
        "defense_type": "missile_defense"
    },
    "ballistic_missile": {
        "name": "موشک بالستیک", "emoji": "🚀", "price": 30_000_000,
        "type": "projectile", "damage": 0.30, "command": "شلیک موشک بالستیک",
        "defense_type": "missile_defense"
    },
    "hypersonic_missile": {
        "name": "موشک هایپرسونیک", "emoji": "🚀", "price": 40_000_000,
        "type": "projectile", "damage": 0.40, "command": "شلیک موشک هایپرسونیک",
        "defense_type": "missile_defense"
    },
    "gbu43_bomb": {
        "name": "بمب GBU-43/B", "emoji": "💣", "price": 35_000_000,
        "type": "projectile", "damage": 0.50, "command": "مادر همه بمب ها",
        "defense_type": None  # بمب‌ها قابل دفاع نیستن
    },
    "nuclear_bomb": {
        "name": "بمب هسته ای B61-12", "emoji": "☢️", "price": 50_000_000,
        "type": "projectile", "damage": 0.60, "command": "بمب هسته ای",
        "defense_type": None
    },
    "gbu12_bomb": {
        "name": "بمب GBU-12", "emoji": "💣", "price": 15_000_000,
        "type": "projectile", "damage": 0.15, "command": "کمی بکنش",
        "defense_type": None
    },
    "shahed131_drone": {
        "name": "پهباد شاهد-131", "emoji": "🛸", "price": 8_000_000,
        "type": "projectile", "damage": 0.10, "command": "پهباد شاهد",
        "defense_type": "drone_defense"
    },
    "mq9_drone": {
        "name": "پهباد MQ-9", "emoji": "🛸", "price": 10_000_000,
        "type": "projectile", "damage": 0.15, "command": "شلیک پهباد MQ",
        "defense_type": "drone_defense"
    },
    # ─── سیستم‌های دفاعی (defense) ───
    "missile_defense": {
        "name": "پدافند موشکی", "emoji": "🛡️", "price": 40_000_000,
        "type": "defense", "defense_chance": 0.35, "defends_against": "missile_defense"
    },
    "drone_defense": {
        "name": "سامانه ضدپهباد", "emoji": "🛡️", "price": 45_000_000,
        "type": "defense", "defense_chance": 0.35, "defends_against": "drone_defense"
    },
}

# تعداد آیتم در هر صفحه بازار سیاه
BLACKMARKET_PER_PAGE = 6

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
    "🎭 <b>کاباره</b>: نیاز به لول ۴+ | باز کردن با ۲۵M | روزی یکبار\n"
    "🏦 <b>بانک</b>: سود روزانه ۲٪ (هر ساعت واریز می‌شود)\n"
    "🏠 <b>ملک‌ها</b>: حداکثر ۵ از هر نوع (سود ۳۵٪)\n"
    "👷 <b>کارگرها</b>: حداکثر ۵ از هر نوع (سود ۳۵٪)\n"
    "💸 <b>برداشت درآمد</b>: در بخش ملک/کارگر، درآمد انباشته‌شده رو دستی برداشت کن\n"
    "🎮 <b>بازی‌ها</b>: حداقل ۱٬۰۰۰ | کارمزد ۱۰٪ (سنگ کاغذ قیچی، دوز، کوییز، پنالتی)\n"
    "🎰 <b>کازینو</b>: حداقل ۱۰٬۰۰۰\n"
    "    بازی‌ها: اسلات، تاس، شیر یا خط، کارت، رولت، مین‌یاب، چرخ شانس\n"
    "💸 <b>انتقال</b>: بالای ۱M کارمزد ۱٪\n"
    "🔒 <b>منو</b>: هر کاربر فقط می‌تونه از منوی خودش استفاده کنه\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🏆 <b>لیدربورد</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "    رتبه‌بندی کاربران بر اساس ثروت (موجودی + بانک)\n"
    "    رتبه خودت + زرکوین‌هات رو ببین\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💀 <b>بازار سیاه</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "    خرید سلاح‌های نظامی برای حمله به کاربران دیگر\n"
    "\n"
    "📋 <b>دسته‌بندی آیتم‌ها:</b>\n"
    "    🚀 <b>وسایل شلیک</b> (الزامی برای شلیک):\n"
    "       • لانچر موشک (۴۰M) — برای شلیک موشک‌ها\n"
    "       • بمب افکن B-2 (۵۰M) — برای بمب هسته‌ای\n"
    "       • هواپیمای MC-130 (۶۰M) — برای بمب GBU-43\n"
    "       • هواپیمای F-35 (۳۰M) — برای بمب GBU-12\n"
    "       • لانچر پهباد (۱۲M) — برای شلیک پهبادها\n"
    "\n"
    "    🚀 <b>مهمات</b> (مصرفی):\n"
    "       • موشک کروز (۲۰M) — ۲۰٪ تخریب\n"
    "       • موشک بالستیک (۳۰M) — ۳۰٪ تخریب\n"
    "       • موشک هایپرسونیک (۴۰M) — ۴۰٪ تخریب\n"
    "       • بمب GBU-43/B (۳۵M) — ۵۰٪ تخریب\n"
    "       • بمب هسته‌ای B61-12 (۵۰M) — ۶۰٪ تخریب\n"
    "       • بمب GBU-12 (۱۵M) — ۱۵٪ تخریب\n"
    "       • پهباد شاهد-131 (۸M) — ۱۰٪ تخریب\n"
    "       • پهباد MQ-9 (۱۰M) — ۱۵٪ تخریب\n"
    "\n"
    "    🛡️ <b>دفاعی</b>:\n"
    "       • پدافند موشکی (۴۰M) — ۳۵٪ احتمال دفاع در برابر موشک\n"
    "       • سامانه ضدپهباد (۴۵M) — ۳۵٪ احتمال دفاع در برابر پهباد\n"
    "\n"
    "🎯 <b>نحوه شلیک:</b>\n"
    "    1. آیتم مورد نظر رو از بازار سیاه بخر\n"
    "    2. روی پیام فرد هدف ریپلای کن\n"
    "    3. دستور شلیک رو بفرست:\n"
    "       • شلیک موشک کروز\n"
    "       • شلیک موشک بالستیک\n"
    "       • شلیک موشک هایپرسونیک\n"
    "       • مادر همه بمب ها\n"
    "       • بمب هسته ای\n"
    "       • کمی بکنش\n"
    "       • پهباد شاهد\n"
    "       • شلیک پهباد MQ\n"
    "\n"
    "⚠️ <b>نکات مهم:</b>\n"
    "    • بدون وسیله شلیک، نمی‌تونی مهمات رو شلیک کنی\n"
    "    • بمب‌ها قابل دفاع نیستن، فقط موشک و پهباد\n"
    "    • هر شلیک یک مهمات رو مصرف می‌کنه\n"
    "    • درصد تخریب از کل اموال هدف (موجودی + بانک) کم می‌شه"
)
