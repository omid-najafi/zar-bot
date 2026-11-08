import html
import secrets
import string
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from cachetools import TTLCache
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter

TEHRAN = ZoneInfo("Asia/Tehran")
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

rooms = {}
pending_transfers = {}
penalty_games = {}
casino_pending = {}
daily_lock = asyncio.Lock()

menu_owners = TTLCache(maxsize=10000, ttl=3600)
user_states = TTLCache(maxsize=10000, ttl=3600)
user_cache = TTLCache(maxsize=1000, ttl=30)

# ✅ منوی اصلی با دکمه ماموریت‌ها
MAIN_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"), InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu")],
    [InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"), InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu")],
    [InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="mission:menu"), InlineKeyboardButton("💸 انتقال زرکوین", callback_data="transfer:start")],
    [InlineKeyboardButton("📚 راهنما", callback_data="help:menu")],
])

BACK_MAIN_KB = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]])
BACK_GAMES_KB = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")]])
BANK_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 واریز", callback_data="bank:deposit"), InlineKeyboardButton("🏧 برداشت", callback_data="bank:withdraw")],
    [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
])
GAMES_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game:rps"), InlineKeyboardButton("❌ دوز", callback_data="game:ttt")],
    [InlineKeyboardButton("🧠 کوییز", callback_data="game:quiz"), InlineKeyboardButton("⚽ پنالتی", callback_data="game:penalty")],
    [InlineKeyboardButton("🎰 کازینو", callback_data="game:casino")],
    [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
])

def fa_to_en(text: str) -> str:
    return (text or "").translate(str.maketrans(PERSIAN_DIGITS, EN_DIGITS))

def fmt(amount: int) -> str:
    return f"{int(amount):,}"

def parse_amount(text: str):
    cleaned = fa_to_en(text).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit(): return None
    v = int(cleaned)
    return v if v > 0 else None

def card_number_for(user_id: int) -> str:
    return f"6037{str(user_id).zfill(12)[-12:]}"

def format_card(card: str) -> str:
    if not card or len(card) != 16: return card or "-"
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
        if rid not in rooms: return rid

def find_user_room(user_id: int):
    for rid, room in rooms.items():
        if user_id in room.get("players", []) and room.get("status") in ("waiting", "playing"):
            return rid
    return None

def remember_owner(message, user_id: int):
    if message:
        menu_owners[(message.chat_id, message.message_id)] = user_id

def invalidate_cache(user_id):
    user_cache.pop(user_id, None)

def apply_commission(full_prize: int, rate: float) -> tuple[int, int]:
    commission = int(full_prize * rate)
    return full_prize - commission, commission

async def safe_answer(query, text=None, show_alert=False):
    try:
        await query.answer(text=text, show_alert=show_alert)
    except Exception:
        pass

async def safe_edit(query, text: str, reply_markup=None):
    try:
        if query.message:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
            return query.message
        else:
            return await query.from_user.send_message(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return query.message
        try:
            return await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception:
            return None
    except Exception:
        return None

def join_room_kb(room_id: str, game_key: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 ورود به بازی", callback_data=f"{game_key}:join:{room_id}")],
        [InlineKeyboardButton("❌ لغو", callback_data=f"room:cancel:{room_id}")],
    ])

def transfer_confirm_kb(user_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"tr:c:{user_id}"),
        InlineKeyboardButton("❌ انصراف", callback_data=f"tr:x:{user_id}"),
    ]])

# ═══════════ سیستم لول ═══════════
def calc_level(total_xp: int) -> tuple[int, int, int]:
    level = 1
    cum = 0
    while True:
        cost = (2 ** level) * 1000
        if total_xp >= cum + cost:
            cum += cost
            level += 1
        else:
            break
    xp_in_level = total_xp - cum
    xp_for_next = (2 ** level) * 1000
    return level, xp_in_level, xp_for_next

def format_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0: return "░" * length
    filled = min(length, int(current * length / total))
    return "▓" * filled + "░" * (length - filled)

# ═══════════ نوتیفیکیشن ماموریت ═══════════
async def notify_mission(bot_or_context, chat_id: int, result: dict | None):
    if not result or not result.get("completed"):
        return
    
    bot = bot_or_context.bot if hasattr(bot_or_context, "bot") else bot_or_context
    
    msg = "🎯 <b>ماموریت کامل شد!</b>\n━━━━━━━━━━━━━━━━━━\n"
    for m in result["completed"]:
        msg += f"✅ {m['desc']}\n   <i>+{m['xp']} XP</i>\n"
    
    total = result.get("total_xp", 0)
    msg += f"\n✨ مجموع: <b>+{total} XP</b>"
    
    if result.get("leveled_up"):
        msg += f"\n\n🎉 <b>لول آپ!</b>\nبه سطح <b>{result['new_level']}</b> رسیدی! 🌟"
    
    try:
        await bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
    except Exception:
        pass
