import html
import secrets
import string
import asyncio
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest

TEHRAN = ZoneInfo("Asia/Tehran")
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

# دیکشنری‌های اشتراکی
rooms: dict[str, dict] = {}
pending_transfers: dict[int, dict] = {}
penalty_games: dict[int, dict] = {}
casino_pending: dict[int, dict] = {}
daily_lock = asyncio.Lock()

class LRUCache:
    def __init__(self, capacity=5000):
        self.cache = OrderedDict()
        self.capacity = capacity
    def get(self, key):
        if key not in self.cache: return None
        self.cache.move_to_end(key)
        return self.cache[key]
    def set(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
    def pop(self, key):
        return self.cache.pop(key, None)
    def __contains__(self, key):
        return key in self.cache

menu_owners = LRUCache(10000)
user_states = LRUCache(10000)
user_cache: dict[int, tuple[dict, float]] = {}

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
        menu_owners.set((message.chat_id, message.message_id), user_id)

def invalidate_cache(user_id):
    user_cache.pop(user_id, None)

def apply_commission(full_prize: int, rate: float) -> tuple[int, int]:
    commission = int(full_prize * rate)
    return full_prize - commission, commission

async def safe_edit(query, text: str, reply_markup=None):
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        return query.message
    except BadRequest as e:
        if "Message is not modified" in str(e): return query.message
        return await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)

# کیبوردهای عمومی
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"), InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu")],
        [InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"), InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu")],
        [InlineKeyboardButton("💸 انتقال زرکوین", callback_data="transfer:start")],
        [InlineKeyboardButton("📚 راهنما", callback_data="help:menu")],
    ])

def back_main_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]])
def back_games_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")]])
def bank_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 واریز", callback_data="bank:deposit"), InlineKeyboardButton("🏧 برداشت", callback_data="bank:withdraw")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

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
