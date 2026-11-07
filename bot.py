# -*- coding: utf-8 -*-
"""
ربات زرکوین (بات زر)
نسخه کامل برای دیپلوی روی Railway
"""

import asyncio
import html
import logging
import os
import random
import re
import secrets
import string
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import aiosqlite
from telegram import (
    ChatMember,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# ⚙️ تنظیمات
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")

TEHRAN = ZoneInfo("Asia/Tehran")

# Railway volume mount path
DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", os.path.join(os.getcwd(), "data"))
DB_PATH = os.path.join(DATA_DIR, "zarcoin.db")

if not BOT_TOKEN:
    raise RuntimeError("❌ متغیر محیطی BOT_TOKEN تنظیم نشده است.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ZarCoinBot")

# ============================================================
# 💰 ثابت‌ها
# ============================================================

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

BANK_INTEREST_RATE = 0.02          # ۲٪ روزانه
MAX_ASSETS_PER_TYPE = 5            # حداکثر ۵ ملک / ۵ کارگر
TRANSFER_FEE_RATE = 0.01           # ۱٪ کارمزد
TRANSFER_FEE_THRESHOLD = 1_000_000 # بالای ۱ میلیون

# -------------------- ملک‌ها (مرتب‌شده از ارزان به گران) --------------------
PROPERTIES = {
    "supermarket": {"name": "سوپرمارکت", "price": 500_000, "income": 50_000, "emoji": "🛒"},
    "fruit":       {"name": "میوه‌فروشی", "price": 800_000, "income": 80_000, "emoji": "🍎"},
    "butcher":     {"name": "قصابی", "price": 1_000_000, "income": 100_000, "emoji": "🥩"},
    "pharmacy":    {"name": "داروخانه", "price": 1_800_000, "income": 180_000, "emoji": "💊"},
    "barber":      {"name": "آرایشگاه", "price": 2_200_000, "income": 220_000, "emoji": "💈"},
    "clothing":    {"name": "فروشگاه پوشاک", "price": 3_000_000, "income": 300_000, "emoji": "👕"},
    "bookstore":   {"name": "کتاب‌فروشی", "price": 3_500_000, "income": 350_000, "emoji": "📚"},
    "mobile":      {"name": "موبایل‌فروشی", "price": 4_000_000, "income": 400_000, "emoji": "📱"},
}

# -------------------- کارگرها --------------------
WORKERS = {
    "teacher":    {"name": "معلم", "price": 300_000, "income": 30_000, "emoji": "👨‍🏫"},
    "doctor":     {"name": "پزشک", "price": 500_000, "income": 50_000, "emoji": "👨‍⚕️"},
    "driver":     {"name": "راننده", "price": 800_000, "income": 80_000, "emoji": "🚕"},
    "developer":  {"name": "برنامه‌نویس", "price": 1_200_000, "income": 120_000, "emoji": "👨‍💻"},
    "ai_expert":  {"name": "متخصص هوش مصنوعی", "price": 2_000_000, "income": 200_000, "emoji": "🤖"},
}

# -------------------- بازی‌ها --------------------
GAMES = {
    "rps":     {"name": "سنگ کاغذ قیچی", "emoji": "✊", "min_entry": 100,   "players": 2, "prize_multiplier": 1.5},
    "ttt":     {"name": "دوزه",          "emoji": "❌", "min_entry": 1_000, "players": 2, "prize_multiplier": 1.7},
    "quiz":    {"name": "کوییز",          "emoji": "🧠", "min_entry": 5_000, "players": 2, "prize_multiplier": 1.8},
    "penalty": {"name": "پنالتی",        "emoji": "⚽", "min_entry": 10_000, "players": 1, "prize_multiplier": 2.0},
    "luck":    {"name": "شانسی",          "emoji": "🍀", "min_entry": 20_000, "players": 1, "prize_multiplier": 2.0},
}

LUCK_EMOJIS = ["👍", "👎", "❤️"]
LUCK_PATTERN = re.compile(r"👍|👎|❤️|❤")

# -------------------- سوالات کوییز --------------------
QUIZ_QUESTIONS = [
    {"q": "پایتخت ایران کجاست؟", "options": ["تهران", "اصفهان", "شیراز", "مشهد"], "answer": 0},
    {"q": "بزرگ‌ترین سیاره منظومه شمسی کدام است؟", "options": ["زحل", "مشتری", "زمین", "نپتون"], "answer": 1},
    {"q": "آب از چه عناصری تشکیل شده است؟", "options": ["اکسیژن و نیتروژن", "هیدروژن و اکسیژن", "کربن و اکسیژن", "هیدروژن و کربن"], "answer": 1},
    {"q": "کدام کشور بیشترین جمعیت جهان را دارد؟", "options": ["هند", "چین", "آمریکا", "اندونزی"], "answer": 1},
    {"q": "نویسنده «شاهنامه» کیست؟", "options": ["حافظ", "سعدی", "فردوسی", "مولانا"], "answer": 2},
    {"q": "درازترین رود جهان کدام است؟", "options": ["نیل", "آمازون", "می‌سی‌سی‌پی", "دانوب"], "answer": 0},
    {"q": "واحد اندازه‌گیری نیرو چیست؟", "options": ["ژول", "وات", "نیوتن", "پاسکال"], "answer": 2},
    {"q": "کدام فلز رسانای بهتری برای برق است؟", "options": ["آهن", "مس", "طلا", "نقره"], "answer": 3},
    {"q": "اولین انسان روی ماه چه کسی بود؟", "options": ["یوری گاگارین", "نیل آرمسترانگ", "باز آلدرین", "مایکل کالینز"], "answer": 1},
    {"q": "زبان رسمی برزیل چیست؟", "options": ["اسپانیایی", "پرتغالی", "انگلیسی", "فرانسوی"], "answer": 1},
    {"q": "کدام حیوان سریع‌ترین جانور خشکی است؟", "options": ["شیر", "یوزپلنگ", "اسب", "آهو"], "answer": 1},
    {"q": "قاره‌ای که بیشترین کشورها را دارد کدام است؟", "options": ["آسیا", "اروپا", "آفریقا", "آمریکای جنوبی"], "answer": 2},
]

# ============================================================
# 🗄️ دیتابیس
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    bank_balance INTEGER NOT NULL DEFAULT 0,
    card_number TEXT UNIQUE,
    last_daily TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asset_type TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    purchase_price INTEGER NOT NULL,
    daily_income INTEGER NOT NULL,
    purchased_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_user_type
ON assets(user_id, asset_type);
"""

# وضعیت‌های موقت در حافظه
user_states: dict[int, dict] = {}
rooms: dict[str, dict] = {}
pending_transfers: dict[int, dict] = {}
penalty_games: dict[int, dict] = {}
luck_games: dict[int, dict] = {}
daily_lock = asyncio.Lock()

# ============================================================
# 🧰 ابزارهای کمکی
# ============================================================

def fa_to_en(text: str) -> str:
    """تبدیل ارقام فارسی به انگلیسی"""
    return text.translate(str.maketrans(PERSIAN_DIGITS, EN_DIGITS))


def to_fa_digits(value) -> str:
    """تبدیل ارقام انگلیسی به فارسی برای نمایش"""
    return str(value).translate(str.maketrans(EN_DIGITS, PERSIAN_DIGITS))


def fmt(amount: int) -> str:
    """قالب‌بندی عدد با جداکننده هزارگان و ارقام فارسی"""
    return to_fa_digits(f"{int(amount):,}")


def parse_amount(text: str) -> int | None:
    """تبدیل متن ورودی به عدد صحیح"""
    if not text:
        return None
    cleaned = fa_to_en(text).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    try:
        value = int(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def card_number_for(user_id: int) -> str:
    """ساخت شماره کارت ۱۶ رقمی بر اساس آیدی عددی"""
    digits = str(user_id).zfill(12)[-12:]
    return f"6037{digits}"


def format_card(card: str) -> str:
    """نمایش شماره کارت با خط تیره"""
    if not card or len(card) != 16:
        return card or "-"
    return f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:16]}"


def now_iso() -> str:
    return datetime.now(TEHRAN).isoformat()


def today_str() -> str:
    return datetime.now(TEHRAN).date().isoformat()


def escape(text: str | None) -> str:
    return html.escape(text or "")


def new_room_id() -> str:
    """شناسه کوتاه یکتا برای اتاق بازی"""
    alphabet = string.ascii_letters + string.digits
    while True:
        rid = "".join(secrets.choice(alphabet) for _ in range(8))
        if rid not in rooms:
            return rid


def find_user_room(user_id: int) -> str | None:
    """پیدا کردن اتاق فعال کاربر"""
    for rid, room in rooms.items():
        if user_id in room.get("players", []) and room.get("status") in ("waiting", "playing"):
            return rid
    return None


def parse_luck_emojis(text: str) -> list[str]:
    """استخراج ایموجی‌های مجاز از متن"""
    found = LUCK_PATTERN.findall(text or "")
    return ["❤️" if e == "❤" else e for e in found]


async def safe_edit(query, text: str, reply_markup=None):
    """ویرایش پیام با مدیریت خطا"""
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        try:
            await query.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("safe_edit fallback failed")


# ============================================================
# 🗄️ توابع دیتابیس
# ============================================================

async def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("✅ دیتابیس آماده است: %s", DB_PATH)


async def ensure_user(user) -> dict:
    """ساخت کاربر در صورت نبود و برگرداندن اطلاعاتش"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT OR IGNORE INTO users
                (user_id, username, first_name, balance, bank_balance, card_number, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                user.username,
                user.first_name,
                START_BALANCE,
                0,
                card_number_for(user.id),
                now_iso(),
            ),
        )
        await db.execute(
            "UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (user.username, user.first_name, user.id),
        )
        await db.commit()

        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
        row = await cur.fetchone()
        return dict(row)


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def add_balance(user_id: int, amount: int):
    if amount <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (amount, user_id),
        )
        await db.commit()


async def deduct_balance(user_id: int, amount: int) -> bool:
    """کم کردن موجودی به صورت اتمیک"""
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
            (amount, user_id, amount),
        )
        await db.commit()
        return cur.rowcount == 1


async def bank_deposit(user_id: int, amount: int) -> bool:
    """واریز به بانک به صورت اتمیک"""
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET balance = balance - ?, bank_balance = bank_balance + ? "
                "WHERE user_id=? AND balance >= ?",
                (amount, amount, user_id, amount),
            )
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("bank_deposit failed")
            return False


async def bank_withdraw(user_id: int, amount: int) -> bool:
    """برداشت از بانک به صورت اتمیک"""
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET bank_balance = bank_balance - ?, balance = balance + ? "
                "WHERE user_id=? AND bank_balance >= ?",
                (amount, amount, user_id, amount),
            )
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("bank_withdraw failed")
            return False


async def transfer_coins(sender_id: int, recipient_id: int, amount: int, fee: int) -> bool:
    """انتقال اتمیک زرکوین همراه با کارمزد"""
    total = amount + fee
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
                (total, sender_id, total),
            )
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (amount, recipient_id),
            )
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("transfer_coins failed")
            return False


async def count_assets(user_id: int, asset_type: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM assets WHERE user_id=? AND asset_type=?",
            (user_id, asset_type),
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def get_assets(user_id: int, asset_type: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM assets WHERE user_id=? AND asset_type=? ORDER BY id ASC",
            (user_id, asset_type),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def buy_asset(
    user_id: int,
    asset_type: str,
    asset_key: str,
    price: int,
    income: int,
) -> str:
    """
    خرید ملک یا کارگر به صورت اتمیک.
    خروجی: ok / limit / balance / error
    """
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            cur = await db.execute(
                "SELECT COUNT(*) FROM assets WHERE user_id=? AND asset_type=?",
                (user_id, asset_type),
            )
            count = int((await cur.fetchone())[0])
            if count >= MAX_ASSETS_PER_TYPE:
                await db.rollback()
                return "limit"

            cur = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
                (price, user_id, price),
            )
            if cur.rowcount != 1:
                await db.rollback()
                return "balance"

            await db.execute(
                """
                INSERT INTO assets
                    (user_id, asset_type, asset_key, purchase_price, daily_income, purchased_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, asset_type, asset_key, price, income, now_iso()),
            )
            await db.commit()
            return "ok"
        except Exception:
            await db.rollback()
            logger.exception("buy_asset failed")
            return "error"


async def find_user_by_card(card: str) -> dict | None:
    """جستجوی کاربر با شماره کارت"""
    digits = "".join(ch for ch in (card or "") if ch.isdigit())
    if len(digits) != 16:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE card_number=?", (digits,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ============================================================
# 💸 سود روزانه ساعت ۰۰:۰۰
# ============================================================

async def daily_payout(context: ContextTypes.DEFAULT_TYPE = None):
    """
    پرداخت سود بانکی ۲٪ و درآمد ملک/کارگر.
    ایدمپوتنت است: برای هر کاربر در هر روز فقط یک بار اجرا می‌شود.
    """
    async with daily_lock:
        today = datetime.now(TEHRAN).date()
        today_iso = today.isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            try:
                rows = await db.execute_fetchall(
                    "SELECT user_id, bank_balance, last_daily FROM users"
                )
            except Exception:
                logger.exception("daily_payout fetch failed")
                return

            for row in rows:
                user_id = row["user_id"]
                bank_balance = int(row["bank_balance"] or 0)
                last_daily = row["last_daily"]

                # محاسبه تعداد روزهای عقب‌افتاده (حداکثر ۷ روز برای جلوگیری از پرداخت نجومی)
                days = 1
                if last_daily:
                    try:
                        last_date = datetime.fromisoformat(last_daily).date()
                        days = max(1, (today - last_date).days)
                        days = min(days, 7)
                    except Exception:
                        days = 1

                # اگر امروز قبلاً پرداخت شده، رد شو
                if last_daily == today_iso:
                    continue

                # سود مرکب بانک
                interest = 0
                current_bank = bank_balance
                for _ in range(days):
                    daily_interest = int(current_bank * BANK_INTEREST_RATE)
                    interest += daily_interest
                    current_bank += daily_interest

                # درآمد ملک و کارگر
                cur = await db.execute(
                    "SELECT COALESCE(SUM(daily_income), 0) AS total FROM assets WHERE user_id=?",
                    (user_id,),
                )
                asset_row = await cur.fetchone()
                daily_asset_income = int(asset_row["total"] or 0)
                asset_income = daily_asset_income * days

                if interest == 0 and asset_income == 0:
                    await db.execute(
                        "UPDATE users SET last_daily=? WHERE user_id=?",
                        (today_iso, user_id),
                    )
                    continue

                await db.execute(
                    """
                    UPDATE users
                    SET bank_balance = bank_balance + ?,
                        balance = balance + ?,
                        last_daily = ?
                    WHERE user_id = ?
                    """,
                    (interest, asset_income, today_iso, user_id),
                )

            await db.commit()
        logger.info("💰 سود روزانه %s پرداخت شد.", today_iso)


# ============================================================
# 🎛️ کیبوردها
# ============================================================

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"),
            InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu"),
        ],
        [
            InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"),
            InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu"),
        ],
        [
            InlineKeyboardButton("💸 انتقال زرکوین", callback_data="transfer:start"),
        ],
        [
            InlineKeyboardButton("📚 راهنما", callback_data="help:menu"),
        ],
    ])


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu:main")],
    ])


def back_games_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")],
    ])


def bank_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 واریز به بانک", callback_data="bank:deposit"),
            InlineKeyboardButton("🏧 برداشت از بانک", callback_data="bank:withdraw"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])


def properties_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for key, prop in sorted(PROPERTIES.items(), key=lambda x: x[1]["price"]):
        pair.append(
            InlineKeyboardButton(
                f"{prop['emoji']} {prop['name']} | {fmt(prop['price'])}",
                callback_data=f"prop:buy:{key}",
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def workers_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for key, worker in sorted(WORKERS.items(), key=lambda x: x[1]["price"]):
        pair.append(
            InlineKeyboardButton(
                f"{worker['emoji']} {worker['name']} | {fmt(worker['price'])}",
                callback_data=f"worker:buy:{key}",
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def games_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game:rps"),
            InlineKeyboardButton("❌ دوزه", callback_data="game:ttt"),
        ],
        [
            InlineKeyboardButton("🧠 کوییز", callback_data="game:quiz"),
            InlineKeyboardButton("⚽ پنالتی", callback_data="game:penalty"),
        ],
        [
            InlineKeyboardButton("🍀 شانسی", callback_data="game:luck"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])


def join_room_kb(room_id: str, game_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 ورود به بازی", callback_data=f"{game_key}:join:{room_id}")],
        [InlineKeyboardButton("❌ لغو اتاق", callback_data=f"room:cancel:{room_id}")],
    ])


def rps_choice_kb(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✊ سنگ", callback_data=f"rps:choice:{room_id}:rock"),
            InlineKeyboardButton("✋ کاغذ", callback_data=f"rps:choice:{room_id}:paper"),
            InlineKeyboardButton("✌️ قیچی", callback_data=f"rps:choice:{room_id}:scissors"),
        ],
    ])


def ttt_keyboard(room: dict) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx = r * 3 + c
            val = room["board"][idx]
            if val:
                label = "❌" if val == "X" else "⭕"
                row.append(InlineKeyboardButton(label, callback_data=f"ttt:noop:{room['id']}:{idx}"))
            else:
                row.append(InlineKeyboardButton("⬜", callback_data=f"ttt:move:{room['id']}:{idx}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def quiz_keyboard(room_id: str, options: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for idx, option in enumerate(options):
        rows.append([InlineKeyboardButton(option, callback_data=f"quiz:ans:{room_id}:{idx}")])
    return InlineKeyboardMarkup(rows)


def penalty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚽ شوت!", callback_data="penalty:shoot")],
    ])


def transfer_confirm_kb(sender_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأیید انتقال", callback_data=f"transfer:confirm:{sender_id}"),
            InlineKeyboardButton("❌ انصراف", callback_data=f"transfer:cancel:{sender_id}"),
        ],
    ])


# ============================================================
# 🖥️ منوها و متن‌ها
# ============================================================

async def build_main_menu_text(user_id: int) -> str:
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    return (
        "✨ <b>به دنیای زرکوین خوش اومدی!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی کیف پول: <b>{fmt(balance)}</b> زرکوین\n\n"
        "از دکمه‌های زیر انتخاب کن:\n"
        "🏦 بانک | 🏠 ملک | 👷 کارگر | 🎮 بازی | 💸 انتقال"
    )


async def build_bank_text(user_id: int) -> str:
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    bank_balance = int(user["bank_balance"]) if user else 0
    card = format_card(user["card_number"]) if user else "-"
    daily_interest = int(bank_balance * BANK_INTEREST_RATE)
    return (
        "🏦 <b>بانک زرکوین</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 شماره کارت شما:\n<code>{card}</code>\n\n"
        f"💰 موجودی کیف پول: <b>{fmt(balance)}</b> زرکوین\n"
        f"🏦 موجودی بانک: <b>{fmt(bank_balance)}</b> زرکوین\n"
        f"📈 سود روزانه (۲٪): <b>{fmt(daily_interest)}</b> زرکوین\n\n"
        "⏰ سود هر روز ساعت <b>۰۰:۰۰</b> به وقت تهران به حسابت واریز میشه."
    )


async def build_properties_text(user_id: int) -> str:
    owned = await get_assets(user_id, "property")
    total_daily = sum(int(a["daily_income"]) for a in owned)
    lines = [
        "🏠 <b>املاک شما</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 تعداد: <b>{to_fa_digits(len(owned))}/{to_fa_digits(MAX_ASSETS_PER_TYPE)}</b>",
        f"💵 درآمد روزانه کل: <b>{fmt(total_daily)}</b> زرکوین\n",
    ]
    if owned:
        for i, asset in enumerate(owned, 1):
            prop = PROPERTIES.get(asset["asset_key"], {})
            name = prop.get("name", asset["asset_key"])
