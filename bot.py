# -*- coding: utf-8 -*-
"""ربات زرکوین (بات زر) - نسخه کامل"""
import asyncio
import html
import logging
import os
import random
import re
import secrets
import string
from datetime import datetime, time
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

# ============================== تنظیمات ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")
TEHRAN = ZoneInfo("Asia/Tehran")

DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", os.path.join(os.getcwd(), "data"))
DB_PATH = os.path.join(DATA_DIR, "zarcoin.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("zarcoin")

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

BANK_RATE = 0.02
MAX_ASSETS = 5
TRANSFER_FEE_RATE = 0.01
TRANSFER_FEE_MIN = 1_000_000

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

WORKERS = {
    "teacher":   {"name": "معلم", "price": 300_000, "income": 30_000, "emoji": "👨‍🏫"},
    "doctor":    {"name": "پزشک", "price": 500_000, "income": 50_000, "emoji": "👨‍⚕️"},
    "driver":    {"name": "راننده", "price": 800_000, "income": 80_000, "emoji": "🚕"},
    "developer": {"name": "برنامه‌نویس", "price": 1_200_000, "income": 120_000, "emoji": "👨‍💻"},
    "ai_expert": {"name": "متخصص هوش مصنوعی", "price": 2_000_000, "income": 200_000, "emoji": "🤖"},
}

GAMES = {
    "rps":     {"name": "سنگ کاغذ قیچی", "emoji": "✊", "min": 100, "players": 2, "mult": 1.5},
    "ttt":     {"name": "دوزه", "emoji": "❌", "min": 1_000, "players": 2, "mult": 1.7},
    "quiz":    {"name": "کوییز", "emoji": "🧠", "min": 5_000, "players": 2, "mult": 1.8},
    "penalty": {"name": "پنالتی", "emoji": "⚽", "min": 10_000, "players": 1, "mult": 2.0},
    "luck":    {"name": "شانسی", "emoji": "🍀", "min": 20_000, "players": 1, "mult": 2.0},
}

QUIZ_QUESTIONS = [
    {"q": "پایتخت ایران کجاست؟", "opts": ["تهران", "اصفهان", "شیراز", "مشهد"], "ans": 0},
    {"q": "بزرگ‌ترین سیاره منظومه شمسی کدام است؟", "opts": ["زحل", "مشتری", "زمین", "نپتون"], "ans": 1},
    {"q": "آب از چه عناصری تشکیل شده است؟", "opts": ["اکسیژن و نیتروژن", "هیدروژن و اکسیژن", "کربن و اکسیژن", "هیدروژن و کربن"], "ans": 1},
    {"q": "کدام کشور بیشترین جمعیت را دارد؟", "opts": ["هند", "چین", "آمریکا", "اندونزی"], "ans": 1},
    {"q": "نویسنده شاهنامه کیست؟", "opts": ["حافظ", "سعدی", "فردوسی", "مولانا"], "ans": 2},
    {"q": "درازترین رود جهان کدام است؟", "opts": ["نیل", "آمازون", "می‌سی‌سی‌پی", "دانوب"], "ans": 0},
    {"q": "واحد اندازه‌گیری نیرو چیست؟", "opts": ["ژول", "وات", "نیوتن", "پاسکال"], "ans": 2},
    {"q": "اولین انسان روی ماه چه کسی بود؟", "opts": ["یوری گاگارین", "نیل آرمسترانگ", "باز آلدرین", "مایکل کالینز"], "ans": 1},
    {"q": "زبان رسمی برزیل چیست؟", "opts": ["اسپانیایی", "پرتغالی", "انگلیسی", "فرانسوی"], "ans": 1},
    {"q": "سریع‌ترین جانور خشکی کدام است؟", "opts": ["شیر", "یوزپلنگ", "اسب", "آهو"], "ans": 1},
]

LUCK_EMOJIS = ["👍", "👎", "❤️"]
LUCK_PATTERN = re.compile(r"👍|👎|❤️|❤")

# ============================== دیتابیس ==============================
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
CREATE INDEX IF NOT EXISTS idx_assets ON assets(user_id, asset_type);
"""

user_states: dict[int, dict] = {}
rooms: dict[str, dict] = {}
pending_transfers: dict[int, dict] = {}
penalty_games: dict[int, dict] = {}
luck_games: dict[int, dict] = {}
daily_lock = asyncio.Lock()

# ============================== کمکی‌ها ==============================
def fa_to_en(text: str) -> str:
    return (text or "").translate(str.maketrans(PERSIAN_DIGITS, EN_DIGITS))

def to_fa(value) -> str:
    return str(value).translate(str.maketrans(EN_DIGITS, PERSIAN_DIGITS))

def fmt(amount: int) -> str:
    return to_fa(f"{int(amount):,}")

def parse_amount(text: str):
    cleaned = fa_to_en(text).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    v = int(cleaned)
    return v if v > 0 else None

def card_number_for(user_id: int) -> str:
    return f"6037{str(user_id).zfill(12)[-12:]}"

def format_card(card: str) -> str:
    if not card or len(card) != 16:
        return card or "-"
    return f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:16]}"

def now_iso() -> str:
    return datetime.now(TEHRAN).isoformat()

def today_str() -> str:
    return datetime.now(TEHRAN).date().isoformat()

def escape(text) -> str:
    return html.escape(str(text or ""))

def new_room_id() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        rid = "".join(secrets.choice(alphabet) for _ in range(8))
        if rid not in rooms:
            return rid

def find_user_room(user_id: int):
    for rid, room in rooms.items():
        if user_id in room.get("players", []) and room.get("status") in ("waiting", "playing"):
            return rid
    return None

def parse_luck_emojis(text: str):
    found = LUCK_PATTERN.findall(text or "")
    return ["❤️" if e == "❤" else e for e in found]

def ttt_check_win(board):
    lines = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None

async def safe_edit(query, text: str, reply_markup=None):
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        try:
            await query.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception:
            logger.exception("safe_edit failed")

# ============================== DB ==============================
async def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("DB ready: %s", DB_PATH)

async def ensure_user(user) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO users "
            "(user_id, username, first_name, balance, bank_balance, card_number, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?)",
            (user.id, user.username, user.first_name, START_BALANCE,
             card_number_for(user.id), now_iso()))
        await db.execute(
            "UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (user.username, user.first_name, user.id))
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
        row = await cur.fetchone()
        return dict(row)

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def add_balance(user_id: int, amount: int):
    if amount <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?",
                         (amount, user_id))
        await db.commit()

async def deduct_balance(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
            (amount, user_id, amount))
        await db.commit()
        return cur.rowcount == 1

async def bank_deposit(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET balance = balance - ?, bank_balance = bank_balance + ? "
                "WHERE user_id=? AND balance >= ?",
                (amount, amount, user_id, amount))
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("bank_deposit")
            return False

async def bank_withdraw(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET bank_balance = bank_balance - ?, balance = balance + ? "
                "WHERE user_id=? AND bank_balance >= ?",
                (amount, amount, user_id, amount))
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("bank_withdraw")
            return False

async def transfer_coins(sender_id: int, recipient_id: int, amount: int, fee: int) -> bool:
    total = amount + fee
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
                (total, sender_id, total))
            if cur.rowcount != 1:
                await db.rollback()
                return False
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (amount, recipient_id))
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            logger.exception("transfer_coins")
            return False

async def count_assets(user_id: int, asset_type: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM assets WHERE user_id=? AND asset_type=?",
            (user_id, asset_type))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def get_assets(user_id: int, asset_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM assets WHERE user_id=? AND asset_type=? ORDER BY id ASC",
            (user_id, asset_type))
        return [dict(r) for r in await cur.fetchall()]

async def buy_asset(user_id: int, asset_type: str, asset_key: str, price: int, income: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT COUNT(*) FROM assets WHERE user_id=? AND asset_type=?",
                (user_id, asset_type))
            if int((await cur.fetchone())[0]) >= MAX_ASSETS:
                await db.rollback()
                return "limit"
            cur = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
                (price, user_id, price))
            if cur.rowcount != 1:
                await db.rollback()
                return "balance"
            await db.execute(
                "INSERT INTO assets (user_id, asset_type, asset_key, purchase_price, daily_income, purchased_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, asset_type, asset_key, price, income, now_iso()))
            await db.commit()
            return "ok"
        except Exception:
            await db.rollback()
            logger.exception("buy_asset")
            return "error"

async def find_user_by_card(card: str):
    digits = "".join(ch for ch in (card or "") if ch.isdigit())
    if len(digits) != 16:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE card_number=?", (digits,))
        row = await cur.fetchone()
        return dict(row) if row else None

# ============================== سود روزانه ==============================
async def daily_payout(context: ContextTypes.DEFAULT_TYPE = None):
    async with daily_lock:
        today = datetime.now(TEHRAN).date()
        today_iso = today.isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT user_id, bank_balance, last_daily FROM users")
            for row in rows:
                user_id = row["user_id"]
                bank_balance = int(row["bank_balance"] or 0)
                last_daily = row["last_daily"]
                if last_daily == today_iso:
                    continue
                days = 1
                if last_daily:
                    try:
                        last_date = datetime.fromisoformat(last_daily).date()
                        days = max(1, min((today - last_date).days, 7))
                    except Exception:
                        days = 1
                interest = 0
                current = bank_balance
                for _ in range(days):
                    d = int(current * BANK_RATE)
                    interest += d
                    current += d
                cur = await db.execute(
                    "SELECT COALESCE(SUM(daily_income), 0) FROM assets WHERE user_id=?",
                    (user_id,))
                asset_income = int((await cur.fetchone())[0] or 0) * days
                await db.execute(
                    "UPDATE users SET bank_balance = bank_balance + ?, "
                    "balance = balance + ?, last_daily = ? WHERE user_id=?",
                    (interest, asset_income, today_iso, user_id))
            await db.commit()
        logger.info("daily payout done for %s", today_iso)

# ============================== کیبوردها ==============================
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"),
         InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu")],
        [InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"),
         InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu")],
        [InlineKeyboardButton("💸 انتقال زرکوین", callback_data="transfer:start")],
        [InlineKeyboardButton("📚 راهنما", callback_data="help:menu")],
    ])

def back_main_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]])

def back_games_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")]])

def bank_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 واریز", callback_data="bank:deposit"),
         InlineKeyboardButton("🏧 برداشت", callback_data="bank:withdraw")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

def properties_menu_kb():
    rows, pair = [], []
    for key, prop in sorted(PROPERTIES.items(), key=lambda x: x[1]["price"]):
        pair.append(InlineKeyboardButton(
            f"{prop['emoji']} {prop['name']} | {fmt(prop['price'])}",
            callback_data=f"prop:buy:{key}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

def workers_menu_kb():
    rows, pair = [], []
    for key, w in sorted(WORKERS.items(), key=lambda x: x[1]["price"]):
        pair.append(InlineKeyboardButton(
            f"{w['emoji']} {w['name']} | {fmt(w['price'])}",
            callback_data=f"worker:buy:{key}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

def games_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game:rps"),
         InlineKeyboardButton("❌ دوزه", callback_data="game:ttt")],
        [InlineKeyboardButton("🧠 کوییز", callback_data="game:quiz"),
         InlineKeyboardButton("⚽ پنالتی", callback_data="game:penalty")],
        [InlineKeyboardButton("🍀 شانسی", callback_data="game:luck")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

def join_room_kb(room_id: str, game_key: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 ورود به بازی", callback_data=f"{game_key}:join:{room_id}")],
        [InlineKeyboardButton("❌ لغو", callback_data=f"room:cancel:{room_id}")],
    ])

def rps_choice_kb(room_id: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✊ سنگ", callback_data=f"rps:c:{room_id}:rock"),
        InlineKeyboardButton("✋ کاغذ", callback_data=f"rps:c:{room_id}:paper"),
        InlineKeyboardButton("✌️ قیچی", callback_data=f"rps:c:{room_id}:scissors"),
    ]])

def ttt_keyboard(room: dict):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            v = room["board"][i]
            if v == "X":
                row.append(InlineKeyboardButton("❌", callback_data="ttt:noop"))
            elif v == "O":
                row.append(InlineKeyboardButton("⭕", callback_data="ttt:noop"))
            else:
                row.append(InlineKeyboardButton("⬜", callback_data=f"ttt:m:{room['id']}:{i}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

def quiz_keyboard(room_id: str, opts):
    return InlineKeyboardMarkup([[InlineKeyboardButton(o, callback_data=f"quiz:a:{room_id}:{i}")]
                                 for i, o in enumerate(opts)])

def penalty_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚽ شوت!", callback_data="pen:shoot")]])

def transfer_confirm_kb(user_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"tr:c:{user_id}"),
        InlineKeyboardButton("❌ انصراف", callback_data=f"tr:x:{user_id}"),
    ]])

# ============================== متن‌ها ==============================
async def build_main_menu_text(user_id):
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    return (
        "✨ <b>به دنیای زرکوین خوش اومدی!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی کیف پول: <b>{fmt(balance)}</b> زرکوین\n\n"
        "از دکمه‌های زیر انتخاب کن 👇"
    )

async def build_bank_text(user_id):
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    bank_balance = int(user["bank_balance"]) if user else 0
    card = format_card(user["card_number"]) if user else "-"
    interest = int(bank_balance * BANK_RATE)
    return (
        "🏦 <b>بانک زرکوین</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 شماره کارت شما:\n<code>{card}</code>\n\n"
        f"💰 کیف پول: <b>{fmt(balance)}</b>\n"
        f"🏦 بانک: <b>{fmt(bank_balance)}</b>\n"
        f"📈 سود روزانه (۲٪): <b>{fmt(interest)}</b>\n\n"
        "⏰ سود هر شب ساعت <b>۰۰:۰۰</b> به وقت تهران واریز میشه."
    )

async def build_assets_text(user_id, asset_type):
    if asset_type == "property":
        title, emoji, store = "املاک شما", "🏠", PROPERTIES
    else:
        title, emoji, store = "کارگرهای شما", "👷", WORKERS
    owned = await get_assets(user_id, asset_type)
    total_daily = sum(int(a["daily_income"]) for a in owned)
    lines = [
        f"{emoji} <b>{title}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 تعداد: <b>{to_fa(len(owned))}/{to_fa(MAX_ASSETS)}</b>",
        f"💵 درآمد روزانه کل: <b>{fmt(total_daily)}</b> زرکوین\n",
    ]
    if owned:
        for i, a in enumerate(owned, 1):
            info = store.get(a["asset_key"], {})
            lines.append(f"{to_fa(i)}. {info.get('emoji','•')} {info.get('name', a['asset_key'])} — {fmt(a['daily_income'])}/روز")
    else:
        lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)

# ============================== کامندها ==============================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        await build_main_menu_text(update.effective_user.id),
        parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def cmd_zarbat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        await build_main_menu_text(update.effective_user.id),
        parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def cmd_zarbazi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        "🎮 <b>بازی‌های زرکوین</b>\n\nیکی رو انتخاب کن:",
        parse_mode=ParseMode.HTML, reply_markup=games_menu_kb())

# ============================== Callback router ==============================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""

    # --- منو اصلی
    if data == "menu:main":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_main_menu_text(query.from_user.id), main_menu_kb())
        return

    # --- بانک
    if data == "bank:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_bank_text(query.from_user.id), bank_menu_kb())
        return
    if data == "bank:deposit":
        await query.answer()
        user_states[query.from_user.id] = {"action": "bank_deposit"}
        await safe_edit(query, "💰 <b>واریز به بانک</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return
    if data == "bank:withdraw":
        await query.answer()
        user_states[query.from_user.id] = {"action": "bank_withdraw"}
        await safe_edit(query, "🏧 <b>برداشت از بانک</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return

    # --- ملک
    if data == "prop:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(query.from_user.id, "property") +
                        "\n\n👇 از لیست زیر یکی بخر:", properties_menu_kb())
        return
    if data.startswith("prop:buy:"):
        key = data.split(":", 2)[2]
        prop = PROPERTIES.get(key)
        if not prop:
            await query.answer("❌ ملک نامعتبر", show_alert=True); return
        await ensure_user(query.from_user)
        count = await count_assets(query.from_user.id, "property")
        if count >= MAX_ASSETS:
            await query.answer(f"❌ حداکثر {MAX_ASSETS} ملک مجاز!", show_alert=True); return
        user = await get_user(query.from_user.id)
        if int(user["balance"]) < prop["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        r = await buy_asset(query.from_user.id, "property", key, prop["price"], prop["income"])
        if r == "ok":
            await query.answer(f"✅ {prop['name']} خریداری شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_ASSETS} ملک مجاز!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
        await safe_edit(query, await build_assets_text(query.from_user.id, "property") +
                        "\n\n👇 از لیست زیر یکی بخر:", properties_menu_kb())
        return

    # --- کارگر
    if data == "worker:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(query.from_user.id, "worker") +
                        "\n\n👇 از لیست زیر یکی استخدام کن:", workers_menu_kb())
        return
    if data.startswith("worker:buy:"):
        key = data.split(":", 2)[2]
        w = WORKERS.get(key)
        if not w:
            await query.answer("❌ نامعتبر", show_alert=True); return
        await ensure_user(query.from_user)
        count = await count_assets(query.from_user.id, "worker")
        if count >= MAX_ASSETS:
            await query.answer(f"❌ حداکثر {MAX_ASSETS} کارگر مجاز!", show_alert=True); return
        user = await get_user(query.from_user.id)
        if int(user["balance"]) < w["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        r = await buy_asset(query.from_user.id, "worker", key, w["price"], w["income"])
        if r == "ok":
            await query.answer(f"✅ {w['name']} استخدام شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_ASSETS} کارگر مجاز!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
        await safe_edit(query, await build_assets_text(query.from_user.id, "worker") +
                        "\n\n👇 از لیست زیر یکی استخدام کن:", workers_menu_kb())
        return

    # --- بازی
    if data == "game:menu":
        await query.answer()
        await safe_edit(query, "🎮 <b>بازی‌های زرکوین</b>\n\nیکی رو انتخاب کن:", games_menu_kb())
        return
    if data.startswith("game:") and data.count(":") == 1:
        gk = data.split(":", 1)[1]
        if gk in GAMES:
            await start_game_entry(query, gk)
        return

    # --- راهنما
    if data == "help:menu":
        await query.answer()
        await safe_edit(query, HELP_TEXT, back_main_kb())
        return

    # --- انتقال
    if data == "transfer:start":
        await query.answer()
        user_states[query.from_user.id] = {"action": "transfer_amount"}
        await safe_edit(query, "💸 <b>انتقال زرکوین</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return
    if data.startswith("tr:c:"):
        await query.answer()
        await confirm_transfer(query, int(data.split(":")[2]))
        return
    if data.startswith("tr:x:"):
        await query.answer()
        pending_transfers.pop(query.from_user.id, None)
        await safe_edit(query, "❌ انتقال لغو شد.", back_main_kb())
        return

    # --- اتاق
    if data.startswith("room:cancel:"):
        await query.answer()
        await cancel_room(query, data.split(":")[2])
        return

    # --- RPS
    if data.startswith("rps:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data.startswith("rps:c:"):
        await query.answer()
        parts = data.split(":")
        await rps_choose(query, context, parts[2], parts[3])
        return

    # --- TTT
    if data.startswith("ttt:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data == "ttt:noop":
        await query.answer(); return
    if data.startswith("ttt:m:"):
        parts = data.split(":")
        await ttt_move(query, context, parts[2], int(parts[3]))
        return

    # --- Quiz
    if data.startswith("quiz:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data.startswith("quiz:a:"):
        parts = data.split(":")
        await quiz_answer(query, parts[2], int(parts[3]))
        return

    # --- Penalty
    if data == "pen:shoot":
        await query.answer()
        await penalty_shoot(query, context)
        return

    await query.answer()


# ============================== بازی‌ها ==============================
async def start_game_entry(query, gk: str):
    user_id = query.from_user.id
    if find_user_room(user_id):
        await query.answer("⚠️ شما در یک بازی فعال هستید!", show_alert=True); return
    if user_id in penalty_games or user_id in luck_games:
        await query.answer("⚠️ یک بازی دیگر در جریان است!", show_alert=True); return
    g = GAMES[gk]
    user_states[user_id] = {"action": "game_entry", "game": gk}
    await safe_edit(query,
        f"{g['emoji']} <b>{g['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 حداقل ورودی: <b>{fmt(g['min'])}</b> زرکوین\n"
        f"👥 بازیکنان: {to_fa(g['players'])}\n\n"
        f"مبلغ ورودی رو بفرست:",
        back_games_kb())

async def join_room(query, context, room_id: str):
    room = rooms.get(room_id)
    if not room:
        await query.answer("❌ اتاق نیست", show_alert=True); return
    if room["status"] != "waiting":
        await query.answer("❌ بازی شروع شده", show_alert=True); return
    user_id = query.from_user.id
    if user_id == room["creator"]:
        await query.answer("❌ خودت سازنده‌ای", show_alert=True); return
    if user_id in room["players"]:
        await query.answer("✅ قبلاً وارد شدی", show_alert=True); return
    if find_user_room(user_id):
        await query.answer("⚠️ در بازی دیگر فعالی", show_alert=True); return
    await ensure_user(query.from_user)
    ok = await deduct_balance(user_id, room["entry"])
    if not ok:
        await query.answer("❌ موجودی کافی نیست", show_alert=True); return
    room["players"].append(user_id)
    room["user_names"] = room.get("user_names", {})
    room["user_names"][user_id] = query.from_user.first_name or str(user_id)
    room["status"] = "playing"

    gk = room["game"]
    if gk == "rps":
        room["choices"] = {}
        text = (f"{GAMES['rps']['emoji']} <b>سنگ کاغذ قیچی</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"👤 بازیکن ۱: {escape(room['user_names'][room['players'][0]])}\n"
                f"👤 بازیکن ۲: {escape(room['user_names'][room['players'][1]])}\n\n"
                f"هر دو یک گزینه بزنید:")
        await safe_edit(query, text, rps_choice_kb(room_id))
    elif gk == "ttt":
        room["board"] = [""] * 9
        room["turn"] = room["players"][0]
        room["symbols"] = {room["players"][0]: "X", room["players"][1]: "O"}
        await render_ttt(query, room)
    elif gk == "quiz":
        q = random.choice(QUIZ_QUESTIONS)
        room["question"] = q
        room["answered"] = False
        text = (f"{GAMES['quiz']['emoji']} <b>کوییز</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"❓ <b>{escape(q['q'])}</b>\n\n"
                f"اولین کسی که درست جواب بده برنده‌ست:")
        await safe_edit(query, text, quiz_keyboard(room_id, q["opts"]))

async def cancel_room(query, room_id: str):
    room = rooms.get(room_id)
    if not room:
        await query.answer("❌ اتاق نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"] and user_id != room["creator"]:
        await query.answer("❌ اجازه نداری", show_alert=True); return
    if room["status"] == "finished":
        return
    # برگرداندن پول همه بازیکنان
    for pid in room["players"]:
        await add_balance(pid, room["entry"])
    room["status"] = "cancelled"
    rooms.pop(room_id, None)
    await safe_edit(query, "❌ بازی لغو شد و پول‌ها برگشت داده شد.", back_games_kb())

# --- RPS
async def rps_choose(query, context, room_id, choice):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing":
        await query.answer("❌ بازی فعال نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"]:
        await query.answer("❌ تو بازیکن نیستی", show_alert=True); return
    if user_id in room["choices"]:
        await query.answer("✅ قبلاً انتخاب کردی", show_alert=True); return
    room["choices"][user_id] = choice
    if len(room["choices"]) < 2:
        await query.answer("✅ ثبت شد، منتظر حریف...", show_alert=True)
        text = (f"✊ <b>سنگ کاغذ قیچی</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"👤 {escape(room['user_names'][room['players'][0]])}: "
                f"{'✅' if room['players'][0] in room['choices'] else '⏳'}\n"
                f"👤 {escape(room['user_names'][room['players'][1]])}: "
                f"{'✅' if room['players'][1] in room['choices'] else '⏳'}")
        await safe_edit(query, text, None)
        return
    # resolve
    names = {1: "سنگ ✊", 2: "کاغذ ✋", 3: "قیچی ✌️"}
    p1, p2 = room["players"]
    c1, c2 = room["choices"][p1], room["choices"][p2]
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if c1 == c2:
        # مساوی: پول هر دو برگردانده شود
        await add_balance(p1, room["entry"])
        await add_balance(p2, room["entry"])
        result = "🤝 مساوی! پول‌ها برگشت."
    else:
        winner = p1 if beats[c1] == c2 else p2
        prize = int(room["entry"] * GAMES["rps"]["mult"])
        await add_balance(winner, prize)
        result = (f"🏆 <b>{escape(room['user_names'][winner])}</b> برنده شد!\n"
                  f"💰 جایزه: <b>{fmt(prize)}</b> زرکوین")
    text = (
        f"✊ <b>نتیجه سنگ کاغذ قیچی</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 {escape(room['user_names'][p1])}: {names[{'rock':1,'paper':2,'scissors':3}[c1]]}\n"
        f"👤 {escape(room['user_names'][p2])}: {names[{'rock':1,'paper':2,'scissors':3}[c2]]}\n\n"
        f"{result}")
    room["status"] = "finished"
    rooms.pop(room_id, None)
    await safe_edit(query, text, back_games_kb())

# --- TTT
async def render_ttt(query, room):
    p1, p2 = room["players"]
    turn = room["turn"]
    text = (f"❌ <b>دوزه</b>\n"
            f"💰 ورودی: {fmt(room['entry'])}\n\n"
            f"👤 {escape(room['user_names'][p1])} ❌\n"
            f"👤 {escape(room['user_names'][p2])} ⭕\n\n"
            f"🎯 نوبت: <b>{escape(room['user_names'][turn])}</b>")
    await safe_edit(query, text, ttt_keyboard(room))

async def ttt_move(query, context, room_id, idx):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing":
        await query.answer("❌ بازی فعال نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id != room["turn"]:
        await query.answer("⏳ نوبت تو نیست", show_alert=True); return
    if room["board"][idx]:
        await query.answer("❌ خانه پر است", show_alert=True); return
    room["board"][idx] = room["symbols"][user_id]
    winner_symbol = ttt_check_win(room["board"])
    if winner_symbol:
        p1, p2 = room["players"]
        if winner_symbol == "draw":
            await add_balance(p1, room["entry"])
            await add_balance(p2, room["entry"])
            text = "🤝 <b>مساوی!</b> پول‌ها برگشت."
        else:
            winner = p1 if winner_symbol == "X" else p2
            prize = int(room["entry"] * GAMES["ttt"]["mult"])
            await add_balance(winner, prize)
            text = f"🏆 <b>{escape(room['user_names'][winner])}</b> برنده شد!\n💰 جایزه: <b>{fmt(prize)}</b>"
        room["status"] = "finished"
        rooms.pop(room_id, None)
        await safe_edit(query, text, back_games_kb())
        return
    room["turn"] = p2 if room["turn"] == p1 else p1
    await render_ttt(query, room)

# --- Quiz
async def quiz_answer(query, room_id, idx):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing" or room.get("answered"):
        await query.answer("❌ بازی تمام شد", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"]:
        await query.answer("❌ تو بازیکن نیستی", show_alert=True); return
    q = room["question"]
    if idx == q["ans"]:
        room["answered"] = True
        prize = int(room["entry"] * GAMES["quiz"]["mult"])
        await add_balance(user_id, prize)
        # برگرداندن ورودی بازیکن بازنده هم نه — طبق منطق بازی می‌بازه
        room["status"] = "finished"
        rooms.pop(room_id, None)
        await query.answer("✅ درست بود!", show_alert=True)
        text = (f"🧠 <b>نتیجه کوییز</b>\n"
                f"❓ {escape(q['q'])}\n\n"
                f"🏆 برنده: <b>{escape(query.from_user.first_name)}</b>\n"
                f"💰 جایزه: <b>{fmt(prize)}</b> زرکوین")
        await safe_edit(query, text, back_games_kb())
    else:
        await query.answer("❌ اشتباه! دوباره تلاش کن", show_alert=True)

# --- Penalty
async def penalty_entry_done(update, entry: int):
    user_id = update.effective_user.id
    penalty_games[user_id] = {"entry": entry, "chat_id": update.effective_chat.id}
    await update.message.reply_text(
        f"⚽ <b>پنالتی</b>\n"
        f"💰 ورودی: {fmt(entry)}\n\n"
        f"آماده‌ای؟ شوت کن!",
        parse_mode=ParseMode.HTML, reply_markup=penalty_kb())

async def penalty_shoot(query, context):
    user_id = query.from_user.id
    game = penalty_games.get(user_id)
    if not game:
        await query.answer("❌ بازی فعالی نداری", show_alert=True); return
    penalty_games.pop(user_id, None)
    if random.random() < 0.5:
        prize = int(game["entry"] * 2)
        await add_balance(user_id, prize)
        await safe_edit(query,
            f"⚽ <b>گل!!!</b> 🎉\n\n"
            f"💰 جایزه: <b>{fmt(prize)}</b> زرکوین\n"
            f"🎯 توپ رفت گوشه دروازه!",
            back_games_kb())
    else:
        await safe_edit(query,
            f"⚽ <b>دروازه‌بان گرفت!</b> 😢\n\n"
            f"💸 متأسفانه {fmt(game['entry'])} زرکوین از دست رفت.",
            back_games_kb())

# --- Luck (شانسی)
async def luck_entry_done(update, context, entry: int):
    user_id = update.effective_user.id
    bot_seq = [random.choice(LUCK_EMOJIS) for _ in range(3)]
    luck_games[user_id] = {
        "entry": entry,
        "bot_seq": bot_seq,
        "deadline": datetime.now(TEHRAN).timestamp() + 60,
        "chat_id": update.effective_chat.id,
    }
    # تایمر 60 ثانیه
    try:
        context.job_queue.run_once(
            luck_timeout, when=60,
            data={"user_id": user_id},
            name=f"luck:{user_id}:{int(datetime.now().timestamp())}")
    except Exception:
        logger.exception("schedule luck_timeout failed")
    await update.message.reply_text(
        f"🍀 <b>بازی شانسی</b>\n"
        f"💰 ورودی: {fmt(entry)}\n\n"
        f"⏳ ۶۰ ثانیه وقت داری <b>سه ایموجی</b> از این‌ها بفرستی:\n"
        f"👍 👎 ❤️\n\n"
        f"مثال: 👍 👎 ❤️\n"
        f"🎯 هرچی به ترتیب بات نزدیک‌تر باشی، جایزه بیشتری می‌گیری!",
        parse_mode=ParseMode.HTML)

async def luck_timeout(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    game = luck_games.pop(user_id, None)
    if not game:
        return
    try:
        await context.bot.send_message(
            game["chat_id"],
            f"⏰ <a href='tg://user?id={user_id}'>وقت تموم شد!</a> بازی شانسی رو باختی.",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass

async def handle_luck_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True اگه پیام مربوط به بازی شانسی بود"""
    user_id = update.effective_user.id
    game = luck_games.get(user_id)
    if not game:
        return False
    # چک کردن تایم
    if datetime.now(TEHRAN).timestamp() > game["deadline"]:
        luck_games.pop(user_id, None)
        await update.message.reply_text("⏰ زمان تموم شد! بازی رو باختی.")
        return True
    emojis = parse_luck_emojis(update.message.text or "")
    if len(emojis) < 3:
        await update.message.reply_text("❌ باید <b>دقیقاً سه ایموجی</b> از (👍 👎 ❤️) بفرستی.",
                                        parse_mode=ParseMode.HTML)
        return True
    emojis = emojis[:3]
    luck_games.pop(user_id, None)
    bot_seq = game["bot_seq"]
    matches = sum(1 for a, b in zip(emojis, bot_seq) if a == b)
    seq_str = " ".join(bot_seq)
    user_str = " ".join(emojis)
    entry = game["entry"]
    if matches == 3:
        prize = entry * 2
        await add_balance(user_id, prize)
        text = (f"🍀 <b>بردی!</b> 🎉\n\n"
                f"🤖 ترتیب بات: {seq_str}\n"
                f"👤 ترتیب تو: {user_str}\n\n"
                f"🎯 هر سه تا درست! جایزه: <b>{fmt(prize)}</b>")
    elif matches == 2:
        prize = int(entry * 1.5)
        await add_balance(user_id, prize)
        text = (f"🍀 <b>نزدیک بود!</b>\n\n"
                f"🤖 ترتیب بات: {seq_str}\n"
                f"👤 ترتیب تو: {user_str}\n\n"
                f"🎯 دو تا درست! جایزه: <b>{fmt(prize)}</b>")
    else:
        text = (f"🍀 <b>باختی!</b> 😢\n\n"
                f"🤖 ترتیب بات: {seq_str}\n"
                f"👤 ترتیب تو: {user_str}\n\n"
                f"💸 {fmt(entry)} زرکوین از دست رفت.")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return True


# ============================== انتقال ==============================
async def confirm_transfer(query, owner_id: int):
    if query.from_user.id != owner_id:
        await query.answer("❌ این دکمه برای تو نیست", show_alert=True); return
    pending = pending_transfers.pop(owner_id, None)
    if not pending:
        await query.answer("❌ انتقال منقضی شده", show_alert=True); return
    ok = await transfer_coins(owner_id, pending["recipient_id"],
                              pending["amount"], pending["fee"])
    if not ok:
        await query.answer("❌ موجودی کافی نیست", show_alert=True)
        await safe_edit(query, "❌ انتقال انجام نشد.", back_main_kb())
        return
    await safe_edit(query,
        f"✅ <b>انتقال انجام شد!</b>\n\n"
        f"👤 گیرنده: {escape(pending['recipient_name'])}\n"
        f"💰 مبلغ: <b>{fmt(pending['amount'])}</b>\n"
        f"💵 کارمزد: <b>{fmt(pending['fee'])}</b>",
        back_main_kb())
    try:
        await query.bot.send_message(
            pending["recipient_id"],
            f"🎁 <b>زرکوین دریافت کردی!</b>\n\n"
            f"💰 مبلغ: <b>{fmt(pending['amount'])}</b> زرکوین\n"
            f"👤 از طرف: {escape(query.from_user.first_name)}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


# ============================== ادمین ==============================
async def owner_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return
    m = re.match(r"^انتقال زرکوین\s+([\d۰-۹,،]+)\s*$", msg.text or "")
    if not m:
        return
    amount = parse_amount(m.group(1))
    if not amount:
        await msg.reply_text("❌ مبلغ نامعتبر")
        return
    target = msg.reply_to_message.from_user
    if target.is_bot:
        await msg.reply_text("❌ به بات نمی‌شه انتقال داد")
        return
    await ensure_user(target)
    await add_balance(target.id, amount)
    await msg.reply_text(
        f"✅ <b>{fmt(amount)}</b> زرکوین به {escape(target.first_name)} واریز شد.",
        parse_mode=ParseMode.HTML)


# ============================== پیام‌های متنی ==============================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    # اول شانسی
    if await handle_luck_message(update, context):
        return
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    state = user_states.get(user_id)
    if not state:
        return

    action = state["action"]

    # --- بانک
    if action == "bank_deposit":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        await ensure_user(user)
        ok = await bank_deposit(user_id, amount)
        user_states.pop(user_id, None)
        if ok:
            await update.message.reply_text(
                f"✅ <b>{fmt(amount)}</b> زرکوین به بانک واریز شد.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        else:
            await update.message.reply_text("❌ موجودی کافی نیست",
                                            reply_markup=main_menu_kb())
        return

    if action == "bank_withdraw":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        ok = await bank_withdraw(user_id, amount)
        user_states.pop(user_id, None)
        if ok:
            await update.message.reply_text(
                f"✅ <b>{fmt(amount)}</b> زرکوین از بانک برداشت شد.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        else:
            await update.message.reply_text("❌ موجودی بانک کافی نیست",
                                            reply_markup=main_menu_kb())
        return

    # --- شروع بازی
    if action == "game_entry":
        gk = state["game"]
        g = GAMES.get(gk)
        if not g:
            user_states.pop(user_id, None); return
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]:
            await update.message.reply_text(f"❌ حداقل ورودی {fmt(g['min'])} است"); return
        await ensure_user(user)
        if not await deduct_balance(user_id, amount):
            await update.message.reply_text("❌ موجودی کافی نیست"); return
        user_states.pop(user_id, None)

        # تک‌نفره‌ها
        if gk == "penalty":
            await penalty_entry_done(update, amount)
            return
        if gk == "luck":
            await luck_entry_done(update, context, amount)
            return

        # دونفره
        rid = new_room_id()
        rooms[rid] = {
            "id": rid,
            "game": gk,
            "entry": amount,
            "creator": user_id,
            "players": [user_id],
            "status": "waiting",
            "user_names": {user_id: user.first_name or str(user_id)},
            "chat_id": update.effective_chat.id,
            "created_at": now_iso(),
        }
        text_out = (
            f"{g['emoji']} <b>{g['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 ورودی: <b>{fmt(amount)}</b>\n\n"
            f"👤 بازیکن ۱: {escape(user.first_name)}\n\n"
            f"⏳ منتظر بازیکن دوم...")
        await update.message.reply_text(
            text_out, parse_mode=ParseMode.HTML,
            reply_markup=join_room_kb(rid, gk))
        return

    # --- انتقال: مرحله ۱ (مبلغ)
    if action == "transfer_amount":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        await ensure_user(user)
        fee = int(amount * TRANSFER_FEE_RATE) if amount > TRANSFER_FEE_MIN else 0
        total = amount + fee
        u = await get_user(user_id)
        if int(u["balance"]) < total:
            await update.message.reply_text(
                f"❌ موجودی کافی نیست (نیاز: {fmt(total)})"); return
        user_states[user_id] = {"action": "transfer_card", "amount": amount, "fee": fee}
        await update.message.reply_text(
            f"💸 مبلغ: <b>{fmt(amount)}</b>\n"
            f"💵 کارمزد: <b>{fmt(fee)}</b>\n"
            f"📊 مجموع کسر: <b>{fmt(total)}</b>\n\n"
            f"شماره کارت مقصد رو بفرست:",
            parse_mode=ParseMode.HTML)
        return

    # --- انتقال: مرحله ۲ (کارت)
    if action == "transfer_card":
        recipient = await find_user_by_card(text)
        if not recipient:
            await update.message.reply_text("❌ کاربری با این شماره کارت پیدا نشد"); return
        if recipient["user_id"] == user_id:
            await update.message.reply_text("❌ به خودت نمی‌تونی انتقال بدی"); return
        amount = state["amount"]
        fee = state["fee"]
        total = amount + fee
        sender = await get_user(user_id)
        if int(sender["balance"]) < total:
            user_states.pop(user_id, None)
            await update.message.reply_text("❌ موجودی کافی نیست"); return
        pending_transfers[user_id] = {
            "recipient_id": recipient["user_id"],
            "recipient_name": recipient["first_name"] or str(recipient["user_id"]),
            "amount": amount,
            "fee": fee,
            "total": total,
        }
        user_states.pop(user_id, None)
        await update.message.reply_text(
            f"💸 <b>تأیید انتقال</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 گیرنده: {escape(recipient['first_name'])}\n"
            f"💳 کارت: <code>{format_card(recipient['card_number'])}</code>\n"
            f"💰 مبلغ: <b>{fmt(amount)}</b>\n"
            f"💵 کارمزد: <b>{fmt(fee)}</b>\n"
            f"📊 مجموع کسر: <b>{fmt(total)}</b>\n\n"
            f"آیا تأیید می‌کنی؟",
            parse_mode=ParseMode.HTML,
            reply_markup=transfer_confirm_kb(user_id))
        return


# ============================== خوش‌آمد گروه ==============================
async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if not cm or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    if cm.new_chat_member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and \
       cm.old_chat_member.status in (ChatMember.LEFT, ChatMember.KICKED):
        try:
            await context.bot.send_message(
                update.effective_chat.id,
                "✨ <b>زرکوین بات در این گروه فعال شد!</b> ✨\n\n"
                "💡 برای شروع بنویس: <code>زربات</code>\n"
                "🎮 برای بازی‌ها بنویس: <code>زر بازی</code>",
                parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("welcome failed")


# ============================== راهنما ==============================
HELP_TEXT = (
    "📚 <b>راهنمای زرکوین بات</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🪙 <b>زرکوین چیه؟</b>\n"
    "واحد پول بازی، قابل کسب از طریق خرید ملک، استخدام کارگر، سود بانکی و برد در بازی‌ها.\n\n"
    "🎯 <b>دستورات</b>\n"
    "• <code>زربات</code> — باز کردن منوی اصلی\n"
    "• <code>زر بازی</code> — رفتن به بخش بازی‌ها\n\n"
    "🏦 <b>بانک</b>\n"
    "سپرده‌گذاری با سود روزانه ۲٪ که هر شب ساعت ۰۰:۰۰ واریز میشه.\n"
    "شماره کارت اختصاصی بر اساس آیدی عددی تو ساخته میشه.\n\n"
    "🏠 <b>ملک‌ها</b> (حداکثر ۵ تا)\n"
    "🛒 سوپرمارکت ۵۰۰K → ۵۰K/روز\n"
    "🍎 میوه‌فروشی ۸۰۰K → ۸۰K/روز\n"
    "🥩 قصابی ۱M → ۱۰۰K/روز\n"
    "💊 داروخانه ۱.۸M → ۱۸۰K/روز\n"
    "💈 آرایشگاه ۲.۲M → ۲۲۰K/روز\n"
    "👕 پوشاک ۳M → ۳۰۰K/روز\n"
    "📚 کتاب‌فروشی ۳.۵M → ۳۵۰K/روز\n"
    "📱 موبایل ۴M → ۴۰۰K/روز\n\n"
    "👷 <b>کارگرها</b> (حداکثر ۵ تا)\n"
    "👨‍🏫 معلم ۳۰۰K → ۳۰K/روز\n"
    "👨‍⚕️ پزشک ۵۰۰K → ۵۰K/روز\n"
    "🚕 راننده ۸۰۰K → ۸۰K/روز\n"
    "👨‍💻 برنامه‌نویس ۱.۲M → ۱۲۰K/روز\n"
    "🤖 متخصص AI ۲M → ۲۰۰K/روز\n\n"
    "🎮 <b>بازی‌ها</b>\n"
    "✊ سنگ کاغذ قیچی (حداقل ۱۰۰)\n"
    "❌ دوزه (حداقل ۱۰۰۰)\n"
    "🧠 کوییز (حداقل ۵۰۰۰)\n"
    "⚽ پنالتی (حداقل ۱۰,۰۰۰)\n"
    "🍀 شانسی (حداقل ۲۰,۰۰۰)\n\n"
    "💸 <b>انتقال</b>\n"
    "با شماره کارت. بالای ۱ میلیون، ۱٪ کارمزد.\n\n"
    "👑 <b>اهدا از طرف مالک</b>\n"
    "مالک با ریپلای روی پیام کسی بنویسه:\n"
    "<code>انتقال زرکوین 5000</code>"
)


# ============================== main ==============================
async def post_init(app: Application):
    await init_db()
    # اجرای یک‌باره برای جبران عقب‌ماندگی
    try:
        await daily_payout()
    except Exception:
        logger.exception("initial daily_payout failed")
    # زمان‌بندی روزانه ساعت 00:00 تهران
    app.job_queue.run_daily(
        daily_payout,
        time=time(hour=0, minute=0, tzinfo=TEHRAN),
        name="daily_payout")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # منوها (فقط در گروه یا چت خصوصی)
    app.add_handler(MessageHandler(filters.Regex(r"^زربات$"), cmd_zarbat))
    app.add_handler(MessageHandler(filters.Regex(r"^زر\s*بازی$"), cmd_zarbazi))
    app.add_handler(CommandHandler("start", cmd_start))

    # خوش‌آمد گروه
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))

    # ادمین: انتقال زرکوین با ریپلای
    app.add_handler(MessageHandler(
        filters.Regex(r"^انتقال زرکوین\s+[\d۰-۹,،]+"),
        owner_give))

    # کیبورد
    app.add_handler(CallbackQueryHandler(callback_handler))

    # متن (آخر از همه)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🚀 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
