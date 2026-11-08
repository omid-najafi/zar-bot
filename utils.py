import html
import secrets
import string
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from cachetools import TTLCache
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest
import config

logger = logging.getLogger("zarcoin")

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

# ✅ کش بررسی عضویت — فقط برای نتایج مثبت
_membership_cache = TTLCache(maxsize=1000, ttl=600)
_logged_groups = set()

# ═══════════ منوی اصلی — ایموجی‌های اصلی ═══════════
MAIN_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"), InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu")],
    [InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"), InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu")],
    [InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="mission:menu"), InlineKeyboardButton("💸 انتقال", callback_data="transfer:start")],
    [InlineKeyboardButton("🎭 کاباره زر", callback_data="kabareh:menu")],
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
        if "Message is not modified" in str(e): return query.message
        try:
            return await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception: return None
    except Exception: return None

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

async def notify_mission(bot_or_context, chat_id: int, result: dict | None):
    if not result or not result.get("completed"): return
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


# ═══════════════════════════════════════════
# ═══════════ جوین اجباری (اصلاح‌شده) ═══════════
# ═══════════════════════════════════════════

def get_join_keyboard():
    buttons = []
    for ch in config.REQUIRED_CHANNELS:
        buttons.append([InlineKeyboardButton(f"📢 {ch['name']}", url=ch["url"])])
    if config.REQUIRED_GROUP and config.REQUIRED_GROUP.get("url"):
        buttons.append([InlineKeyboardButton(f"💬 {config.REQUIRED_GROUP['name']}", url=config.REQUIRED_GROUP["url"])])
    buttons.append([InlineKeyboardButton("✅ عضو شدم، بررسی کن!", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)


def get_join_text(missing: list = None) -> str:
    text = "🔒 <b>برای استفاده از ربات، ابتدا باید عضو کانال‌ها و گروه زیر بشی:</b>\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"
    if missing:
        text += "❌ <b>هنوز عضو این‌ها نشدی:</b>\n"
        for name in missing:
            text += f"• {name}\n"
        text += "\n"
    for ch in config.REQUIRED_CHANNELS:
        text += f"📢 {ch['name']}\n"
    if config.REQUIRED_GROUP and config.REQUIRED_GROUP.get("url"):
        text += f"💬 {config.REQUIRED_GROUP['name']}\n"
    text += "\n👇 روی دکمه‌های زیر بزن و عضو شو، بعد دکمه «✅ عضو شدم» رو بزن:"
    return text


async def check_membership_quiet(bot, user_id: int, force: bool = False) -> tuple[bool, list]:
    """
    ✅ اصلاح‌شده: فقط نتایج مثبت کش می‌شن.
    کاربر بعد از عضویت فوراً شناسایی میشه.
    """
    if not force and user_id in _membership_cache:
        cached = _membership_cache[user_id]
        if cached[0]:  # فقط True کش میشه
            return cached

    missing = []

    for ch in config.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            status = getattr(member, "status", None)
            if status in ("left", "kicked"):
                missing.append(ch["name"])
        except Exception as e:
            logger.warning(f"⚠️ چک عضویت {ch['name']} ناموفق: {e}")

    if config.REQUIRED_GROUP:
        group_id = config.REQUIRED_GROUP.get("id")
        if group_id:
            try:
                member = await bot.get_chat_member(chat_id=group_id, user_id=user_id)
                status = getattr(member, "status", None)
                if status in ("left", "kicked"):
                    missing.append(config.REQUIRED_GROUP["name"])
            except Exception as e:
                logger.warning(f"⚠️ چک عضویت گروه ناموفق: {e}")

    result = (len(missing) == 0, missing)

    # ✅ فقط نتایج مثبت کش می‌شن
    if result[0]:
        _membership_cache[user_id] = result
    else:
        _membership_cache.pop(user_id, None)

    return result


async def check_membership_force(bot, user_id: int) -> tuple[bool, list]:
    return await check_membership_quiet(bot, user_id, force=True)


async def verify_membership(update, context) -> bool:
    user_id = update.effective_user.id
    bot = context.bot

    is_joined, missing = await check_membership_quiet(bot, user_id)
    if is_joined:
        return True

    text = get_join_text(missing)
    kb = get_join_keyboard()

    try:
        if update.callback_query:
            await update.callback_query.answer("❌ هنوز عضو نشدی!", show_alert=True)
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        logger.warning(f"ارسال پیام جوین ناموفق: {e}")

    return False


def log_group_chat_id(update):
    if not update.effective_chat: return
    if update.effective_chat.type not in ("group", "supergroup"): return
    chat_id = update.effective_chat.id
    if chat_id in _logged_groups: return
    _logged_groups.add(chat_id)
    title = update.effective_chat.title or "بدون نام"
    username = update.effective_chat.username or "ندارد"
    logger.warning(
        f"\n{'='*60}\n"
        f"💬 گروه شناسایی شد!\n"
        f"   Chat ID:  {chat_id}\n"
        f"   Title:    {title}\n"
        f"   Username: @{username}\n\n"
        f"   برای فعال‌سازی جوین اجباری این گروه، در config.py:\n"
        f"   REQUIRED_GROUP['id'] = {chat_id}\n"
        f"{'='*60}\n"
    )
