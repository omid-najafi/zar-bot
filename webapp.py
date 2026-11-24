# -*- coding: utf-8 -*-
"""
🎲 سرور مینی‌اپ کازینو زر + پنل مدیریت
─────────────────────────────────────────────
- مینی‌اپ: بازی‌ها از games/*.py import می‌شوند (casino, rps, ttt, quiz, penalty)
- پنل مدیریت: http(s)://دامنه/admin  (ورود با نام کاربری/رمز — پیش‌فرض admin / admin)
    • جستجوی کاربر با آیدی عددی / یوزرنیم / نام / شماره کارت
    • کم و زیاد کردن پول، بانک، XP، لول، ملک، کارگر، آیتم‌های بازار سیاه
    • ساخت کد هدیه با محدودیت (تعداد، لول، تاریخ انقضا)
- ربات: «هدیه زر کد» برای فعال‌سازی کد هدیه
- منوی اصلی: دکمه «🎮 بازی‌ها» حذف و «🎰 کازینو» (باز کردن مینی‌اپ) جایگزین شد
- بازار سیاه: از هر سیستم دفاعی فقط ۱ عدد | هر وسیله شلیک بعد از شلیک ۱ ساعت خنک می‌شود
"""
import asyncio
import base64
import decimal
import hashlib
import hmac
import json
import logging
import html
import math
import os
import random
import re
import secrets
import time
import urllib.parse
from pathlib import Path

import aiomysql
from aiohttp import web

import config
import db
import redis_client
from games import casino, rps, ttt, quiz, penalty

try:
    import utils as _utils
except Exception:  # pragma: no cover
    _utils = None

logger = logging.getLogger("zarcoin.webapp")

# ═══════════ مسیرها ═══════════
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MINIAPP_HTML = TEMPLATES_DIR / "miniapp.html"
ADMIN_HTML = TEMPLATES_DIR / "admin.html"

# ═══════════ تنظیمات ═══════════
COMMISSION_RATE = float(getattr(config, "MINIAPP_COMMISSION_RATE", 0.05))
MATCH_TIMEOUT = int(getattr(config, "MATCHMAKING_TIMEOUT", 60))
TURN_TIMEOUT = int(getattr(config, "MINIAPP_TURN_TIMEOUT", 45))
MAX_BET = int(os.getenv("MINIAPP_MAX_BET") or getattr(config, "MINIAPP_MAX_BET", 30_000_000))  # حداکثر شرط کازینو
FINISHED_GAME_TTL = 180
SOLO_SESSION_TTL = 3600
SWEEP_INTERVAL = 3
LAUNCH_COOLDOWN = int(getattr(config, "LAUNCH_COOLDOWN_SECONDS", 3600))  # خنک شدن هر وسیله شلیک
MAX_LEVEL = 50
XP_MIN = int(getattr(config, "MINIAPP_XP_MIN", 15))              # حداقل XP برد
XP_MAX = int(getattr(config, "MINIAPP_XP_MAX", 2500))            # حداکثر XP برد
XP_DIVISOR = int(getattr(config, "MINIAPP_XP_DIVISOR", 10000))  # XP برد = مبلغ شرط ÷ این عدد
MIN_BET = int(os.getenv("MINIAPP_MIN_BET") or getattr(config, "MINIAPP_MIN_BET", 10_000))  # حداقل شرط کازینو
LAUNCHER_MAX = int(os.getenv("LAUNCHER_MAX_PER_ITEM") or 3)  # از هر وسیله شلیک حداکثر ۳ عدد
LAUNCHER_MAX_VIP = 6                                          # سقف وسیله شلیک برای VIP
DEFENSE_MAX = 1                                               # از هر سیستم دفاعی فقط ۱ عدد
BANK_LOCK_SECONDS = int(getattr(config, "BANK_LOCK_SECONDS", 5 * 3600))  # قفل برداشت بعد از واریز (۵ ساعت)
WH_MAX_LEVEL = 10                                             # حداکثر لول انبار
_banned: set = set()                                          # کاربران بن‌شده (کش حافظه)
_bot_off = False                                              # حالت خاموشی بات (از پنل مدیریت)
_admins: set = set()                                          # ادمین‌های افزوده‌شده از پنل (کش حافظه)

# بخش‌های قابل خاموش/روشن کردن از پنل مدیریت
SECTIONS = [
    ("bank", "🏦 بانک"), ("property", "🏠 ملک‌ها"), ("worker", "👷 کارگرها"), ("casino", "🎰 کازینو"),
    ("missions", "🎯 ماموریت‌ها"), ("transfer", "💸 انتقال"), ("kabareh", "🎭 کاباره زر"),
    ("leaderboard", "🏆 لیدربورد"), ("blackmarket", "💀 بازار سیاه"), ("shop", "💎 خرید کوین و لول"),
    ("gift", "🎁 کد هدیه"), ("help", "📚 راهنما"),
]
_settings_cache: dict = {}
_settings_at = 0.0
_settings_loaded = False

ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME") or getattr(config, "ADMIN_USERNAME", "") or "admin").strip()
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or getattr(config, "ADMIN_PASSWORD", "") or "admin").strip()

# ═══════════ لیست بازی‌ها ═══════════
_DEFAULT_GAMES = {
    # ─── تک‌نفره ───
    "wheel": {"name": "چرخ شانس", "emoji": "🎡", "type": "1p", "min_bet": 1_000, "desc": "چرخ را بچرخان — تا ۵ برابر جایزه"},
    "crash": {"name": "موشک", "emoji": "🚀", "type": "1p", "min_bet": 1_000, "desc": "ضریب هدف را انتخاب کن؛ قبل از انفجار برس"},
    "mines": {"name": "مین‌یاب", "emoji": "💣", "type": "1p", "min_bet": 1_000, "desc": "خانه‌های امن را باز کن و به‌موقع برداشت کن"},
    "hilo": {"name": "بالا پایین", "emoji": "🎴", "type": "1p", "min_bet": 1_000, "desc": "کارت بعدی بالاتر است یا پایین‌تر؟"},
    "roulette": {"name": "رولت", "emoji": "🎯", "type": "1p", "min_bet": 1_000, "desc": "رنگ، زوج/فرد، دسته یا عدد — تا ۳۶ برابر"},
    "card": {"name": "کارت شانس", "emoji": "🃏", "type": "1p", "min_bet": 1_000, "desc": "رنگ (×۱٫۹) یا خال (×۳٫۸) کارت را حدس بزن"},
    "penalty": {"name": "پنالتی", "emoji": "⚽", "type": "1p", "min_bet": 1_000, "desc": "یک گوشه را انتخاب کن و دروازه‌بان را فریب بده"},
    "coin": {"name": "شیر یا خط", "emoji": "🪙", "type": "1p", "min_bet": 1_000, "desc": "۵۰/۵۰ — برد ۱٫۹ برابر"},
    # ─── دونفره ───
    "holdem": {"name": "پوکر تگزاس هولدم", "emoji": "♠️", "type": "2p", "min_bet": 10_000, "desc": "هدز‌آپ با رِیز آزاد و آل‌این"},
    "hokm": {"name": "حکم", "emoji": "👑", "type": "2p", "min_bet": 10_000, "desc": "حکم دونفره — هر کس ۷ دست ببرد"},
    "blackjack": {"name": "بلک‌جک", "emoji": "🂡", "type": "2p", "min_bet": 5_000, "desc": "نزدیک‌تر به ۲۱ بدون سوختن"},
    "quiz": {"name": "کوییز", "emoji": "🧠", "type": "2p", "min_bet": 1_000, "desc": "۵ سوال هم‌زمان — جواب درست بیشتر برنده"},
    "connect4": {"name": "چهار در یک ردیف", "emoji": "🔴", "type": "2p", "min_bet": 5_000, "desc": "اولین نفری که ۴ مهره پشت‌سرهم بچیند"},
    "rps": {"name": "سنگ کاغذ قیچی", "emoji": "✊", "type": "2p", "min_bet": 1_000, "desc": "سه دست — هر کس ۲ دست ببرد"},
    "ttt": {"name": "دوز", "emoji": "⭕", "type": "2p", "min_bet": 1_000, "desc": "سه در یک خط — کلاسیک دونفره"},
    "othello": {"name": "اتللو", "emoji": "⚫", "type": "2p", "min_bet": 5_000, "desc": "مهره‌های حریف را محاصره و برعکس کن"},
}


def _build_games() -> dict:
    games = {}
    for key, g in _DEFAULT_GAMES.items():
        merged = dict(g)
        merged["min_bet"] = MIN_BET
        merged["max_bet"] = max(MAX_BET, MIN_BET)
        games[key] = merged
    return games


GAMES = _build_games()
MINIAPP_GAMES = GAMES

GAME_IMPL = {}
for _m in (casino, rps, ttt, quiz):
    GAME_IMPL.update(_m.MINIAPP_GAMES)
SOLO_INSTANT = dict(casino.SOLO_INSTANT)
SOLO_INSTANT.update(penalty.SOLO_INSTANT)
_MISSION_KEYS = {"rps": "rps", "ttt": "ttt", "quiz": "quiz", "penalty": "penalty"}

# ═══════════ حافظه ═══════════
_match_queues: dict[str, dict[int, "MatchEntry"]] = {}
_waiting: dict[int, dict] = {}
_active_games: dict[str, "GameState"] = {}
_user_games: dict[int, str] = {}
_solo_sessions: dict[int, dict] = {}
_user_locks: dict[int, asyncio.Lock] = {}
_matchmaking_lock = asyncio.Lock()
_bg_tasks: set = set()


def _ulock(uid: int) -> asyncio.Lock:
    lk = _user_locks.get(uid)
    if lk is None:
        lk = _user_locks[uid] = asyncio.Lock()
    return lk


class MatchEntry:
    __slots__ = ("user_id", "name", "balance", "bet", "joined_at", "avatar")

    def __init__(self, user_id, name, balance, bet, avatar=""):
        self.user_id, self.name, self.balance, self.bet, self.avatar = user_id, name, balance, bet, avatar
        self.joined_at = time.time()


class GameState:
    """حالت یک بازی دونفره — منطق بازی در games/*.py است"""
    __slots__ = ("game_id", "game_key", "players", "bet", "contrib", "data", "waiting", "deadline", "created_at",
                 "updated_at", "finished", "finished_at", "winner", "reason", "payout", "lock", "version", "outcome")

    def __init__(self, game_id, game_key, players, bet):
        now = time.time()
        self.game_id, self.game_key, self.players, self.bet = game_id, game_key, players, bet
        self.contrib = {p["user_id"]: bet for p in players}
        self.data, self.waiting = {}, set()
        self.deadline = now + TURN_TIMEOUT
        self.created_at = self.updated_at = now
        self.finished, self.finished_at = False, 0.0
        self.winner, self.reason, self.payout = None, "", 0
        self.lock = asyncio.Lock()
        self.version = 0
        self.outcome = None

    @property
    def pot(self) -> int:
        return sum(self.contrib.values())

    def uids(self) -> list:
        return [p["user_id"] for p in self.players]

    def opp(self, uid: int) -> int:
        a, b = self.uids()
        return b if uid == a else a

    def name(self, uid: int) -> str:
        return next((p["name"] for p in self.players if p["user_id"] == uid), "بازیکن")

    def finish(self, winner, reason: str):
        """توسط ماژول بازی صدا زده می‌شود — پرداخت در webapp انجام می‌شود"""
        if self.outcome is None and not self.finished:
            self.outcome = (winner, reason)
            self.waiting = set()

    def touch(self):
        now = time.time()
        self.updated_at, self.deadline = now, now + TURN_TIMEOUT
        self.version += 1


# ═══════════ ابزار ═══════════
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _to_int(v, default=None):
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v == v and abs(v) < 1e15 else default
    if isinstance(v, str):
        s = v.translate(_FA_DIGITS).replace(",", "").replace("،", "").replace("_", "").strip()
        if 0 < len(s) <= 16 and s.lstrip("-").isdigit():
            return int(s)
    return default


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def _json_default(o):
    if isinstance(o, decimal.Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, (set, frozenset)):
        return list(o)
    return str(o)


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False, default=_json_default))


def _err(msg: str, status: int = 400, code: str = "error", **extra) -> web.Response:
    payload = {"ok": False, "error": msg, "code": code}
    payload.update(extra)
    return _json(payload, status)


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _balance(uid: int) -> int:
    try:
        u = await db.get_user(uid)
        return int(u["balance"]) if u else 0
    except Exception:
        return 0


def _uname(user: dict) -> str:
    return ((user.get("first_name") or user.get("username") or "بازیکن").strip()[:32]) or "بازیکن"


def _redis_on() -> bool:
    try:
        return bool(redis_client.is_redis_available())
    except Exception:
        return False


def _spawn(coro):
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


def _invalidate(uid: int):
    if not _utils:
        return
    for fn in ("invalidate_cache", "invalidate_assets_cache"):
        f = getattr(_utils, fn, None)
        if f:
            try:
                f(uid)
            except Exception:
                pass


def _calc_level(xp: int) -> int:
    if _utils and hasattr(_utils, "calc_level"):
        return _utils.calc_level(int(xp))[0]
    level, cum = 1, 0
    while xp >= cum + (2 ** level) * 1000:
        cum += (2 ** level) * 1000
        level += 1
    return level


def _xp_for_level(level: int) -> int:
    return sum((2 ** lv) * 1000 for lv in range(1, max(1, level)))


def _win_xp(bet: int) -> int:
    """XP برد بر اساس مبلغ شرط — فقط با برد داده می‌شود (حداقل XP_MIN، حداکثر XP_MAX)"""
    try:
        return max(XP_MIN, min(XP_MAX, int(bet) // XP_DIVISOR))
    except Exception:
        return XP_MIN


async def _track_async(uid: int, game_key: str, solo: bool, won: bool, bet: int = 0):
    try:
        mk = _MISSION_KEYS.get(game_key) or ("casino" if solo else None)
        xp = _win_xp(bet) if won else 0  # XP فقط با برد و بر اساس مبلغ شرط
        await db.progress_mission(uid, "play_any_game", 1, base_xp=xp)
        if mk:
            await db.progress_mission(uid, f"play_{mk}", 1, base_xp=0)
        if won:
            await db.progress_mission(uid, "win_any_game", 1, base_xp=0)
            if mk:
                await db.progress_mission(uid, f"win_{mk}", 1, base_xp=0)
    except Exception as e:
        logger.debug(f"progress_mission ناموفق: {e}")


def _track(uid: int, game_key: str, solo: bool, won: bool, bet: int = 0):
    _spawn(_track_async(uid, game_key, solo, won, bet))


async def _take_bet(uid: int, game_key: str, bet) -> str | None:
    g = GAMES.get(game_key)
    if not g:
        return "بازی نامعتبر است"
    s = await _get_settings()
    if s.get(f"game_off:{game_key}") == "1":
        return "این بازی فعلاً غیرفعال است"
    if not isinstance(bet, int) or bet <= 0:
        return "مبلغ شرط نامعتبر است"
    if bet < g["min_bet"]:
        return f"حداقل شرط {_fmt(g['min_bet'])} است"
    if bet > g["max_bet"]:
        return f"حداکثر شرط {_fmt(g['max_bet'])} است"
    if not await db.deduct_balance(uid, bet):
        return "موجودی کافی نیست"
    return None


# ═══════════ دیتابیس (جداول جدید) ═══════════
_tables_ready = False
_tables_lock = asyncio.Lock()


async def _ensure_tables():
    global _tables_ready
    if _tables_ready:
        return
    async with _tables_lock:
        if _tables_ready:
            return
        if getattr(db, "db_pool", None) is None:
            raise RuntimeError("db pool آماده نیست")
        async with db.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS gift_codes (code VARCHAR(64) PRIMARY KEY, rewards TEXT NOT NULL, "
                    "max_uses INT NOT NULL DEFAULT 0, used_count INT NOT NULL DEFAULT 0, min_level INT NOT NULL DEFAULT 0, "
                    "expires_at DOUBLE NULL, active TINYINT NOT NULL DEFAULT 1, note VARCHAR(255) NULL, "
                    "created_at DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS gift_redemptions (id INT PRIMARY KEY AUTO_INCREMENT, code VARCHAR(64) NOT NULL, "
                    "user_id BIGINT NOT NULL, redeemed_at DOUBLE NOT NULL, UNIQUE KEY uq_code_user (code, user_id), "
                    "INDEX idx_user (user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS shop_products (id INT PRIMARY KEY AUTO_INCREMENT, title VARCHAR(64) NOT NULL, "
                    "description TEXT NULL, rewards TEXT NOT NULL, price_toman BIGINT NOT NULL DEFAULT 0, "
                    "price_stars INT NOT NULL DEFAULT 0, active TINYINT NOT NULL DEFAULT 1, sort INT NOT NULL DEFAULT 0, "
                    "created_at DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS shop_orders (id INT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, "
                    "product_id INT NOT NULL, title VARCHAR(64) NOT NULL, rewards TEXT NOT NULL, method VARCHAR(16) NOT NULL, "
                    "amount BIGINT NOT NULL, status VARCHAR(20) NOT NULL, receipt_file_id VARCHAR(255) NULL, "
                    "charge_id VARCHAR(255) NULL, created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, "
                    "INDEX idx_user_status (user_id, status)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS zar_settings (k VARCHAR(64) PRIMARY KEY, v TEXT NULL) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS banned_users (user_id BIGINT PRIMARY KEY, reason VARCHAR(255) NULL, "
                    "banned_at DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS bot_admins (user_id BIGINT PRIMARY KEY, note VARCHAR(255) NULL, "
                    "added_at DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                try:
                    await cur.execute("ALTER TABLE inventory ADD COLUMN last_used DOUBLE NULL DEFAULT NULL")
                except Exception:
                    pass  # ستون از قبل وجود دارد
                for _col, _ddl in (("warehouse_level", "INT NOT NULL DEFAULT 1"),
                                   ("vip_until", "DOUBLE NULL DEFAULT NULL"),
                                   ("last_bank_deposit", "DOUBLE NULL DEFAULT NULL")):
                    try:
                        await cur.execute(f"ALTER TABLE users ADD COLUMN {_col} {_ddl}")
                    except Exception:
                        pass  # ستون از قبل وجود دارد
                # محصولات پیش‌فرض VIP (اگر نبودند ساخته می‌شوند)
                for _title, _days, _price, _desc in (
                    ("👑 VIP یک‌ماهه", 30, 80_000, "اشتراک VIP یک ماهه — تا ۶ وسیله شلیک، +۵ ظرفیت انبار، +۱۰٪ سود ملک و کارگر، سود بانک ۵٪"),
                    ("👑 VIP سه‌ماهه", 90, 220_000, "اشتراک VIP سه ماهه — تا ۶ وسیله شلیک، +۵ ظرفیت انبار، +۱۰٪ سود ملک و کارگر، سود بانک ۵٪"),
                    ("👑 VIP شش‌ماهه", 180, 450_000, "اشتراک VIP شش ماهه — تا ۶ وسیله شلیک، +۵ ظرفیت انبار، +۱۰٪ سود ملک و کارگر، سود بانک ۵٪"),
                ):
                    await cur.execute("SELECT id FROM shop_products WHERE title=%s", (_title,))
                    if not await cur.fetchone():
                        await cur.execute(
                            "INSERT INTO shop_products (title, description, rewards, price_toman, price_stars, active, sort, created_at) "
                            "VALUES (%s,%s,%s,%s,0,1,0,%s)",
                            (_title, _desc, json.dumps({"vip_days": _days}, ensure_ascii=False), _price, time.time()))
            await conn.commit()
        _tables_ready = True
        logger.info("✅ جداول کد هدیه / خنک‌شدن لانچر آماده است")


async def _fetch(sql: str, args=(), one: bool = False):
    async with db.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            rows = await (cur.fetchone() if one else cur.fetchall())
        await conn.commit()
    return rows


async def _exec(sql: str, args=()) -> int:
    async with db.db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            n = cur.rowcount
        await conn.commit()
    return n


async def _tx(fn):
    async with db.db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                res = await fn(cur)
            await conn.commit()
            return res
        except Exception:
            await conn.rollback()
            raise


def _now_iso() -> str:
    if _utils and hasattr(_utils, "now_iso"):
        return _utils.now_iso()
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _bm_items() -> dict:
    return getattr(config, "BLACKMARKET_ITEMS", {}) or {}


def _defense_keys() -> set:
    return {k for k, v in _bm_items().items() if v.get("type") == "defense"}


def _item_cap(key: str, vip: bool = False) -> int:
    """سقف تعداد مجاز یک آیتم بازار سیاه (۰ = نامحدود) — مهمات با ظرفیت انبار محدود می‌شود"""
    t = _bm_items().get(key, {}).get("type")
    if t == "defense":
        return DEFENSE_MAX
    if t == "launcher":
        return LAUNCHER_MAX_VIP if vip else LAUNCHER_MAX
    return 0


def _wh_capacity(level: int, vip: bool = False) -> int:
    """ظرفیت هر مهمات در انبار: ۲ × لول (+۵ برای VIP)"""
    return 2 * max(1, min(WH_MAX_LEVEL, int(level))) + (5 if vip else 0)


def _wh_upgrade_cost(level: int) -> int:
    """هزینه ارتقای انبار از لول فعلی: ۲^لول × ۱٬۰۰۰٬۰۰۰"""
    return (2 ** max(1, int(level))) * 1_000_000


async def _wh_level(uid: int) -> int:
    try:
        r = await _fetch("SELECT warehouse_level FROM users WHERE user_id=%s", (uid,), one=True)
        return max(1, min(WH_MAX_LEVEL, int(r["warehouse_level"] or 1))) if r else 1
    except Exception:
        return 1


async def _vip_until(uid: int) -> float:
    try:
        r = await _fetch("SELECT vip_until FROM users WHERE user_id=%s", (uid,), one=True)
        return float(r["vip_until"]) if r and r["vip_until"] else 0.0
    except Exception:
        return 0.0


async def _is_vip(uid: int) -> bool:
    return await _vip_until(uid) > time.time()


GRANT_KINDS = ("coins", "bank", "xp", "levels", "property", "worker", "item", "warehouse", "vip_days")


async def _grant(cur, uid: int, kind: str, key: str, n: int) -> int:
    """افزودن (داخل تراکنش). خروجی: مقدار واقعاً اعمال‌شده"""
    if n <= 0:
        return 0
    if kind == "coins":
        await cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (n, uid))
        return n if cur.rowcount else 0
    if kind == "bank":
        await cur.execute("UPDATE users SET bank_balance = bank_balance + %s WHERE user_id=%s", (n, uid))
        return n if cur.rowcount else 0
    if kind in ("xp", "levels"):
        await cur.execute("SELECT total_xp FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        xp = int(row["total_xp"] or 0)
        if kind == "xp":
            new_xp = xp + n
        else:
            new_xp = max(xp, _xp_for_level(min(MAX_LEVEL, _calc_level(xp) + n)))
        await cur.execute("UPDATE users SET total_xp=%s, level=%s WHERE user_id=%s", (new_xp, _calc_level(new_xp), uid))
        return n
    if kind in ("property", "worker"):
        store = config.PROPERTIES if kind == "property" else config.WORKERS
        info = store.get(key)
        if not info:
            return 0
        await cur.execute("SELECT COUNT(*) AS c FROM assets WHERE user_id=%s AND asset_type=%s AND asset_key=%s",
                          (uid, kind, key))
        have = int((await cur.fetchone())["c"])
        add = max(0, min(n, int(getattr(config, "MAX_PER_KEY", 5)) - have))
        for _ in range(add):
            await cur.execute(
                "INSERT INTO assets (user_id, asset_type, asset_key, purchase_price, daily_income, purchased_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)", (uid, kind, key, int(info["price"]), int(info["income"]), _now_iso()))
        return add
    if kind == "item":
        info = _bm_items().get(key)
        if not info:
            return 0
        add = min(n, 100)
        await cur.execute("SELECT vip_until, warehouse_level FROM users WHERE user_id=%s", (uid,))
        ur = await cur.fetchone()
        vip = bool(ur and ur["vip_until"] and float(ur["vip_until"]) > time.time())
        if info.get("type") == "projectile":
            cap = _wh_capacity(int(ur["warehouse_level"] or 1) if ur else 1, vip)
        else:
            cap = _item_cap(key, vip)
        if cap:
            await cur.execute("SELECT COUNT(*) AS c FROM inventory WHERE user_id=%s AND item_key=%s", (uid, key))
            add = max(0, min(n, cap - int((await cur.fetchone())["c"])))
        for _ in range(add):
            await cur.execute("INSERT INTO inventory (user_id, item_key, purchased_at) VALUES (%s,%s,%s)",
                              (uid, key, _now_iso()))
        return add
    if kind == "warehouse":
        await cur.execute("SELECT warehouse_level FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        cur_lvl = int(row["warehouse_level"] or 1)
        new_lvl = min(WH_MAX_LEVEL, cur_lvl + n)
        await cur.execute("UPDATE users SET warehouse_level=%s WHERE user_id=%s", (new_lvl, uid))
        return new_lvl - cur_lvl
    if kind == "vip_days":
        await cur.execute("SELECT vip_until FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        new_until = max(time.time(), float(row["vip_until"] or 0)) + n * 86400
        await cur.execute("UPDATE users SET vip_until=%s WHERE user_id=%s", (new_until, uid))
        return n
    return 0


async def _revoke(cur, uid: int, kind: str, key: str, n: int) -> int:
    """کم کردن (داخل تراکنش). خروجی: مقدار واقعاً کم‌شده"""
    if n <= 0:
        return 0
    if kind in ("coins", "bank"):
        col = "balance" if kind == "coins" else "bank_balance"
        await cur.execute(f"SELECT {col} AS v FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        take = min(n, int(row["v"] or 0))
        await cur.execute(f"UPDATE users SET {col} = {col} - %s WHERE user_id=%s", (take, uid))
        return take
    if kind in ("xp", "levels"):
        await cur.execute("SELECT total_xp FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        xp = int(row["total_xp"] or 0)
        new_xp = max(0, xp - n) if kind == "xp" else _xp_for_level(max(1, _calc_level(xp) - n))
        new_xp = min(new_xp, xp)
        await cur.execute("UPDATE users SET total_xp=%s, level=%s WHERE user_id=%s", (new_xp, _calc_level(new_xp), uid))
        return n
    if kind in ("property", "worker"):
        await cur.execute("DELETE FROM assets WHERE user_id=%s AND asset_type=%s AND asset_key=%s ORDER BY id DESC LIMIT %s",
                          (uid, kind, key, n))
        return cur.rowcount
    if kind == "item":
        await cur.execute("DELETE FROM inventory WHERE user_id=%s AND item_key=%s ORDER BY id DESC LIMIT %s", (uid, key, n))
        return cur.rowcount
    if kind == "warehouse":
        await cur.execute("SELECT warehouse_level FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        cur_lvl = int(row["warehouse_level"] or 1)
        new_lvl = max(1, cur_lvl - n)
        await cur.execute("UPDATE users SET warehouse_level=%s WHERE user_id=%s", (new_lvl, uid))
        return cur_lvl - new_lvl
    if kind == "vip_days":
        await cur.execute("SELECT vip_until FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        row = await cur.fetchone()
        if not row:
            return 0
        new_until = max(0.0, float(row["vip_until"] or 0) - n * 86400)
        await cur.execute("UPDATE users SET vip_until=%s WHERE user_id=%s", (new_until, uid))
        return n
    return 0


def _kind_label(kind: str, key: str) -> str:
    if kind == "coins":
        return "💰 زرکوین"
    if kind == "bank":
        return "🏦 موجودی بانک"
    if kind == "xp":
        return "✨ XP"
    if kind == "levels":
        return "⭐ لول"
    if kind == "warehouse":
        return "🏭 لول انبار"
    if kind == "vip_days":
        return "👑 روز اشتراک VIP"
    store = {"property": config.PROPERTIES, "worker": config.WORKERS, "item": _bm_items()}.get(kind, {})
    info = store.get(key, {})
    return f"{info.get('emoji', '•')} {info.get('name', key)}"


# ═══════════ کد هدیه ═══════════
def _norm_code(s) -> str:
    s = str(s or "").translate(_FA_DIGITS).strip().upper()
    return re.sub(r"[^\w\-]", "", s)[:64]


def _rewards_list(rewards: dict) -> list:
    """تبدیل rewards ذخیره‌شده به لیست (kind, key, n)"""
    out = []
    for kind in ("coins", "bank", "xp", "levels"):
        n = _to_int(rewards.get(kind), 0) or 0
        if n > 0:
            out.append((kind, "", n))
    n = _to_int(rewards.get("vip_days"), 0) or 0
    if n > 0:
        out.append(("vip_days", "", n))
    for kind, field in (("property", "properties"), ("worker", "workers"), ("item", "items")):
        for key, n in (rewards.get(field) or {}).items():
            n = _to_int(n, 0) or 0
            if n > 0:
                out.append((kind, key, n))
    return out


def _rewards_text(items) -> str:
    return "\n".join(f"• {_kind_label(k, key)}: {_fmt(n)}" for k, key, n in items) or "—"


async def redeem_gift(user_id: int, code_raw: str) -> tuple[bool, str]:
    code = _norm_code(code_raw)
    if not code:
        return False, "❌ کد هدیه نامعتبر است."
    await _ensure_tables()
    now = time.time()

    async def run(cur):
        await cur.execute("SELECT * FROM gift_codes WHERE code=%s FOR UPDATE", (code,))
        gc = await cur.fetchone()
        if not gc or not gc["active"]:
            return False, "❌ این کد هدیه وجود ندارد یا غیرفعال است."
        if gc["expires_at"] and float(gc["expires_at"]) < now:
            return False, "⌛ مهلت استفاده از این کد تمام شده."
        if gc["max_uses"] and int(gc["used_count"]) >= int(gc["max_uses"]):
            return False, "😔 ظرفیت این کد هدیه تکمیل شده."
        await cur.execute("SELECT total_xp FROM users WHERE user_id=%s", (user_id,))
        u = await cur.fetchone()
        if not u:
            return False, "❌ اول ربات را /start کن."
        lvl = _calc_level(int(u["total_xp"] or 0))
        if int(gc["min_level"] or 0) > lvl:
            return False, f"🔒 این کد برای لول {gc['min_level']} به بالاست (لول تو: {lvl})."
        await cur.execute("SELECT 1 FROM gift_redemptions WHERE code=%s AND user_id=%s", (code, user_id))
        if await cur.fetchone():
            return False, "⚠️ قبلاً از این کد هدیه استفاده کرده‌ای."
        await cur.execute("INSERT INTO gift_redemptions (code, user_id, redeemed_at) VALUES (%s,%s,%s)", (code, user_id, now))
        await cur.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code=%s", (code,))
        try:
            rewards = json.loads(gc["rewards"] or "{}")
        except Exception:
            rewards = {}
        granted, skipped = [], []
        for kind, key, n in _rewards_list(rewards):
            done = await _grant(cur, user_id, kind, key, n)
            if done > 0:
                granted.append((kind, key, done))
            if done < n:
                skipped.append((kind, key, n - done))
        text = f"🎁 <b>کد هدیه فعال شد!</b>\n━━━━━━━━━━━━━━━━━━\n{_rewards_text(granted)}"
        if skipped:
            text += "\n\n⚠️ به‌خاطر سقف مجاز این موارد اضافه نشد:\n" + _rewards_text(skipped)
        return True, text

    try:
        ok, text = await _tx(run)
    except Exception:
        logger.exception("redeem_gift error")
        return False, "❌ خطا در فعال‌سازی کد — دوباره تلاش کن."
    if ok:
        _invalidate(user_id)
    return ok, text


# ═══════════ احراز هویت مینی‌اپ ═══════════
def validate_init_data(init_data_raw: str) -> dict | None:
    if not init_data_raw or not config.BOT_TOKEN:
        return None
    try:
        parsed = urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True)
    except Exception:
        return None
    pairs, received_hash = {}, None
    for k, v in parsed:
        if k == "hash":
            received_hash = v
        else:
            pairs[k] = v
    if not received_hash:
        return None
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        logger.warning("⚠️ initData نامعتبر — هش مطابقت ندارد")
        return None
    try:
        if pairs.get("auth_date") and time.time() - int(pairs["auth_date"]) > 86400:
            return None
        user = json.loads(pairs.get("user") or "null")
    except Exception:
        return None
    return user if isinstance(user, dict) else None


def validate_browser_token(token: str) -> int | None:
    if not token or "." not in token:
        return None
    try:
        raw_b64, sig = token.rsplit(".", 1)
        raw = base64.urlsafe_b64decode((raw_b64 + "=" * (-len(raw_b64) % 4)).encode())
        expected = hmac.new(config.BOT_TOKEN.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(raw)
        if payload.get("exp", 0) < time.time():
            return None
        return int(payload.get("uid", 0)) or None
    except Exception:
        return None


async def _get_user_for_request(request: web.Request) -> dict | None:
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data") or ""
    user_id, tg = None, None
    if init_data:
        tg = validate_init_data(init_data)
        if tg:
            user_id = tg.get("id")
    if not user_id:
        user_id = validate_browser_token(request.headers.get("X-Browser-Token") or request.query.get("token") or "")
    if not user_id:
        return None
    try:
        db_user = await db.get_user(int(user_id))
        if not db_user and tg:
            db_user = await db.ensure_user(type("U", (), {
                "id": int(user_id), "first_name": tg.get("first_name", ""), "last_name": tg.get("last_name", ""),
                "username": tg.get("username", ""), "language_code": tg.get("language_code", "fa"), "is_bot": False,
            })())
    except Exception as e:
        logger.exception(f"get/ensure user در مینی‌اپ ناموفق: {e}")
        return None
    if not db_user:
        return None
    user = dict(db_user)
    user["user_id"] = int(user_id)
    user["_banned"] = int(user_id) in _banned
    if tg and tg.get("first_name"):
        user["first_name"] = tg["first_name"]
    return user


def _auth(handler):
    async def wrapper(request: web.Request):
        user = await _get_user_for_request(request)
        if not user:
            return _err("احراز هویت ناموفق بود — مینی‌اپ را از داخل ربات باز کن", 401, "auth")
        if user.get("_banned"):
            return _err("🚫 شما از ربات محروم شده‌اید", 403, "banned")
        try:
            s = await _get_settings()
            if s.get("section_off:casino") == "1":
                return _err("🎰 کازینو فعلاً غیرفعال است", 403, "casino_off")
        except Exception:
            pass
        try:
            return await handler(request, user)
        except Exception as e:
            logger.exception(f"❌ خطای مینی‌اپ در {request.path}: {e}")
            return _err("خطای داخلی سرور — دوباره تلاش کن", 500, "server")
    return wrapper


# ═══════════ تک‌نفره ═══════════
def _solo_view(s, reveal=False):
    if not s:
        return None
    return casino.mines_view(s, reveal) if s["type"] == "mines" else casino.hilo_view(s, reveal)


@_auth
async def api_solo_instant(request, user):
    key = request.match_info.get("game", "")
    fn = SOLO_INSTANT.get(key)
    if not fn or GAMES.get(key, {}).get("type") != "1p":
        return _err("بازی نامعتبر است", 404)
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    async with _ulock(uid):
        try:
            res = fn(body)
        except ValueError as e:
            return _err(str(e))
        err = await _take_bet(uid, key, bet)
        if err:
            return _err(err)
        win = int(bet * float(res.get("mult") or 0))
        if win > 0:
            await db.add_balance(uid, win)
        _track(uid, key, True, win > bet, bet)
        out = {"ok": True}
        out.update(res)
        out.update({"win": win, "profit": win - bet, "balance": await _balance(uid)})
        return _json(out)


@_auth
async def api_solo_state(request, user):
    uid = user["user_id"]
    return _json({"ok": True, "session": _solo_view(_solo_sessions.get(uid)), "balance": await _balance(uid)})


async def _solo_begin(uid, key, bet, factory):
    if uid in _solo_sessions:
        return None, _err("یک بازی نیمه‌تمام داری — اول آن را تمام کن", code="active_session",
                          session=_solo_view(_solo_sessions[uid]))
    err = await _take_bet(uid, key, bet)
    if err:
        return None, _err(err)
    s = factory()
    s["created"] = time.time()
    _solo_sessions[uid] = s
    return s, None


async def _solo_payout(uid, s, amount, key):
    s["finished"] = True
    _solo_sessions.pop(uid, None)
    if amount > 0:
        await db.add_balance(uid, amount)
    _track(uid, key, True, amount > s["bet"], s["bet"])


@_auth
async def api_mines_start(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet, count = _to_int(body.get("bet")), _to_int(body.get("mines"), 3)
    if count not in casino.MINES_COUNTS:
        return _err("تعداد مین نامعتبر است")
    async with _ulock(uid):
        s, resp = await _solo_begin(uid, "mines", bet, lambda: casino.mines_start(bet, count))
        if resp:
            return resp
        return _json({"ok": True, "session": _solo_view(s), "balance": await _balance(uid)})


@_auth
async def api_mines_reveal(request, user):
    uid = user["user_id"]
    idx = _to_int((await _body(request)).get("idx"), -1)
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "mines":
            return _err("بازی مین‌یاب فعالی نداری", code="no_session")
        try:
            result = casino.mines_reveal(s, idx)
        except ValueError as e:
            return _err(str(e))
        win = 0
        if result == "lose":
            await _solo_payout(uid, s, 0, "mines")
        elif result == "win":
            win = casino.mines_payout(s)
            await _solo_payout(uid, s, win, "mines")
        return _json({"ok": True, "session": _solo_view(s, reveal=bool(result)), "result": result, "win": win,
                      "balance": await _balance(uid)})


@_auth
async def api_mines_cashout(request, user):
    uid = user["user_id"]
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "mines":
            return _err("بازی مین‌یاب فعالی نداری", code="no_session")
        if not s["revealed"]:
            return _err("حداقل یک خانه باز کن")
        win = casino.mines_payout(s)
        await _solo_payout(uid, s, win, "mines")
        return _json({"ok": True, "session": _solo_view(s, True), "result": "win", "win": win,
                      "balance": await _balance(uid)})


@_auth
async def api_hilo_start(request, user):
    uid = user["user_id"]
    bet = _to_int((await _body(request)).get("bet"))
    async with _ulock(uid):
        s, resp = await _solo_begin(uid, "hilo", bet, lambda: casino.hilo_start(bet))
        if resp:
            return resp
        return _json({"ok": True, "session": _solo_view(s), "balance": await _balance(uid)})


@_auth
async def api_hilo_guess(request, user):
    uid = user["user_id"]
    direction = (await _body(request)).get("dir")
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "hilo":
            return _err("بازی بالا‌پایین فعالی نداری", code="no_session")
        try:
            won, nxt = casino.hilo_guess(s, direction)
        except ValueError as e:
            return _err(str(e))
        if not won:
            await _solo_payout(uid, s, 0, "hilo")
        return _json({"ok": True, "session": _solo_view(s), "result": None if won else "lose",
                      "next": casino.cj(nxt), "win": 0, "balance": await _balance(uid)})


@_auth
async def api_hilo_cashout(request, user):
    uid = user["user_id"]
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "hilo":
            return _err("بازی بالا‌پایین فعالی نداری", code="no_session")
        if s["steps"] < 1:
            return _err("حداقل یک حدس درست لازم است")
        win = casino.hilo_payout(s)
        await _solo_payout(uid, s, win, "hilo")
        return _json({"ok": True, "session": _solo_view(s), "result": "win", "win": win,
                      "balance": await _balance(uid)})


async def _close_solo_session(uid: int):
    s = _solo_sessions.get(uid)
    if not s:
        return
    try:
        if s["type"] == "mines" and s["revealed"]:
            await _solo_payout(uid, s, casino.mines_payout(s), "mines")
        elif s["type"] == "hilo" and s["steps"] > 0:
            await _solo_payout(uid, s, casino.hilo_payout(s), "hilo")
        else:
            _solo_sessions.pop(uid, None)
            await db.add_balance(uid, s["bet"])
    except Exception:
        logger.exception("بستن سشن تک‌نفره ناموفق")


# ═══════════ دونفره ═══════════
async def _settle(g: GameState, winner, reason: str):
    if g.finished:
        return
    g.finished, g.finished_at = True, time.time()
    g.winner, g.reason, g.waiting = winner, reason, set()
    g.version += 1
    try:
        if winner is None:
            for uid, amount in g.contrib.items():
                if amount > 0:
                    await db.add_balance(uid, amount)
            g.payout = 0
        else:
            pot = g.pot
            g.payout = pot - int(pot * COMMISSION_RATE)
            await db.add_balance(winner, g.payout)
    except Exception:
        logger.exception(f"❌ پرداخت بازی {g.game_id} ناموفق")
    for uid in g.uids():
        if _user_games.get(uid) == g.game_id:
            _user_games.pop(uid, None)
        _track(uid, g.game_key, False, uid == winner, g.contrib.get(uid, g.bet))


async def _apply_outcome(g: GameState):
    if g.outcome and not g.finished:
        await _settle(g, *g.outcome)


async def _prepare(g: GameState):
    prep = GAME_IMPL.get(g.game_key, {}).get("prepare")
    if prep and not g.finished:
        try:
            await prep(g)
        except Exception:
            logger.exception("prepare error")


def _game_view(g: GameState, uid: int) -> dict:
    o = g.opp(uid)
    meta = GAMES.get(g.game_key, {})
    result = None
    if g.finished:
        result = "draw" if g.winner is None else ("win" if g.winner == uid else "lose")
    try:
        state = GAME_IMPL[g.game_key]["view"](g, uid)
    except Exception:
        logger.exception("view error")
        state = {}
    return {"game_id": g.game_id, "game_key": g.game_key, "title": meta.get("name", g.game_key),
            "emoji": meta.get("emoji", "🎮"), "bet": g.bet, "pot": g.pot,
            "me": {"id": uid, "name": g.name(uid)}, "opp": {"id": o, "name": g.name(o)},
            "your_turn": uid in g.waiting, "opp_turn": o in g.waiting,
            "deadline_in": 0 if g.finished else max(0, int(g.deadline - time.time())),
            "turn_timeout": TURN_TIMEOUT, "finished": g.finished, "result": result, "reason": g.reason,
            "payout": g.payout if g.winner == uid else 0, "lost": g.contrib.get(uid, 0),
            "version": g.version, "state": state}


# ─── صف ───
async def _queue_add(game_key, bet, uid, name) -> bool:
    entry = MatchEntry(uid, name, 0, bet)
    if _redis_on():
        data = {"name": name, "balance": 0, "avatar": ""}
        ok = await redis_client.add_to_queue(game_key, bet, uid, data)
        if not ok:
            try:
                await redis_client.remove_from_queue(uid)
            except Exception:
                pass
            ok = await redis_client.add_to_queue(game_key, bet, uid, data)
        if not ok:
            return False
    else:
        _match_queues.setdefault(f"{game_key}:{bet}", {})[uid] = entry
    _waiting[uid] = {"game_key": game_key, "bet": bet, "joined_at": entry.joined_at, "name": name}
    return True


async def _queue_remove(uid) -> dict | None:
    w = _waiting.pop(uid, None)
    if _redis_on():
        try:
            await redis_client.remove_from_queue(uid)
        except Exception:
            pass
    if w:
        q = _match_queues.get(f"{w['game_key']}:{w['bet']}")
        if q:
            q.pop(uid, None)
    return w


async def _queue_pop_opponent(game_key, bet, uid) -> dict | None:
    now = time.time()
    if _redis_on():
        for _ in range(10):
            opp = await redis_client.find_opponent_and_remove(game_key, bet, uid)
            if not opp:
                return None
            oid = int(opp["user_id"])
            w = _waiting.pop(oid, None)
            joined = w["joined_at"] if w else float(opp.get("joined_at") or 0)
            if oid == uid or oid in _user_games or now - joined > MATCH_TIMEOUT:
                await db.add_balance(oid, bet)
                continue
            return {"user_id": oid, "name": (w or {}).get("name") or opp.get("name") or "بازیکن"}
        return None
    q = _match_queues.get(f"{game_key}:{bet}") or {}
    for oid, e in sorted(q.items(), key=lambda kv: kv[1].joined_at):
        if oid == uid:
            continue
        q.pop(oid, None)
        _waiting.pop(oid, None)
        if now - e.joined_at > MATCH_TIMEOUT or oid in _user_games:
            await db.add_balance(oid, e.bet)
            continue
        return {"user_id": oid, "name": e.name}
    return None


async def _reclaim_orphan(uid) -> int:
    if uid in _waiting or not _redis_on():
        return 0
    try:
        st = await redis_client.get_queue_status(uid)
    except Exception:
        st = None
    if not st:
        return 0
    try:
        await redis_client.remove_from_queue(uid)
    except Exception:
        pass
    bet = int(st.get("bet") or 0)
    if bet > 0:
        await db.add_balance(uid, bet)
    return bet


async def _create_game(game_key, players, bet) -> GameState:
    import random as _r
    _r.SystemRandom().shuffle(players)
    g = GameState(secrets.token_urlsafe(9), game_key, players, bet)
    _active_games[g.game_id] = g
    for p in players:
        _user_games[p["user_id"]] = g.game_id
    async with g.lock:
        await GAME_IMPL[game_key]["init"](g)
        g.touch()
        await _apply_outcome(g)
    return g


def _active_game_of(uid) -> GameState | None:
    gid = _user_games.get(uid)
    g = _active_games.get(gid) if gid else None
    if g and not g.finished:
        return g
    if gid:
        _user_games.pop(uid, None)
    return None


def _queue_info(uid) -> dict | None:
    w = _waiting.get(uid)
    if not w:
        return None
    meta = GAMES.get(w["game_key"], {})
    return {"game_key": w["game_key"], "bet": w["bet"], "title": meta.get("name", ""), "emoji": meta.get("emoji", ""),
            "remaining": max(0, int(MATCH_TIMEOUT - (time.time() - w["joined_at"])))}


@_auth
async def api_me(request, user):
    uid = user["user_id"]
    async with _matchmaking_lock:
        refunded = await _reclaim_orphan(uid)
    g = _active_game_of(uid)
    return _json({
        "ok": True,
        "user": {"id": uid, "name": _uname(user), "balance": await _balance(uid),
                 "level": _calc_level(int(user.get("total_xp", 0) or 0))},
        "games": _games_for_client(await _get_settings()), "commission": COMMISSION_RATE,
        "match_timeout": MATCH_TIMEOUT, "turn_timeout": TURN_TIMEOUT, "max_bet": MAX_BET,
        "xp": {"min": XP_MIN, "max": XP_MAX, "divisor": XP_DIVISOR},
        "wheel_segments": casino.WHEEL_SEGMENTS, "queue": _queue_info(uid), "game_id": g.game_id if g else None,
        "solo": _solo_view(_solo_sessions.get(uid)), "refunded": refunded,
    })


@_auth
async def api_balance(request, user):
    return _json({"ok": True, "balance": await _balance(user["user_id"])})


@_auth
async def api_match_join(request, user):
    uid = user["user_id"]
    body = await _body(request)
    game_key = body.get("game")
    if GAMES.get(game_key, {}).get("type") != "2p" or game_key not in GAME_IMPL:
        return _err("بازی دونفره نامعتبر است")
    bet = _to_int(body.get("bet"))
    name = _uname(user)
    async with _matchmaking_lock:
        g = _active_game_of(uid)
        if g:
            return _err("در یک بازی فعال هستی", code="in_game", game_id=g.game_id)
        if uid in _waiting:
            return _err("در صف انتظار هستی", code="in_queue", queue=_queue_info(uid))
        await _reclaim_orphan(uid)
        err = await _take_bet(uid, game_key, bet)
        if err:
            return _err(err)
        opp = await _queue_pop_opponent(game_key, bet, uid)
        if opp:
            g = await _create_game(game_key, [opp, {"user_id": uid, "name": name}], bet)
            return _json({"ok": True, "status": "matched", "game_id": g.game_id, "balance": await _balance(uid)})
        if not await _queue_add(game_key, bet, uid, name):
            await db.add_balance(uid, bet)
            return _err("ورود به صف ناموفق بود — دوباره تلاش کن")
        return _json({"ok": True, "status": "waiting", "queue": _queue_info(uid), "balance": await _balance(uid)})


@_auth
async def api_match_cancel(request, user):
    uid = user["user_id"]
    async with _matchmaking_lock:
        g = _active_game_of(uid)
        if g:
            return _json({"ok": True, "status": "matched", "game_id": g.game_id})
        w = await _queue_remove(uid)
        if w:
            await db.add_balance(uid, w["bet"])
            refunded = w["bet"]
        else:
            refunded = await _reclaim_orphan(uid)
    return _json({"ok": True, "status": "cancelled", "refunded": refunded, "balance": await _balance(uid)})


@_auth
async def api_match_status(request, user):
    uid = user["user_id"]
    async with _matchmaking_lock:
        g = _active_game_of(uid)
        if g:
            return _json({"ok": True, "status": "matched", "game_id": g.game_id})
        w = _waiting.get(uid)
        if w:
            if time.time() - w["joined_at"] >= MATCH_TIMEOUT:
                await _queue_remove(uid)
                await db.add_balance(uid, w["bet"])
                return _json({"ok": True, "status": "timeout", "refunded": w["bet"], "balance": await _balance(uid)})
            return _json({"ok": True, "status": "waiting", "queue": _queue_info(uid)})
        refunded = await _reclaim_orphan(uid)
    if refunded:
        return _json({"ok": True, "status": "timeout", "refunded": refunded, "balance": await _balance(uid)})
    return _json({"ok": True, "status": "idle", "balance": await _balance(uid)})


def _find_game(uid, gid) -> GameState | None:
    g = _active_games.get(gid) if isinstance(gid, str) else None
    if g is None:
        g = _active_games.get(_user_games.get(uid, ""))
    return g if g and uid in g.uids() else None


@_auth
async def api_game_state(request, user):
    uid = user["user_id"]
    g = _find_game(uid, (await _body(request)).get("game_id"))
    if not g:
        return _json({"ok": True, "game": None, "balance": await _balance(uid)})
    await _check_timeout(g)
    await _prepare(g)
    return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})


@_auth
async def api_game_action(request, user):
    uid = user["user_id"]
    body = await _body(request)
    g = _find_game(uid, body.get("game_id"))
    if not g:
        return _err("بازی پیدا نشد", 404, "no_game")
    async with g.lock:
        if not g.finished:
            err = await GAME_IMPL[g.game_key]["action"](g, uid, body)
            await _apply_outcome(g)
            if err:
                await _prepare(g)
                return _err(err, game=_game_view(g, uid))
            if not g.finished:
                g.touch()
    await _prepare(g)
    return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})


@_auth
async def api_game_leave(request, user):
    uid = user["user_id"]
    g = _find_game(uid, (await _body(request)).get("game_id"))
    if not g:
        return _json({"ok": True, "game": None, "balance": await _balance(uid)})
    async with g.lock:
        if not g.finished:
            await _settle(g, g.opp(uid), f"{g.name(uid)} بازی را ترک کرد")
    return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})


async def _check_timeout(g: GameState):
    if g.finished or time.time() <= g.deadline:
        return
    async with g.lock:
        if g.finished or time.time() <= g.deadline:
            return
        stalled = list(g.waiting)
        if len(stalled) == 1:
            await _settle(g, g.opp(stalled[0]), f"⏰ زمان {g.name(stalled[0])} تمام شد")
        else:
            await _settle(g, None, "⏰ هر دو بازیکن غیرفعال بودند — مساوی")


async def _sweeper():
    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL)
            now = time.time()
            async with _matchmaking_lock:
                for uid, w in list(_waiting.items()):
                    if now - w["joined_at"] >= MATCH_TIMEOUT + 15:
                        await _queue_remove(uid)
                        await db.add_balance(uid, w["bet"])
            for gid, g in list(_active_games.items()):
                if not g.finished:
                    await _check_timeout(g)
                elif now - g.finished_at > FINISHED_GAME_TTL:
                    _active_games.pop(gid, None)
            for uid, s in list(_solo_sessions.items()):
                if now - s.get("created", now) > SOLO_SESSION_TTL:
                    async with _ulock(uid):
                        await _close_solo_session(uid)
            for k, p in list(_pending_launch.items()):
                if now - p["t"] > 120:
                    _pending_launch.pop(k, None)
            for k, d in list(_last_damage.items()):
                if now - d["t"] > 120:
                    _last_damage.pop(k, None)
            for ip, fails in list(_admin_fails.items()):
                if not fails or now - fails[-1] > 600:
                    _admin_fails.pop(ip, None)
            for k, t in list(_ban_notified.items()):
                if now - t > 600:
                    _ban_notified.pop(k, None)
            try:
                await _get_settings()
                if _utils and hasattr(_utils, "build_main_menu_kb"):
                    _utils.MAIN_MENU_KB = _utils.build_main_menu_kb()
            except Exception:
                pass
            if len(_user_locks) > 5000:
                for uid, lk in list(_user_locks.items()):
                    if not lk.locked():
                        _user_locks.pop(uid, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sweeper error")


# ═══════════════════════════════════════════════
# ═══════════ پنل مدیریت ═══════════
# ═══════════════════════════════════════════════
_admin_fails: dict[str, list] = {}


def _client_ip(request) -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[0].strip() if xff else request.remote) or "?"


def _admin_ok(request) -> bool:
    h = request.headers.get("Authorization", "")
    if not h.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(h[6:].strip()).decode("utf-8")
    except Exception:
        return False
    u, _, p = raw.partition(":")
    ok_u = hmac.compare_digest(u.encode(), ADMIN_USERNAME.encode())
    ok_p = hmac.compare_digest(p.encode(), ADMIN_PASSWORD.encode())
    return ok_u and ok_p


def _admin(handler):
    async def wrapper(request: web.Request):
        ip = _client_ip(request)
        now = time.time()
        fails = [t for t in _admin_fails.get(ip, []) if now - t < 600]
        _admin_fails[ip] = fails
        if len(fails) >= 20:
            return web.Response(status=429, text="تلاش‌های ناموفق زیاد — ۱۰ دقیقه بعد امتحان کن")
        if not _admin_ok(request):
            if request.headers.get("Authorization"):
                fails.append(now)
            return web.Response(status=401, text="🔒 نیاز به ورود",
                                headers={"WWW-Authenticate": 'Basic realm="Zar Admin Panel", charset="UTF-8"'})
        try:
            if request.method == "POST":
                return await handler(request, await _body(request))
            return await handler(request, {})
        except Exception as e:
            logger.exception(f"admin error {request.path}: {e}")
            return _err(f"خطای سرور: {e}", 500)
    return wrapper


def _catalog() -> dict:
    return {
        "properties": [{"key": k, "name": v["name"], "emoji": v["emoji"], "price": v["price"]}
                       for k, v in config.PROPERTIES.items()],
        "workers": [{"key": k, "name": v["name"], "emoji": v["emoji"], "price": v["price"]}
                    for k, v in config.WORKERS.items()],
        "items": [{"key": k, "name": v["name"], "emoji": v["emoji"], "price": v["price"], "type": v.get("type")}
                  for k, v in _bm_items().items()],
        "max_per_key": int(getattr(config, "MAX_PER_KEY", 5)),
    }


async def _user_detail(uid: int) -> dict | None:
    await _ensure_tables()
    u = await _fetch("SELECT user_id, username, first_name, balance, bank_balance, total_xp, level, card_number, "
                     "warehouse_level, vip_until, created_at FROM users WHERE user_id=%s", (uid,), one=True)
    if not u:
        return None
    assets = await _fetch("SELECT asset_type, asset_key, COUNT(*) AS c, SUM(daily_income) AS inc FROM assets "
                          "WHERE user_id=%s GROUP BY asset_type, asset_key", (uid,))
    inv = await _fetch("SELECT item_key, COUNT(*) AS c FROM inventory WHERE user_id=%s GROUP BY item_key", (uid,))
    try:
        await _ensure_tables()
        gifts = await _fetch("SELECT code, redeemed_at FROM gift_redemptions WHERE user_id=%s ORDER BY id DESC LIMIT 10", (uid,))
    except Exception:
        gifts = []
    xp = int(u["total_xp"] or 0)
    return {
        "user_id": int(u["user_id"]), "username": u["username"], "first_name": u["first_name"],
        "balance": int(u["balance"] or 0), "bank": int(u["bank_balance"] or 0), "xp": xp, "level": _calc_level(xp),
        "card": u["card_number"], "created_at": u["created_at"],
        "properties": {r["asset_key"]: int(r["c"]) for r in assets if r["asset_type"] == "property"},
        "workers": {r["asset_key"]: int(r["c"]) for r in assets if r["asset_type"] == "worker"},
        "daily_income": sum(int(r["inc"] or 0) for r in assets),
        "items": {r["item_key"]: int(r["c"]) for r in inv},
        "gifts": [{"code": g["code"], "at": float(g["redeemed_at"])} for g in gifts],
        "in_game": uid in _user_games, "in_queue": uid in _waiting, "banned": uid in _banned,
        "warehouse_level": int(u["warehouse_level"] or 1) if u.get("warehouse_level") is not None else 1,
        "vip_until": float(u["vip_until"]) if u.get("vip_until") else 0,
    }


@_admin
async def admin_page(request, body):
    try:
        html = ADMIN_HTML.read_text(encoding="utf-8")
    except FileNotFoundError:
        return web.Response(text="templates/admin.html پیدا نشد", status=500)
    return web.Response(text=html, content_type="text/html", charset="utf-8")


@_admin
async def admin_stats(request, body):
    s = await _fetch("SELECT COUNT(*) AS users, COALESCE(SUM(balance),0) AS bal, COALESCE(SUM(bank_balance),0) AS bank "
                     "FROM users", one=True)
    try:
        await _ensure_tables()
        gc = await _fetch("SELECT COUNT(*) AS c FROM gift_codes WHERE active=1", one=True)
    except Exception:
        gc = {"c": 0}
    return _json({"ok": True, "users": int(s["users"]), "balance": int(s["bal"]), "bank": int(s["bank"]),
                  "gifts": int(gc["c"]), "games": sum(1 for g in _active_games.values() if not g.finished),
                  "queue": len(_waiting), "redis": _redis_on(), "default_password": ADMIN_PASSWORD == "admin",
                  "bot_off": _bot_off,
                  "catalog": _catalog()})


@_admin
async def admin_search(request, body):
    q = str(body.get("q") or "").translate(_FA_DIGITS).strip().lstrip("@")
    if not q:
        return _json({"ok": True, "results": []})
    cols = "user_id, username, first_name, balance, bank_balance, total_xp"
    if q.isdigit() and len(q) <= 19:
        rows = await _fetch(f"SELECT {cols} FROM users WHERE user_id=%s OR card_number=%s LIMIT 20", (int(q), q))
    else:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = await _fetch(f"SELECT {cols} FROM users WHERE username LIKE %s OR first_name LIKE %s "
                            "ORDER BY balance DESC LIMIT 20", (like, like))
    return _json({"ok": True, "results": [{
        "user_id": int(r["user_id"]), "username": r["username"], "first_name": r["first_name"],
        "balance": int(r["balance"] or 0), "bank": int(r["bank_balance"] or 0),
        "level": _calc_level(int(r["total_xp"] or 0)), "banned": int(r["user_id"]) in _banned} for r in rows]})


@_admin
async def admin_user(request, body):
    uid = _to_int(body.get("user_id"))
    d = await _user_detail(uid) if uid else None
    if not d:
        return _err("کاربر پیدا نشد", 404)
    return _json({"ok": True, "user": d})


@_admin
async def admin_adjust(request, body):
    uid = _to_int(body.get("user_id"))
    kind = body.get("kind")
    key = str(body.get("key") or "")
    amount = _to_int(body.get("amount"), 0) or 0
    if kind not in GRANT_KINDS:
        return _err("نوع تغییر نامعتبر است")
    if not amount or abs(amount) > 10 ** 15:
        return _err("مقدار نامعتبر است")
    if kind in ("property", "worker", "item"):
        store = {"property": config.PROPERTIES, "worker": config.WORKERS, "item": _bm_items()}[kind]
        if key not in store:
            return _err("آیتم نامعتبر است")
    if not uid or not await _fetch("SELECT user_id FROM users WHERE user_id=%s", (uid,), one=True):
        return _err("کاربر پیدا نشد", 404)
    fn = _grant if amount > 0 else _revoke
    done = await _tx(lambda cur: fn(cur, uid, kind, key, abs(amount)))
    _invalidate(uid)
    logger.warning(f"🛠 ادمین: {kind}:{key} {'+' if amount > 0 else '-'}{done} برای {uid}")
    msg = f"{_kind_label(kind, key)}: {'+' if amount > 0 else '−'}{_fmt(done)}"
    if done < abs(amount):
        msg += " (بیشتر از این ممکن نبود — سقف/موجودی)"
    return _json({"ok": True, "done": done, "message": msg, "user": await _user_detail(uid)})


@_admin
async def admin_gifts_list(request, body):
    await _ensure_tables()
    rows = await _fetch("SELECT * FROM gift_codes ORDER BY created_at DESC LIMIT 300")
    out = []
    for r in rows:
        try:
            rewards = json.loads(r["rewards"] or "{}")
        except Exception:
            rewards = {}
        out.append({"code": r["code"], "rewards": rewards,
                    "rewards_text": _rewards_text(_rewards_list(rewards)).replace("• ", ""),
                    "max_uses": int(r["max_uses"]), "used": int(r["used_count"]), "min_level": int(r["min_level"]),
                    "expires_at": float(r["expires_at"]) if r["expires_at"] else None, "active": bool(r["active"]),
                    "note": r["note"] or "", "created_at": float(r["created_at"])})
    return _json({"ok": True, "gifts": out})


@_admin
async def admin_gifts_create(request, body):
    await _ensure_tables()
    code = _norm_code(body.get("code")) or secrets.token_hex(4).upper()
    raw = body.get("rewards") or {}
    rewards = {}
    for k in ("coins", "bank", "xp", "levels"):
        n = _to_int(raw.get(k), 0) or 0
        if n < 0 or n > 10 ** 15:
            return _err("مقدار جایزه نامعتبر است")
        if n:
            rewards[k] = min(n, MAX_LEVEL) if k == "levels" else n
    for field, store in (("properties", config.PROPERTIES), ("workers", config.WORKERS), ("items", _bm_items())):
        sub = {}
        for key, n in (raw.get(field) or {}).items():
            n = _to_int(n, 0) or 0
            if key not in store:
                return _err(f"آیتم نامعتبر: {key}")
            if n > 0:
                sub[key] = min(n, 100)
        if sub:
            rewards[field] = sub
    if not rewards:
        return _err("حداقل یک جایزه تعیین کن")
    max_uses = max(0, _to_int(body.get("max_uses"), 0) or 0)
    min_level = max(0, _to_int(body.get("min_level"), 0) or 0)
    hours = max(0, _to_int(body.get("expires_hours"), 0) or 0)
    expires = time.time() + hours * 3600 if hours else None
    note = str(body.get("note") or "")[:255]
    if await _fetch("SELECT code FROM gift_codes WHERE code=%s", (code,), one=True):
        return _err("این کد قبلاً ساخته شده")
    await _exec("INSERT INTO gift_codes (code, rewards, max_uses, used_count, min_level, expires_at, active, note, created_at) "
                "VALUES (%s,%s,%s,0,%s,%s,1,%s,%s)",
                (code, json.dumps(rewards, ensure_ascii=False), max_uses, min_level, expires, note, time.time()))
    return _json({"ok": True, "code": code})


@_admin
async def admin_gifts_toggle(request, body):
    await _ensure_tables()
    n = await _exec("UPDATE gift_codes SET active = 1 - active WHERE code=%s", (_norm_code(body.get("code")),))
    return _json({"ok": bool(n)})


@_admin
async def admin_gifts_delete(request, body):
    await _ensure_tables()
    code = _norm_code(body.get("code"))
    n = await _exec("DELETE FROM gift_codes WHERE code=%s", (code,))
    await _exec("DELETE FROM gift_redemptions WHERE code=%s", (code,))
    return _json({"ok": bool(n)})


# ═══════════════════════════════════════════════
# ═══════════ اتصال به ربات تلگرام ═══════════
# ═══════════════════════════════════════════════
_setup_apps: set = set()
_pending_launch: dict = {}


def casino_text() -> str:
    if _settings_cache.get("casino_text"):
        return _settings_cache["casino_text"]
    n1 = sum(1 for g in GAMES.values() if g["type"] == "1p")
    n2 = sum(1 for g in GAMES.values() if g["type"] == "2p")
    return ("🎰 <b>کازینو زر</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🎯 {n1} بازی تک‌نفره | ⚔️ {n2} بازی دونفره آنلاین\n"
            f"💰 شرط: از {_fmt(MIN_BET)} تا {_fmt(MAX_BET)}\n\n👇 برای ورود به کازینو بزن:")


def patch_bot_ui():
    """منوی اصلی: حذف «🎮 بازی‌ها» و افزودن «🎰 کازینو» (مینی‌اپ) + به‌روزرسانی راهنما"""
    if _utils:
        from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

        def build_main_menu_kb():
            s = _settings_cache

            def on(key):
                return s.get(f"section_off:{key}") != "1"

            items = []
            if on("bank"): items.append(B("🏦 بانک", callback_data="bank:menu"))
            if on("property"): items.append(B("🏠 ملک‌ها", callback_data="prop:menu"))
            if on("worker"): items.append(B("👷 کارگرها", callback_data="worker:menu"))
            if on("casino"): items.append(casino.miniapp_button("🎰 کازینو"))
            if on("missions"): items.append(B("🎯 ماموریت‌ها", callback_data="mission:menu"))
            if on("transfer"): items.append(B("💸 انتقال", callback_data="transfer:start"))
            if on("kabareh"): items.append(B("🎭 کاباره زر", callback_data="kabareh:menu"))
            if on("leaderboard"): items.append(B("🏆 لیدربورد", callback_data="lb:menu"))
            if on("blackmarket"): items.append(B("💀 بازار سیاه", callback_data="bm:menu:0"))
            if on("shop"): items.append(B("💎 خرید کوین و لول", callback_data="shop:menu"))
            if on("help"): items.append(B("📚 راهنما", callback_data="help:menu"))
            return M([items[i:i + 2] for i in range(0, len(items), 2)])

        _utils.build_main_menu_kb = build_main_menu_kb
        _utils.MAIN_MENU_KB = build_main_menu_kb()
        _utils.GAMES_MENU_KB = casino.miniapp_keyboard()
        _utils.BACK_GAMES_KB = M([[B("🔙 بازگشت", callback_data="menu:main")]])
    # تخریب حمله: پول + ملک/کارگر تصادفی (bot.py همین db.apply_damage را صدا می‌زند)
    global _orig_apply_damage, _orig_transfer
    if not getattr(getattr(db, "apply_damage", None), "_zar", False):
        _orig_apply_damage = getattr(db, "apply_damage", None)
        db.apply_damage = apply_damage_split
    # انتقال به/از کاربر بن‌شده ممنوع
    if hasattr(db, "transfer_coins") and not getattr(db.transfer_coins, "_zar", False):
        _orig_transfer = db.transfer_coins
        db.transfer_coins = _transfer_guarded
    # جوین اجباری: پیام عضویت به نام همان کاربر ثبت می‌شود + کش نتیجه مثبت (سریع‌تر)
    if _utils and not getattr(getattr(_utils, "verify_membership", None), "_zar", False):
        _utils.verify_membership = verify_membership_owned
    # انبار بازار سیاه (جایگزین اینونتوری)
    try:
        import blackmarket as _bm
        if not getattr(_bm, "_zar_patched", False):
            _bm._zar_patched = True
            _bm._build_inventory_text = _build_warehouse_text
            _bm._inventory_kb = _warehouse_kb
    except Exception:
        logger.exception("patch blackmarket failed")
    # قفل برداشت بانک + بونوس VIP روی درآمد
    global _orig_bank_deposit, _orig_bank_withdraw, _orig_accrue, _orig_peek
    if hasattr(db, "bank_deposit") and not getattr(db.bank_deposit, "_zar", False):
        _orig_bank_deposit = db.bank_deposit
        db.bank_deposit = _bank_deposit_locked
    if hasattr(db, "bank_withdraw") and not getattr(db.bank_withdraw, "_zar", False):
        _orig_bank_withdraw = db.bank_withdraw
        db.bank_withdraw = _bank_withdraw_locked
    if hasattr(db, "accrue_income") and not getattr(db.accrue_income, "_zar", False):
        _orig_accrue = db.accrue_income
        db.accrue_income = _accrue_vip
    if hasattr(db, "peek_income") and not getattr(db.peek_income, "_zar", False):
        _orig_peek = db.peek_income
        db.peek_income = _peek_vip
    t = getattr(config, "HELP_TEXT", "") or ""
    if t and "کازینو (مینی‌اپ)" not in t:
        block = ("🎰 کازینو (مینی‌اپ) : از منوی اصلی روی «🎰 کازینو» بزن\n"
                 "   تک‌نفره: چرخ شانس، موشک، مین‌یاب، بالا پایین، رولت، کارت شانس، پنالتی، شیر یا خط\n"
                 "   دونفره: پوکر تگزاس هولدم، حکم، بلک‌جک، کوییز، چهار در یک ردیف، سنگ کاغذ قیچی، دوز\n"
                 f"   حداکثر شرط {_fmt(MAX_BET)} | کارمزد برنده‌ی دونفره ۵٪\n"
                 "🎁 کد هدیه : بنویس «هدیه زر کد»\n")
        s, e = t.find("🎮"), t.find("💸 انتقال")
        t = t[:s] + block + t[e:] if 0 <= s < e else t + "\n" + block
        t = t.replace("• هر شلیک یک مهمات رو مصرف می‌کنه",
                      "• هر شلیک یک مهمات رو مصرف می‌کنه\n"
                      " • هر وسیله شلیک بعد از شلیک ۱ ساعت خنک می‌شه (با خرید وسیله بیشتر می‌تونی زودتر شلیک کنی)\n"
                      " • از هر سیستم دفاعی فقط ۱ عدد می‌تونی داشته باشی")
        config.HELP_TEXT = t


def _stop():
    from telegram.ext import ApplicationHandlerStop
    return ApplicationHandlerStop()


async def _h_gift(update, context):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    if _utils:
        _utils.log_group_chat_id(update)
    s = await _get_settings()
    if s.get("section_off:gift") == "1":
        await msg.reply_text("🎁 کد هدیه فعلاً غیرفعال است.")
        raise _stop()
    m = re.match(r"^\s*هدیه\s*زر\s+(\S+)\s*$", msg.text)
    if not m:
        await msg.reply_text("🎁 برای استفاده از کد هدیه بنویس:\n<code>هدیه زر کد</code>", parse_mode="HTML")
        raise _stop()
    if _utils and not await _utils.verify_membership(update, context):
        raise _stop()
    await db.ensure_user(update.effective_user)
    ok, text = await redeem_gift(update.effective_user.id, m.group(1))
    await msg.reply_text(text, parse_mode="HTML")
    raise _stop()


async def _h_casino_text(update, context):
    msg = update.effective_message
    if _utils:
        _utils.log_group_chat_id(update)
        if not await _utils.verify_membership(update, context):
            raise _stop()
    s = await _get_settings()
    if s.get("section_off:casino") == "1":
        await msg.reply_text("🎰 کازینو فعلاً غیرفعال است.")
        raise _stop()
    await msg.reply_text(casino_text(), parse_mode="HTML", reply_markup=casino.miniapp_keyboard(back=False))
    raise _stop()


async def _h_legacy_cb(update, context):
    q = update.callback_query
    uid = q.from_user.id
    owner = (not q.message) or (not _utils) or _utils.is_menu_owner(q.message.chat_id, q.message.message_id, uid)
    if owner and q.data in ("game:menu", "game:casino") and _utils:
        await _utils.safe_answer(q)
        m = await _utils.safe_edit(q, casino_text(), casino.miniapp_keyboard())
        if m:
            _utils.remember_owner(m, uid)
    else:
        try:
            await q.answer(casino.MOVED_TEXT, show_alert=True)
        except Exception:
            pass
    raise _stop()


async def _count_items(uid: int, key: str) -> int:
    r = await _fetch("SELECT COUNT(*) AS c FROM inventory WHERE user_id=%s AND item_key=%s", (uid, key), one=True)
    return int(r["c"]) if r else 0


def _cap_text(key: str, vip: bool = False) -> str:
    if _bm_items().get(key, {}).get("type") == "defense":
        return "🛡️ از هر سیستم دفاعی فقط ۱ عدد می‌تونی داشته باشی!"
    return f"🚀 از هر وسیله شلیک حداکثر {LAUNCHER_MAX_VIP if vip else LAUNCHER_MAX} عدد می‌تونی داشته باشی!"


async def _h_bm_guard(update, context):
    """سقف خرید: پدافند ۱، وسیله شلیک ۳ (VIP: ۶)، مهمات طبق ظرفیت انبار"""
    q = update.callback_query
    parts = (q.data or "").split(":")
    key = parts[2] if len(parts) > 2 else ""
    item = _bm_items().get(key)
    if not item or _not_owner(q):
        return
    uid = q.from_user.id
    vip = await _is_vip(uid)
    if item.get("type") == "projectile":
        cap = _wh_capacity(await _wh_level(uid), vip)
        msg = f"📦 انبار پر است! از این مهمات حداکثر {cap} عدد می‌تونی نگه داری — انبار را ارتقا بده."
    else:
        cap = _item_cap(key, vip)
        if not cap:
            return
        msg = _cap_text(key, vip)
    try:
        have = await _count_items(uid, key)
    except Exception:
        return
    if have >= cap:
        try:
            await q.answer(msg + f"\n(الان {have} عدد داری)", show_alert=True)
        except Exception:
            pass
        raise _stop()


async def _h_bm_post(update, context):
    """اطمینان نهایی: اگر به هر دلیلی بیش از سقف ثبت شد، اضافه حذف و پولش برمی‌گردد"""
    q = update.callback_query
    parts = (q.data or "").split(":")
    key = parts[2] if len(parts) > 2 else ""
    item = _bm_items().get(key)
    if not item:
        return
    uid = q.from_user.id
    vip = await _is_vip(uid)
    cap = _wh_capacity(await _wh_level(uid), vip) if item.get("type") == "projectile" else _item_cap(key, vip)
    if not cap:
        return
    try:
        have = await _count_items(uid, key)
        if have > cap:
            removed = await _exec("DELETE FROM inventory WHERE user_id=%s AND item_key=%s ORDER BY id DESC LIMIT %s",
                                  (uid, key, have - cap))
            refund = removed * int(item["price"])
            if refund:
                await db.add_balance(uid, refund)
                await context.bot.send_message(q.message.chat_id if q.message else uid,
                                               f"{_cap_text(key, vip)} — {_fmt(refund)} برگشت داده شد.")
    except Exception:
        logger.exception("bm post-check error")


def _cmd_map() -> dict:
    return {v["command"]: k for k, v in _bm_items().items() if v.get("type") == "projectile" and v.get("command")}


async def _h_attack_pre(update, context):
    """خنک شدن ۱ ساعته‌ی هر وسیله شلیک (هر واحد جداگانه)"""
    msg = update.effective_message
    if not msg or not msg.text or not msg.reply_to_message:
        return
    proj = _cmd_map().get(msg.text.strip())
    if not proj:
        return
    target = msg.reply_to_message.from_user
    if target and target.id in _banned:
        await msg.reply_text("🚫 این کاربر از ربات محروم است و نمی‌توان به او حمله کرد.")
        raise _stop()
    launchers = [k for k, v in _bm_items().items() if v.get("type") == "launcher" and proj in v.get("launches", [])]
    if not launchers:
        return
    uid = update.effective_user.id
    try:
        await _ensure_tables()
        ph = ",".join(["%s"] * len(launchers))
        rows = await _fetch(f"SELECT id, item_key, last_used FROM inventory WHERE user_id=%s AND item_key IN ({ph})",
                            (uid, *launchers))
        proj_count = await _count_items(uid, proj) if rows else 0
        if not rows or proj_count <= 0:
            return  # هندلر اصلی پیام «وسیله/مهمات نداری» را می‌دهد
    except Exception:
        logger.exception("attack pre-check error")
        return
    now = time.time()
    ready = [r for r in rows if not r["last_used"] or now - float(r["last_used"]) >= LAUNCH_COOLDOWN]
    if not ready:
        wait = min(float(r["last_used"]) + LAUNCH_COOLDOWN for r in rows) - now
        mins = max(1, math.ceil(wait / 60))
        names = "، ".join(f"{_bm_items()[k]['emoji']} {_bm_items()[k]['name']}" for k in launchers)
        await msg.reply_text(
            f"⏳ <b>وسیله شلیک در حال خنک شدن است</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🚀 وسایل تو ({len(rows)} عدد) همه در ۱ ساعت گذشته شلیک کرده‌اند.\n"
            f"⏰ زمان باقی‌مانده: <b>{mins} دقیقه</b>\n\n"
            f"💡 با خرید یک وسیله دیگر از بازار سیاه می‌تونی همین الان شلیک کنی:\n{names}",
            parse_mode="HTML")
        raise _stop()
    _pending_launch[update.update_id] = {"row": ready[0]["id"], "uid": uid, "proj": proj, "count": proj_count, "t": now}


async def _h_attack_post(update, context):
    p = _pending_launch.pop(update.update_id, None)
    if p:
        try:
            if await _count_items(p["uid"], p["proj"]) < p["count"]:  # شلیک واقعاً انجام شد
                await _exec("UPDATE inventory SET last_used=%s WHERE id=%s", (time.time(), p["row"]))
        except Exception:
            logger.exception("attack post error")
    # گزارش ملک/کارگرهای نابودشده
    try:
        msg = update.effective_message
        rep = msg.reply_to_message if msg else None
        tgt = rep.from_user.id if rep and rep.from_user else None
        d = _last_damage.pop(tgt, None) if tgt else None
        if d and time.time() - d["t"] < 60 and d["total"] > 0:
            report = _damage_report(d)
            await msg.reply_text(f"🏚 <b>جزئیات خسارت</b>\n━━━━━━━━━━━━━━━━━━\n{report}\n\n💥 مجموع خسارت: <b>{_fmt(d['total'])}</b>",
                                 parse_mode="HTML")
            if d["assets"]:
                try:
                    await context.bot.send_message(tgt, f"🏚 <b>در حمله این دارایی‌ها از دست رفت:</b>\n{report}",
                                                   parse_mode="HTML")
                except Exception:
                    pass
    except Exception:
        logger.exception("damage report error")


def setup_bot(app):
    """ثبت امکانات جدید روی اپلیکیشن ربات (یک بار)"""
    if id(app) in _setup_apps:
        return
    _setup_apps.add(id(app))
    global _bot_app
    _bot_app = app
    from telegram import Update
    from telegram.ext import (CallbackQueryHandler, CommandHandler, MessageHandler, PreCheckoutQueryHandler,
                              TypeHandler, filters)
    patch_bot_ui()
    app.add_handler(TypeHandler(Update, _h_bot_gate), group=-100)  # حالت خاموشی/بن → ربات جواب نمی‌دهد
    app.add_handler(CallbackQueryHandler(_h_section_gate), group=-2)  # بخش خاموش → دکمه کار نمی‌کند
    app.add_handler(CallbackQueryHandler(_h_check_membership, pattern=r"^check_membership$"), group=-2)
    app.add_handler(CallbackQueryHandler(_h_lb_cb, pattern=r"^lb:"), group=-2)
    app.add_handler(CommandHandler("start", _h_start_shop, filters=filters.ChatType.PRIVATE), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\s*هدیه\s*زر(\s+\S+)?\s*$"), _h_gift), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\s*(کازینو\s*زربات|زر\s*بازی)\s*$"),
                                   _h_casino_text), group=-2)
    app.add_handler(CallbackQueryHandler(_h_help_cb, pattern=r"^help:(menu|p:\d+)$"), group=-2)
    app.add_handler(CallbackQueryHandler(_h_wh_upgrade, pattern=r"^wh:upgrade$"), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _h_bank_lock), group=-2)
    app.add_handler(CallbackQueryHandler(_h_shop_cb, pattern=r"^shop:"), group=-2)
    app.add_handler(PreCheckoutQueryHandler(_h_precheckout), group=-2)
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, _h_paid), group=-2)
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, _h_receipt), group=-2)
    app.add_handler(CallbackQueryHandler(
        _h_legacy_cb, pattern=r"^(game:(menu|casino|rps|ttt|quiz|penalty)$|casino:|rps:|ttt:|quiz:|penalty:|pen:)"),
        group=-2)
    app.add_handler(CallbackQueryHandler(_h_bm_guard, pattern=r"^bm:buy:"), group=-2)
    app.add_handler(CallbackQueryHandler(_h_bm_post, pattern=r"^bm:buy:"), group=1)
    cmds = _cmd_map()
    if cmds:
        rx = r"^(" + "|".join(re.escape(c) for c in cmds) + r")$"
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(rx), _h_attack_pre), group=-2)
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(rx), _h_attack_post), group=1)

    old_init = getattr(app, "post_init", None)
    old_shutdown = getattr(app, "post_shutdown", None)

    async def _post_init(application):
        if old_init:
            await old_init(application)
        try:
            await start_webapp()
        except Exception:
            logger.exception("start_webapp ناموفق")
        try:
            await _ensure_tables()
            await _load_bans()
        except Exception:
            logger.exception("ساخت جداول جدید / بارگذاری بن‌ها ناموفق")
        try:
            await _load_admins()
        except Exception:
            logger.exception("بارگذاری ادمین‌ها ناموفق")

    async def _post_shutdown(application):
        try:
            await stop_webapp()
        except Exception:
            logger.exception("stop_webapp ناموفق")
        if old_shutdown:
            await old_shutdown(application)

    app.post_init = _post_init
    app.post_shutdown = _post_shutdown
    logger.info("✅ کازینو، کد هدیه، پنل مدیریت و قوانین بازار سیاه فعال شد")


# ═══════════════════════════════════════════════
# ═══════════ تخریب حمله: پول + ملک/کارگر تصادفی ═══════════
# ═══════════════════════════════════════════════
_rng = random.SystemRandom()
_last_damage: dict = {}
_orig_apply_damage = None
_bot_app = None


def _esc(s) -> str:
    return html.escape(str(s or ""))


async def apply_damage_split(target_id, damage_percent, *args, **kwargs) -> int:
    """
    همان درصد تخریب وسیله از پول هدف (کیف پول + بانک) و همان درصد از «تعداد» ملک‌ها و کارگرهایش کم می‌شود.
    ملک/کارگرهای نابودشده تصادفی انتخاب می‌شوند. گرد کردن احتمالی است (مثلاً ۲۰٪ از ۳ ملک = ۰٫۶ → با احتمال ۶۰٪ یکی)
    و با درصد کمتر از ۱۰۰ هیچ‌وقت همه‌ی دارایی‌ها یک‌جا صفر نمی‌شود.
    خروجی: ارزش کل خسارت (برای پیام bot.py)
    """
    try:
        pct = max(0.0, min(float(damage_percent), 1.0))
        target_id = int(target_id)
    except (TypeError, ValueError):
        return 0
    if pct <= 0 or target_id in _banned:
        return 0

    async def run(cur):
        await cur.execute("SELECT balance, bank_balance, total_xp, level FROM users WHERE user_id=%s FOR UPDATE", (target_id,))
        u = await cur.fetchone()
        if not u:
            return None
        bal, bank = max(0, int(u["balance"] or 0)), max(0, int(u["bank_balance"] or 0))
        xp0, lvl0 = int(u["total_xp"] or 0), int(u["level"] or 1)  # حمله هرگز لول/XP را کم نمی‌کند
        await cur.execute("SELECT id, asset_type, asset_key, purchase_price FROM assets WHERE user_id=%s FOR UPDATE",
                          (target_id,))
        assets = list(await cur.fetchall())
        money_part = int((bal + bank) * pct)
        n = len(assets)
        k = 0
        if n:
            exact = n * pct
            k = int(exact)
            if _rng.random() < exact - k:
                k += 1
            if pct < 1 and n > 1:
                k = min(k, n - 1)
        removed = _rng.sample(assets, k) if k else []
        if money_part <= 0 and not removed:
            return None
        from_bal = min(bal, money_part)
        from_bank = min(bank, money_part - from_bal)
        money_part = from_bal + from_bank
        await cur.execute("UPDATE users SET balance = balance - %s, bank_balance = bank_balance - %s WHERE user_id=%s",
                          (from_bal, from_bank, target_id))
        if removed:
            ids = [int(a["id"]) for a in removed]
            await cur.execute(f"DELETE FROM assets WHERE id IN ({','.join(['%s'] * len(ids))})", ids)
        asset_value = sum(int(a["purchase_price"] or 0) for a in removed)
        # اطمینان نهایی: لول و XP دقیقاً به مقدار قبل از حمله برگردد
        await cur.execute("UPDATE users SET total_xp=%s, level=%s WHERE user_id=%s", (xp0, lvl0, target_id))
        return {"money": money_part, "assets": [(a["asset_type"], a["asset_key"]) for a in removed],
                "asset_value": asset_value, "total": money_part + asset_value}

    try:
        res = await _tx(run)
    except Exception:
        logger.exception("apply_damage_split error — استفاده از نسخه قدیمی")
        if _orig_apply_damage:
            try:
                before = await _fetch("SELECT total_xp, level FROM users WHERE user_id=%s", (target_id,), one=True)
            except Exception:
                before = None
            res = await _orig_apply_damage(target_id, damage_percent, *args, **kwargs)
            if before:  # حتی نسخه قدیمی هم حق ندارد لول/XP را کم کند
                try:
                    await _exec("UPDATE users SET total_xp=%s, level=%s WHERE user_id=%s",
                               (int(before["total_xp"] or 0), int(before["level"] or 1), target_id))
                    _invalidate(target_id)
                except Exception:
                    pass
            return res
        return 0
    _invalidate(target_id)
    if not res:
        return 0
    res["t"] = time.time()
    _last_damage[target_id] = res
    return res["total"]


apply_damage_split._zar = True


def _damage_report(d: dict) -> str:
    lines = [f"💰 پول: {_fmt(d['money'])}"]
    counts = {}
    for t, k in d["assets"]:
        counts[(t, k)] = counts.get((t, k), 0) + 1
    for (t, k), n in counts.items():
        lines.append(f"{_kind_label(t, k)} × {n}")
    if not d["assets"]:
        lines.append("🏠 ملک یا کارگری نابود نشد")
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# ═══════════ راهنمای صفحه‌بندی‌شده ═══════════
# ═══════════════════════════════════════════════
def _help_pages() -> list:
    s = _settings_cache
    c = config
    bm = _bm_items()
    one = [g for g in GAMES.values() if g["type"] == "1p"]
    two = [g for g in GAMES.values() if g["type"] == "2p"]

    def items(t):
        out = []
        for v in bm.values():
            if v.get("type") != t:
                continue
            extra = ""
            if t == "projectile":
                extra = f" — {int(v.get('damage', 0) * 100)}٪ تخریب"
            elif t == "defense":
                extra = f" — {int(v.get('defense_chance', 0) * 100)}٪ دفاع"
            out.append(f" • {v['emoji']} {v['name']} ({_fmt(v['price'])}){extra}")
        return "\n".join(out) or " —"

    cmds = "\n".join(f" • <code>{v['command']}</code> ← {v['emoji']} {v['name']}"
                     for v in bm.values() if v.get("type") == "projectile" and v.get("command"))
    p1 = ("📚 <b>راهنما — اقتصاد و پیشرفت</b>\n━━━━━━━━━━━━━━━━━━\n"
          "⭐ <b>لول:</b> هر لول نیاز به 2^level × 1000 XP دارد\n"
          f"🎯 <b>ماموریت‌ها:</b> هر روز {getattr(c, 'DAILY_MISSION_COUNT', 6)} ماموریت جدید با جایزه XP\n"
          "💰 <b>زر:</b> هر ۵ دقیقه بنویس «زر» و زرکوین رایگان بگیر\n"
          f"🏦 <b>بانک:</b> سود روزانه {int(getattr(c, 'BANK_RATE', 0.02) * 100)}٪ (هر ساعت واریز می‌شود)\n"
          f"🔒 <b>برداشت از بانک:</b> بعد از واریز، تا {BANK_LOCK_SECONDS // 3600} ساعت قفل است\n"
          f"🏠 <b>ملک‌ها</b> و 👷 <b>کارگرها:</b> حداکثر {getattr(c, 'MAX_PER_KEY', 5)} از هر نوع — سود روزانه ۳۵٪\n"
          "💸 <b>برداشت درآمد:</b> از بخش ملک یا کارگر، درآمد انباشته را برداشت کن\n"
          "💸 <b>انتقال:</b> بالای ۱ میلیون کارمزد ۱٪\n"
          "🔒 هر کاربر فقط می‌تواند از منوی خودش استفاده کند")
    p2 = ("🎰 <b>راهنما — کازینو (مینی‌اپ)</b>\n━━━━━━━━━━━━━━━━━━\n"
          "از منوی اصلی روی «🎰 کازینو» بزن یا بنویس <b>کازینو زربات</b>\n\n"
          f"🎯 <b>تک‌نفره ({len(one)}):</b>\n" + "، ".join(f"{g['emoji']} {g['name']}" for g in one) + "\n\n"
          f"⚔️ <b>دونفره آنلاین ({len(two)}):</b>\n" + "، ".join(f"{g['emoji']} {g['name']}" for g in two) + "\n\n"
          f"💰 حداقل شرط: {_fmt(MIN_BET)} | حداکثر: {_fmt(MAX_BET)} زرکوین\n"
          f"⭐ XP فقط با برد داده می‌شود و بر اساس مبلغ شرط است (حداکثر {XP_MAX})\n"
          f"⏳ یافتن حریف: حداکثر {MATCH_TIMEOUT} ثانیه (وگرنه پول برمی‌گردد)\n"
          f"⏰ زمان هر نوبت: {TURN_TIMEOUT} ثانیه\n"
          f"💵 کارمزد برنده‌ی دونفره: {int(COMMISSION_RATE * 100)}٪ — مساوی = برگشت کامل پول")
    p3 = ("💎 <b>راهنما — فروشگاه، هدیه و سرگرمی</b>\n━━━━━━━━━━━━━━━━━━\n"
          "💎 <b>خرید کوین و لول:</b> از منوی اصلی محصول را انتخاب کن و با ⭐ استارز تلگرام یا 💳 کارت به کارت بپرداز. "
          "خرید کارت به کارت بعد از تأیید رسید توسط مدیر تحویل می‌شود.\n\n"
          "👑 <b>اشتراک VIP</b> (از فروشگاه — یک‌ماهه/سه‌ماهه/شش‌ماهه):\n"
          " • تا ۶ عدد از هر وسیله شلیک (به‌جای ۳)\n"
          " • +۵ ظرفیت هر مهمات در انبار\n"
          " • +۱۰٪ سود ملک و کارگر\n"
          " • سود بانک ۵٪ (به‌جای ۲٪)\n\n"
          "🎁 <b>کد هدیه:</b> بنویس <code>هدیه زر کد</code> — از هر کد فقط یک بار\n\n"
          f"🎭 <b>کاباره زر:</b> نیاز به لول {getattr(c, 'KABAREH_MIN_LEVEL', 4)}+ | "
          f"باز کردن با {_fmt(getattr(c, 'KABAREH_UNLOCK_COST', 0))} | روزی یک بار\n\n"
          "🏆 <b>لیدربورد:</b> رتبه‌بندی بر اساس ثروت (موجودی + بانک)")
    p4 = ("💀 <b>راهنما — بازار سیاه</b>\n━━━━━━━━━━━━━━━━━━\n"
          f"🚀 <b>وسایل شلیک</b> (الزامی برای شلیک — از هر کدام حداکثر {LAUNCHER_MAX} عدد):\n{items('launcher')}\n\n"
          f"💥 <b>مهمات</b> (مصرفی):\n{items('projectile')}\n\n"
          f"🛡️ <b>دفاعی</b> (از هر کدام فقط ۱ عدد):\n{items('defense')}\n\n"
          "🏭 <b>انبار:</b> ۱۰ لول دارد؛ ظرفیت هر مهمات = ۲ × لول انبار (لول ۱۰ = ۲۰ عدد) — هزینه ارتقا = ۲^لول × ۱٬۰۰۰٬۰۰۰ زرکوین")
    p5 = ("🎯 <b>راهنما — حمله و دفاع</b>\n━━━━━━━━━━━━━━━━━━\n"
          "۱. وسیله شلیک و مهمات را از بازار سیاه بخر\n۲. روی پیام هدف ریپلای کن\n۳. دستور شلیک را بفرست:\n"
          + cmds + "\n\n⚠️ <b>قوانین:</b>\n"
          f" • هر وسیله شلیک بعد از شلیک {LAUNCH_COOLDOWN // 60} دقیقه خنک می‌شود؛ با چند وسیله می‌توانی پشت‌سرهم شلیک کنی\n"
          " • همان درصد تخریب وسیله از پول هدف (کیف + بانک) و همان درصد از تعداد ملک‌ها و کارگرهایش کم می‌شود؛ "
          "ملک و کارگرهای نابودشده تصادفی انتخاب می‌شوند\n"
          " • به کاربران بن‌شده نمی‌توان حمله کرد یا پول انتقال داد\n"
          " • بمب‌ها قابل دفاع نیستند، فقط موشک و پهپاد\n"
          " • هر شلیک یک مهمات مصرف می‌کند")
    pages = [p1, p2, p3, p4, p5]
    for i in range(5):
        if s.get(f"help_page:{i + 1}"):
            pages[i] = s[f"help_page:{i + 1}"]
    return pages


def _not_owner(q) -> bool:
    return bool(q.message and _utils and not _utils.is_menu_owner(q.message.chat_id, q.message.message_id, q.from_user.id))


async def _h_help_cb(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    q = update.callback_query
    if _not_owner(q):
        await _utils.safe_answer(q, "❌ این منو برای شما نیست!\nبرای منوی خودت /menu را بفرست.", show_alert=True)
        raise _stop()
    pages = _help_pages()
    page = 0 if q.data == "help:menu" else max(0, min(int(q.data.split(":")[2]), len(pages) - 1))
    nav = []
    if page > 0:
        nav.append(B("➡️ قبلی", callback_data=f"help:p:{page - 1}"))
    nav.append(B(f"📄 {page + 1}/{len(pages)}", callback_data=f"help:p:{page}"))
    if page < len(pages) - 1:
        nav.append(B("بعدی ⬅️", callback_data=f"help:p:{page + 1}"))
    await _utils.safe_answer(q)
    m = await _utils.safe_edit(q, pages[page], M([nav, [B("🔙 بازگشت", callback_data="menu:main")]]))
    if m:
        _utils.remember_owner(m, q.from_user.id)
    raise _stop()


# ═══════════════════════════════════════════════
# ═══════════ فروشگاه: خرید کوین و لول ═══════════
# ═══════════════════════════════════════════════
def _env_admin_ids() -> set:
    """مالک (OWNER_ID) + آیدی‌های SHOP_ADMIN_IDS — از تنظیمات سرور می‌آیند و از پنل قابل حذف نیستند"""
    ids = {int(getattr(config, "OWNER_ID", 0) or 0)}
    for x in (os.getenv("SHOP_ADMIN_IDS") or "").split(","):
        if x.strip().isdigit():
            ids.add(int(x.strip()))
    ids.discard(0)
    return ids


def _owner_ids() -> set:
    """همه‌ی ادمین‌های ربات: مالک + تنظیمات سرور + ادمین‌های افزوده‌شده از پنل"""
    return _env_admin_ids() | _admins


async def _get_settings(force: bool = False) -> dict:
    """کش تنظیمات (۳۰ ثانیه) — برای منو، بازی‌ها، متن‌ها و رنگ‌ها"""
    global _settings_cache, _settings_at, _settings_loaded
    now = time.time()
    if force or not _settings_loaded or now - _settings_at > 30:
        try:
            await _ensure_tables()
            rows = await _fetch("SELECT k, v FROM zar_settings")
            _settings_cache = {r["k"]: r["v"] for r in rows}
            _settings_at = now
            _settings_loaded = True
        except Exception:
            pass
    return _settings_cache


async def _get_setting(k: str, default: str = "") -> str:
    s = await _get_settings()
    return s.get(k) or default


async def _set_setting(k: str, v: str):
    await _ensure_tables()
    await _exec("INSERT INTO zar_settings (k, v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)", (k, v))
    _settings_cache[k] = v
    _settings_at = time.time()


def _games_for_client(s: dict) -> list:
    """لیست بازی‌ها برای مینی‌اپ — با اعمال خاموشی و نام/توضیح سفارشی"""
    out = []
    for k, v in GAMES.items():
        if s.get(f"game_off:{k}") == "1":
            continue
        g = dict(key=k, **v)
        if s.get(f"game_name:{k}"):
            g["name"] = s[f"game_name:{k}"]
        if s.get(f"game_desc:{k}"):
            g["desc"] = s[f"game_desc:{k}"]
        out.append(g)
    return out


def _clean_rewards(raw) -> tuple:
    raw = raw if isinstance(raw, dict) else {}
    rewards = {}
    for k in ("coins", "bank", "xp", "levels"):
        n = _to_int(raw.get(k), 0) or 0
        if n < 0 or n > 10 ** 15:
            return None, "مقدار جایزه نامعتبر است"
        if n:
            rewards[k] = min(n, MAX_LEVEL) if k == "levels" else n
    n = _to_int(raw.get("vip_days"), 0) or 0
    if n < 0 or n > 3650:
        return None, "مدت اشتراک VIP نامعتبر است"
    if n:
        rewards["vip_days"] = n
    for field, store in (("properties", config.PROPERTIES), ("workers", config.WORKERS), ("items", _bm_items())):
        sub = {}
        for key, n in (raw.get(field) or {}).items():
            n = _to_int(n, 0) or 0
            if key not in store:
                return None, f"آیتم نامعتبر: {key}"
            if n > 0:
                sub[key] = min(n, 100)
        if sub:
            rewards[field] = sub
    if not rewards:
        return None, "حداقل یک مورد (پول/لول/ملک/...) تعیین کن"
    return rewards, None


def _loads(s) -> dict:
    try:
        d = json.loads(s or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _price_line(p) -> str:
    parts = []
    if int(p["price_stars"] or 0):
        parts.append(f"⭐ {_fmt(p['price_stars'])} استارز")
    if int(p["price_toman"] or 0):
        parts.append(f"💳 {_fmt(p['price_toman'])} تومان")
    return " | ".join(parts) or "—"


async def _shop_products(active_only: bool = True):
    await _ensure_tables()
    where = " WHERE active=1" if active_only else ""
    return await _fetch(f"SELECT * FROM shop_products{where} ORDER BY sort ASC, id ASC")


async def _create_order(uid: int, p: dict, method: str, amount: int, status: str) -> int:
    now = time.time()
    async with db.db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO shop_orders (user_id, product_id, title, rewards, method, amount, status, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (uid, int(p["id"]), p["title"], p["rewards"], method, amount, status, now, now))
            oid = cur.lastrowid
        await conn.commit()
    return int(oid)


async def _deliver_order(oid: int, allowed: tuple, charge_id=None):
    """تحویل سفارش (اتمیک). خروجی: (user_id یا None, متن)"""
    now = time.time()

    async def run(cur):
        await cur.execute("SELECT * FROM shop_orders WHERE id=%s FOR UPDATE", (oid,))
        o = await cur.fetchone()
        if not o:
            return None, "سفارش پیدا نشد"
        if o["status"] not in allowed:
            return None, f"وضعیت فعلی سفارش: {o['status']}"
        granted, skipped = [], []
        for kind, key, n in _rewards_list(_loads(o["rewards"])):
            done = await _grant(cur, int(o["user_id"]), kind, key, n)
            if done:
                granted.append((kind, key, done))
            if done < n:
                skipped.append((kind, key, n - done))
        await cur.execute("UPDATE shop_orders SET status='paid', charge_id=%s, updated_at=%s WHERE id=%s",
                          (charge_id, now, oid))
        text = f"✅ <b>خرید تحویل شد!</b>\n━━━━━━━━━━━━━━━━━━\n🛒 {_esc(o['title'])} (سفارش #{oid})\n{_rewards_text(granted)}"
        if skipped:
            text += "\n\n⚠️ به‌خاطر سقف مجاز اضافه نشد:\n" + _rewards_text(skipped)
        return int(o["user_id"]), text

    uid, text = await _tx(run)
    if uid:
        _invalidate(uid)
    return uid, text


async def _notify(uid: int, text: str, bot=None):
    bot = bot or (_bot_app.bot if _bot_app else None)
    if not bot:
        return
    try:
        await bot.send_message(uid, text, parse_mode="HTML")
    except Exception:
        pass


async def _h_shop_cb(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, LabeledPrice
    q = update.callback_query
    uid = q.from_user.id
    parts = (q.data or "").split(":")
    act = parts[1] if len(parts) > 1 else "menu"
    arg = _to_int(parts[2], 0) if len(parts) > 2 else 0
    await _ensure_tables()

    # ─── تأیید / رد رسید توسط مدیر ───
    if act in ("ok", "no"):
        if uid not in _owner_ids():
            await _utils.safe_answer(q, "❌ فقط مدیر می‌تواند رسید را بررسی کند", show_alert=True)
            raise _stop()
        if act == "ok":
            buyer, text = await _deliver_order(arg, ("review", "awaiting_receipt"))
            note = "✅ تأیید و تحویل شد" if buyer else "⚠️ " + text
            if buyer:
                await _notify(buyer, text, context.bot)
        else:
            o = await _fetch("SELECT user_id FROM shop_orders WHERE id=%s", (arg,), one=True)
            n = await _exec("UPDATE shop_orders SET status='rejected', updated_at=%s WHERE id=%s "
                            "AND status IN ('review','awaiting_receipt')", (time.time(), arg))
            note = "❌ رد شد" if n else "⚠️ این سفارش قابل رد نیست"
            if n and o:
                await _notify(int(o["user_id"]), f"❌ رسید سفارش #{arg} تأیید نشد. در صورت مشکل با پشتیبانی تماس بگیر.",
                              context.bot)
        try:
            await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n" + note)
        except Exception:
            pass
        await _utils.safe_answer(q, note)
        raise _stop()

    if _not_owner(q):
        await _utils.safe_answer(q, "❌ این منو برای شما نیست!\nبرای منوی خودت /menu را بفرست.", show_alert=True)
        raise _stop()

    async def edit(text, rows):
        m = await _utils.safe_edit(q, text, M(rows))
        if m:
            _utils.remember_owner(m, uid)

    # خرید فقط از پیوی ربات
    if act in ("menu", "p", "stars", "card") and q.message and q.message.chat.type != "private":
        un = context.bot.username
        rows = [[B("🛒 ورود به فروشگاه در پیوی ربات", url=f"https://t.me/{un}?start=shop")]] if un else []
        rows.append([B("🔙 بازگشت", callback_data="menu:main")])
        await _utils.safe_answer(q, "🛒 خرید فقط از پیوی ربات امکان‌پذیر است", show_alert=True)
        await edit("💎 <b>خرید کوین و لول</b>\n━━━━━━━━━━━━━━━━━━\n🔒 برای امنیت پرداخت، خرید فقط از "
                   "<b>پیوی ربات</b> امکان‌پذیر است.\n👇 روی دکمه زیر بزن:", rows)
        raise _stop()

    if act == "menu":
        if not await _utils.verify_membership(update, context):
            raise _stop()
        text, rows = await _shop_menu_content()
        await _utils.safe_answer(q)
        await edit(text, rows)
        raise _stop()

    p = None
    if act in ("p", "stars", "card"):
        p = await _fetch("SELECT * FROM shop_products WHERE id=%s AND active=1", (arg,), one=True)
        if not p:
            await _utils.safe_answer(q, "❌ این محصول دیگر موجود نیست", show_alert=True)
            raise _stop()

    if act == "p":
        card = await _get_setting("card_number")
        desc = (_esc(p["description"]) + "\n\n") if p["description"] else ""
        text = (f"💎 <b>{_esc(p['title'])}</b>\n━━━━━━━━━━━━━━━━━━\n{desc}🎁 <b>شامل:</b>\n"
                f"{_rewards_text(_rewards_list(_loads(p['rewards'])))}\n\n💰 <b>قیمت:</b> {_price_line(p)}\n\n👇 روش پرداخت:")
        rows = []
        if int(p["price_stars"] or 0):
            rows.append([B(f"⭐ پرداخت با استارز ({_fmt(p['price_stars'])})", callback_data=f"shop:stars:{p['id']}")])
        if int(p["price_toman"] or 0) and card:
            rows.append([B(f"💳 کارت به کارت ({_fmt(p['price_toman'])} تومان)", callback_data=f"shop:card:{p['id']}")])
        if not rows:
            text += "\n⚠️ فعلاً روش پرداختی فعال نیست."
        rows.append([B("🔙 بازگشت به فروشگاه", callback_data="shop:menu")])
        await _utils.safe_answer(q)
        await edit(text, rows)
        raise _stop()

    if act == "stars":
        stars = int(p["price_stars"] or 0)
        if stars <= 0:
            await _utils.safe_answer(q, "❌ پرداخت با استارز برای این محصول فعال نیست", show_alert=True)
            raise _stop()
        oid = await _create_order(uid, p, "stars", stars, "pending")
        desc = (p["description"] or _rewards_text(_rewards_list(_loads(p["rewards"]))))[:250] or p["title"]
        kw = dict(title=p["title"][:32], description=desc, payload=f"zarshop:{oid}", provider_token="",
                  currency="XTR", prices=[LabeledPrice(p["title"][:32], stars)])
        try:
            await context.bot.send_invoice(chat_id=uid, **kw)
            await _utils.safe_answer(q, "🧾 فاکتور پرداخت ارسال شد 👇")
        except Exception as e:
            logger.warning(f"send_invoice ناموفق: {e}")
            await _exec("UPDATE shop_orders SET status='cancelled', updated_at=%s WHERE id=%s", (time.time(), oid))
            await _utils.safe_answer(q, "❌ ارسال فاکتور ناموفق بود — دوباره تلاش کن", show_alert=True)
        raise _stop()

    if act == "card":
        card, holder = await _get_setting("card_number"), await _get_setting("card_holder")
        if not card or not int(p["price_toman"] or 0):
            await _utils.safe_answer(q, "❌ پرداخت کارت به کارت فعال نیست", show_alert=True)
            raise _stop()
        await _exec("UPDATE shop_orders SET status='cancelled', updated_at=%s WHERE user_id=%s AND status='awaiting_receipt'",
                    (time.time(), uid))
        oid = await _create_order(uid, p, "card", int(p["price_toman"]), "awaiting_receipt")
        text = (f"💳 <b>پرداخت کارت به کارت</b>\n━━━━━━━━━━━━━━━━━━\n🛒 محصول: <b>{_esc(p['title'])}</b>\n"
                f"💰 مبلغ: <b>{_fmt(p['price_toman'])} تومان</b>\n💳 شماره کارت: <code>{_esc(card)}</code>\n"
                + (f"👤 به نام: {_esc(holder)}\n" if holder else "")
                + f"🧾 کد سفارش: <b>#{oid}</b>\n\n📸 بعد از واریز، <b>عکس رسید</b> را در <b>پیوی ربات</b> بفرست.\n"
                  "سفارش بعد از تأیید مدیر خودکار تحویل می‌شود.")
        rows = [[B("❌ لغو سفارش", callback_data=f"shop:cancel:{oid}")]]
        rows.append([B("🔙 بازگشت به فروشگاه", callback_data="shop:menu")])
        await _utils.safe_answer(q)
        await edit(text, rows)
        raise _stop()

    if act == "cancel":
        n = await _exec("UPDATE shop_orders SET status='cancelled', updated_at=%s WHERE id=%s AND user_id=%s "
                        "AND status IN ('awaiting_receipt','pending')", (time.time(), arg, uid))
        await _utils.safe_answer(q, "✅ سفارش لغو شد" if n else "این سفارش قابل لغو نیست", show_alert=True)
        await edit("❌ سفارش لغو شد.", [[B("🔙 بازگشت به فروشگاه", callback_data="shop:menu")]])
        raise _stop()

    await _utils.safe_answer(q)
    raise _stop()


async def _h_precheckout(update, context):
    pq = update.pre_checkout_query
    payload = pq.invoice_payload or ""
    if not payload.startswith("zarshop:"):
        return
    ok = False
    try:
        await _ensure_tables()
        o = await _fetch("SELECT * FROM shop_orders WHERE id=%s", (int(payload.split(":")[1]),), one=True)
        ok = bool(o and o["status"] == "pending" and int(o["user_id"]) == pq.from_user.id
                  and int(o["amount"]) == pq.total_amount and pq.currency == "XTR")
    except Exception:
        logger.exception("precheckout error")
    try:
        if ok:
            await pq.answer(ok=True)
        else:
            await pq.answer(ok=False, error_message="این سفارش معتبر نیست یا قبلاً پرداخت شده.")
    except Exception:
        pass
    raise _stop()


async def _h_paid(update, context):
    msg = update.effective_message
    sp = msg.successful_payment
    if not sp or not (sp.invoice_payload or "").startswith("zarshop:"):
        return
    oid = int(sp.invoice_payload.split(":")[1])
    try:
        buyer, text = await _deliver_order(oid, ("pending", "cancelled"), charge_id=sp.telegram_payment_charge_id)
    except Exception:
        logger.exception("deliver stars order failed")
        buyer, text = None, "خطا در تحویل"
    if buyer:
        await msg.reply_text(text, parse_mode="HTML")
    else:
        await msg.reply_text("⚠️ پرداخت انجام شد ولی تحویل خودکار ناموفق بود — به پشتیبانی پیام بده. کد سفارش: #" + str(oid))
    for admin_id in _owner_ids():
        await _notify(admin_id, f"💎 <b>خرید با استارز</b>\n👤 {_esc(update.effective_user.first_name)} ({update.effective_user.id})\n"
                                f"🧾 سفارش #{oid} — ⭐ {sp.total_amount}\n{'✅ تحویل شد' if buyer else '⚠️ ' + _esc(text)}",
                      context.bot)
    raise _stop()


async def _h_receipt(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    msg = update.effective_message
    uid = update.effective_user.id
    try:
        await _ensure_tables()
        o = await _fetch("SELECT * FROM shop_orders WHERE user_id=%s AND status='awaiting_receipt' AND created_at > %s "
                         "ORDER BY id DESC LIMIT 1", (uid, time.time() - 86400), one=True)
    except Exception:
        return
    if not o:
        return  # عکس مربوط به فروشگاه نیست
    file_id = msg.photo[-1].file_id
    await _exec("UPDATE shop_orders SET status='review', receipt_file_id=%s, updated_at=%s WHERE id=%s",
                (file_id, time.time(), o["id"]))
    caption = (f"🧾 رسید جدید — سفارش #{o['id']}\n👤 {update.effective_user.first_name} ({uid})\n"
               f"🛒 {o['title']}\n💰 {_fmt(o['amount'])} تومان")
    kb = M([[B("✅ تأیید و تحویل", callback_data=f"shop:ok:{o['id']}"), B("❌ رد", callback_data=f"shop:no:{o['id']}")]])
    sent = False
    for admin_id in _owner_ids():
        try:
            await context.bot.send_photo(admin_id, file_id, caption=caption, reply_markup=kb)
            sent = True
        except Exception:
            pass
    await msg.reply_text(f"✅ رسید سفارش #{o['id']} ثبت شد و برای بررسی ارسال شد.\nبعد از تأیید، خرید خودکار تحویل می‌شود."
                         + ("" if sent else "\n(مدیر می‌تواند از پنل مدیریت هم بررسی کند)"))
    raise _stop()


# ─── API پنل: فروشگاه ───
@_admin
async def admin_shop_products(request, body):
    prods = await _shop_products(active_only=False)
    sold = await _fetch("SELECT product_id, COUNT(*) AS c FROM shop_orders WHERE status='paid' GROUP BY product_id")
    sold_map = {int(r["product_id"]): int(r["c"]) for r in sold}
    out = []
    for p in prods:
        rw = _loads(p["rewards"])
        out.append({"id": int(p["id"]), "title": p["title"], "description": p["description"] or "", "rewards": rw,
                    "rewards_text": _rewards_text(_rewards_list(rw)).replace("• ", ""),
                    "price_toman": int(p["price_toman"] or 0), "price_stars": int(p["price_stars"] or 0),
                    "active": bool(p["active"]), "sort": int(p["sort"] or 0), "sold": sold_map.get(int(p["id"]), 0)})
    return _json({"ok": True, "products": out, "card_number": await _get_setting("card_number"),
                  "card_holder": await _get_setting("card_holder")})


@_admin
async def admin_shop_save(request, body):
    await _ensure_tables()
    pid = _to_int(body.get("id"), 0) or 0
    title = str(body.get("title") or "").strip()[:64]
    if not title:
        return _err("عنوان محصول را وارد کن")
    rewards, e = _clean_rewards(body.get("rewards"))
    if e:
        return _err(e)
    toman = max(0, _to_int(body.get("price_toman"), 0) or 0)
    stars = max(0, min(100_000, _to_int(body.get("price_stars"), 0) or 0))
    if not toman and not stars:
        return _err("حداقل یکی از قیمت‌ها (تومان یا استارز) را وارد کن")
    desc = str(body.get("description") or "")[:500]
    sort = _to_int(body.get("sort"), 0) or 0
    rj = json.dumps(rewards, ensure_ascii=False)
    if pid:
        await _exec("UPDATE shop_products SET title=%s, description=%s, rewards=%s, price_toman=%s, price_stars=%s, sort=%s "
                    "WHERE id=%s", (title, desc, rj, toman, stars, sort, pid))
    else:
        await _exec("INSERT INTO shop_products (title, description, rewards, price_toman, price_stars, active, sort, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,1,%s,%s)", (title, desc, rj, toman, stars, sort, time.time()))
    return _json({"ok": True})


@_admin
async def admin_shop_toggle(request, body):
    await _ensure_tables()
    n = await _exec("UPDATE shop_products SET active = 1 - active WHERE id=%s", (_to_int(body.get("id"), 0),))
    return _json({"ok": bool(n)})


@_admin
async def admin_shop_delete(request, body):
    await _ensure_tables()
    n = await _exec("DELETE FROM shop_products WHERE id=%s", (_to_int(body.get("id"), 0),))
    return _json({"ok": bool(n)})


@_admin
async def admin_shop_settings(request, body):
    card = re.sub(r"[^\d\-\s]", "", str(body.get("card_number") or "").translate(_FA_DIGITS)).strip()[:30]
    await _set_setting("card_number", card)
    await _set_setting("card_holder", str(body.get("card_holder") or "").strip()[:64])
    return _json({"ok": True})


@_admin
async def admin_shop_orders(request, body):
    await _ensure_tables()
    status = str(body.get("status") or "")
    args, where = (), ""
    if status in ("pending", "awaiting_receipt", "review", "paid", "rejected", "cancelled"):
        where, args = "WHERE o.status=%s", (status,)
    rows = await _fetch("SELECT o.*, u.first_name, u.username FROM shop_orders o LEFT JOIN users u ON u.user_id=o.user_id "
                        f"{where} ORDER BY o.id DESC LIMIT 200", args)
    rev = await _fetch("SELECT COUNT(*) AS c FROM shop_orders WHERE status='review'", one=True)
    return _json({"ok": True, "review_count": int(rev["c"]), "orders": [{
        "id": int(r["id"]), "user_id": int(r["user_id"]), "name": r["first_name"] or "", "username": r["username"] or "",
        "title": r["title"], "method": r["method"], "amount": int(r["amount"]), "status": r["status"],
        "receipt": bool(r["receipt_file_id"]), "created_at": float(r["created_at"])} for r in rows]})


@_admin
async def admin_shop_approve(request, body):
    oid = _to_int(body.get("id"), 0)
    buyer, text = await _deliver_order(oid, ("review", "awaiting_receipt", "pending"))
    if not buyer:
        return _err(re.sub(r"<[^>]+>", "", text))
    await _notify(buyer, text)
    return _json({"ok": True})


@_admin
async def admin_shop_reject(request, body):
    oid = _to_int(body.get("id"), 0)
    o = await _fetch("SELECT user_id FROM shop_orders WHERE id=%s", (oid,), one=True)
    n = await _exec("UPDATE shop_orders SET status='rejected', updated_at=%s WHERE id=%s "
                    "AND status IN ('review','awaiting_receipt','pending')", (time.time(), oid))
    if not n:
        return _err("این سفارش قابل رد نیست")
    if o:
        await _notify(int(o["user_id"]), f"❌ سفارش #{oid} تأیید نشد. در صورت مشکل با پشتیبانی تماس بگیر.")
    return _json({"ok": True})


@_admin
async def admin_receipt(request, body):
    oid = _to_int(request.match_info.get("oid"), 0)
    o = await _fetch("SELECT receipt_file_id FROM shop_orders WHERE id=%s", (oid,), one=True)
    if not o or not o["receipt_file_id"] or not _bot_app:
        return web.Response(status=404, text="رسید پیدا نشد")
    f = await _bot_app.bot.get_file(o["receipt_file_id"])
    data = await f.download_as_bytearray()
    return web.Response(body=bytes(data), content_type="image/jpeg")


# ═══════════════════════════════════════════════
# ═══════════ گیت بخش‌های ربات (خاموش/روشن از پنل) ═══════════
# ═══════════════════════════════════════════════
def _section_for_callback(data: str) -> str | None:
    if data.startswith("bank:"):
        return "bank"
    if data.startswith("prop:"):
        return "property"
    if data.startswith("worker:"):
        return "worker"
    if data.startswith("mission:"):
        return "missions"
    if data.startswith("transfer:") or data.startswith("tr:"):
        return "transfer"
    if data.startswith("kabareh:"):
        return "kabareh"
    if data.startswith("lb:"):
        return "leaderboard"
    if data.startswith("bm:"):
        return "blackmarket"
    if data.startswith("shop:"):
        return "shop"
    if data.startswith("help:"):
        return "help"
    if data in ("game:menu", "game:casino") or data.startswith("casino:"):
        return "casino"
    return None


async def _h_section_gate(update, context):
    """اگر بخش مربوط به این دکمه خاموش باشد، جلوی ادامه را می‌گیرد"""
    q = update.callback_query
    sec = _section_for_callback(q.data or "")
    if not sec:
        return
    s = await _get_settings()
    if s.get(f"section_off:{sec}") == "1":
        try:
            await q.answer("🚫 این بخش فعلاً غیرفعال است", show_alert=True)
        except Exception:
            pass
        raise _stop()


# ═══════════════════════════════════════════════
# ═══════════ بن کاربر ═══════════
# ═══════════════════════════════════════════════
_ban_notified: dict = {}
_orig_transfer = None


async def _load_bans():
    await _ensure_tables()
    rows = await _fetch("SELECT user_id FROM banned_users")
    _banned.clear()
    _banned.update(int(r["user_id"]) for r in rows)
    logger.info(f"🚫 {len(_banned)} کاربر بن‌شده بارگذاری شد")


async def _h_bot_gate(update, context):
    """اولین هندلر: در حالت خاموشی بات یا کاربر بن‌شده، هیچ پاسخی داده نمی‌شود"""
    u = update.effective_user
    if not u:
        return
    if _bot_off and u.id not in _owner_ids():
        raise _stop()
    if u.id not in _banned:
        return
    try:
        if update.pre_checkout_query:
            await update.pre_checkout_query.answer(ok=False, error_message="🚫 شما از ربات محروم شده‌اید")
        elif update.callback_query:
            await update.callback_query.answer("🚫 شما از ربات محروم شده‌اید", show_alert=True)
        elif update.effective_chat and update.effective_chat.type == "private" and update.effective_message:
            if time.time() - _ban_notified.get(u.id, 0) > 600:
                _ban_notified[u.id] = time.time()
                await update.effective_message.reply_text("🚫 شما از ربات محروم شده‌اید.")
    except Exception:
        pass
    raise _stop()


async def _transfer_guarded(sender_id, recipient_id, *args, **kwargs):
    try:
        if int(recipient_id) in _banned or int(sender_id) in _banned:
            return False
    except (TypeError, ValueError):
        pass
    return await _orig_transfer(sender_id, recipient_id, *args, **kwargs)


_transfer_guarded._zar = True


async def _kick_from_games(uid: int):
    async with _matchmaking_lock:
        w = await _queue_remove(uid)
        if w:
            await db.add_balance(uid, w["bet"])
    g = _active_game_of(uid)
    if g:
        async with g.lock:
            if not g.finished:
                await _settle(g, g.opp(uid), f"{g.name(uid)} از ربات محروم شد")
    async with _ulock(uid):
        await _close_solo_session(uid)


# ═══════════ ادمین‌های ربات (افزودن از پنل با آیدی عددی) ═══════════
async def _load_admins():
    await _ensure_tables()
    rows = await _fetch("SELECT user_id FROM bot_admins")
    _admins.clear()
    _admins.update(int(r["user_id"]) for r in rows)
    logger.info(f"🛡 {len(_admins)} ادمین (افزوده‌شده از پنل) بارگذاری شد")


@_admin
async def admin_admins_list(request, body):
    await _ensure_tables()
    owner = int(getattr(config, "OWNER_ID", 0) or 0)
    fixed = sorted(_env_admin_ids(), key=lambda x: (x != owner, x))
    names = {}
    if fixed:
        ph = ",".join(["%s"] * len(fixed))
        for r in await _fetch(f"SELECT user_id, first_name, username FROM users WHERE user_id IN ({ph})", tuple(fixed)):
            names[int(r["user_id"])] = r
    out = []
    for uid in fixed:
        r = names.get(uid) or {}
        out.append({"user_id": uid, "name": r.get("first_name") or "", "username": r.get("username") or "",
                    "role": "owner" if uid == owner else "env", "note": "", "added_at": None, "removable": False})
    rows = await _fetch("SELECT a.user_id, a.note, a.added_at, u.first_name, u.username FROM bot_admins a "
                        "LEFT JOIN users u ON u.user_id = a.user_id ORDER BY a.added_at ASC")
    for r in rows:
        uid = int(r["user_id"])
        if uid in fixed:
            continue
        out.append({"user_id": uid, "name": r["first_name"] or "", "username": r["username"] or "", "role": "panel",
                    "note": r["note"] or "", "added_at": float(r["added_at"]), "removable": True})
    return _json({"ok": True, "admins": out})


@_admin
async def admin_admins_add(request, body):
    uid = _to_int(body.get("user_id"), 0) or 0
    if uid <= 0:
        return _err("آیدی عددی نامعتبر است")
    if uid in _owner_ids():
        return _err("این کاربر از قبل ادمین است")
    if uid in _banned:
        return _err("این کاربر بن است — اول رفع بن کن")
    u = await _fetch("SELECT first_name FROM users WHERE user_id=%s", (uid,), one=True)
    if not u:
        return _err("کاربری با این آیدی در ربات پیدا نشد — باید اول ربات را استارت کرده باشد", 404)
    await _ensure_tables()
    await _exec("INSERT INTO bot_admins (user_id, note, added_at) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE note=VALUES(note)", (uid, str(body.get("note") or "")[:255], time.time()))
    _admins.add(uid)
    await _notify(uid, "🛡 شما <b>ادمین ربات</b> شدید.\n• رسیدهای خرید برای تأیید یا رد به شما هم ارسال می‌شود\n"
                       "• در حالت خاموشی، ربات برای شما کار می‌کند")
    logger.warning(f"🛡 ادمین جدید از پنل اضافه شد: {uid}")
    return _json({"ok": True, "name": u["first_name"] or ""})


@_admin
async def admin_admins_remove(request, body):
    uid = _to_int(body.get("user_id"), 0) or 0
    if uid in _env_admin_ids():
        return _err("این ادمین از تنظیمات سرور (OWNER_ID یا SHOP_ADMIN_IDS) است و از پنل قابل حذف نیست")
    await _ensure_tables()
    n = await _exec("DELETE FROM bot_admins WHERE user_id=%s", (uid,))
    _admins.discard(uid)
    if not n:
        return _err("این کاربر ادمین نیست")
    await _notify(uid, "ℹ️ دسترسی ادمین شما برداشته شد.")
    logger.warning(f"🛡 ادمین از پنل حذف شد: {uid}")
    return _json({"ok": True})


@_admin
async def admin_settings_get(request, body):
    """همه‌ی تنظیمات قابل ویرایش: بازی‌ها، بخش‌ها، متن‌ها و رنگ‌ها"""
    await _ensure_tables()
    s = await _get_settings(force=True)
    games = [{"key": k, "name": s.get(f"game_name:{k}", v["name"]), "desc": s.get(f"game_desc:{k}", v["desc"]),
              "emoji": v["emoji"], "type": v["type"], "off": s.get(f"game_off:{k}") == "1"}
             for k, v in GAMES.items()]
    sections = [{"key": k, "name": n, "off": s.get(f"section_off:{k}") == "1"} for k, n in SECTIONS]
    texts = {"casino_text": s.get("casino_text", "")}
    texts.update({f"help_page:{i}": s.get(f"help_page:{i}", "") for i in range(1, 6)})
    theme = {k[6:]: v for k, v in s.items() if k.startswith("theme:") and v}
    return _json({"ok": True, "games": games, "sections": sections, "texts": texts, "theme": theme,
                  "defaults": {"casino_text": casino_text(), "help_pages": _help_pages()}})


@_admin
async def admin_settings_save(request, body):
    """ذخیره‌ی تنظیمات — مقدار خالی یعنی بازگشت به پیش‌فرض"""
    await _ensure_tables()
    data = body.get("settings") or {}
    if not isinstance(data, dict):
        return _err("داده نامعتبر است")
    prefixes = ("game_off:", "game_name:", "game_desc:", "section_off:", "help_page:", "casino_text", "theme:")
    for k, v in data.items():
        if not any(k.startswith(p) for p in prefixes):
            continue
        v = str(v or "")[:4000]
        if k.startswith("theme:") and v and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            return _err(f"رنگ نامعتبر برای {k}")
        if k.startswith("game_name:") and GAMES.get(k.split(":", 1)[1], {}).get("name") == v:
            v = ""
        if k.startswith("game_desc:") and GAMES.get(k.split(":", 1)[1], {}).get("desc") == v:
            v = ""
        if v == "":
            await _exec("DELETE FROM zar_settings WHERE k=%s", (k,))
            _settings_cache.pop(k, None)
        else:
            await _exec("INSERT INTO zar_settings (k, v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)", (k, v))
            _settings_cache[k] = v
    _settings_at = time.time()
    return _json({"ok": True})


@_admin
async def admin_vip_list(request, body):
    """لیست کاربران VIP فعال"""
    await _ensure_tables()
    now = time.time()
    rows = await _fetch("SELECT user_id, first_name, username, vip_until FROM users WHERE vip_until > %s "
                        "ORDER BY vip_until DESC LIMIT 200", (now,))
    return _json({"ok": True, "vips": [{
        "user_id": int(r["user_id"]), "name": r["first_name"] or "", "username": r["username"] or "",
        "until": float(r["vip_until"]), "days_left": max(0, round((float(r["vip_until"]) - now) / 86400, 1)),
    } for r in rows]})


@_admin
async def admin_bot_toggle(request, body):
    """خاموش/روشن کردن بات از پنل مدیریت"""
    global _bot_off
    if isinstance(body.get("off"), bool):
        _bot_off = body["off"]
    else:
        _bot_off = not _bot_off
    logger.warning(f"🤖 بات {'🔴 خاموش' if _bot_off else '🟢 روشن'} شد (از پنل مدیریت)")
    for admin_id in _owner_ids():
        await _notify(admin_id, f"🤖 وضعیت ربات تغییر کرد:\n{'🔴 <b>خاموش</b> — ربات به جز ادمین‌ها جواب نمی‌دهد' if _bot_off else '🟢 <b>روشن</b>'}")
    return _json({"ok": True, "off": _bot_off})


@_admin
async def admin_ban(request, body):
    uid = _to_int(body.get("user_id"), 0)
    if not uid:
        return _err("آیدی نامعتبر است")
    if uid in _owner_ids():
        return _err("این کاربر مالک یا ادمین ربات است — اول از تب «ادمین‌ها» حذفش کن")
    if not await _fetch("SELECT user_id FROM users WHERE user_id=%s", (uid,), one=True):
        return _err("کاربر پیدا نشد", 404)
    await _ensure_tables()
    await _exec("INSERT INTO banned_users (user_id, reason, banned_at) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE reason=VALUES(reason), banned_at=VALUES(banned_at)",
                (uid, str(body.get("reason") or "")[:255], time.time()))
    _banned.add(uid)
    await _kick_from_games(uid)
    await _notify(uid, "🚫 شما از ربات محروم شدید.")
    logger.warning(f"🚫 ادمین کاربر {uid} را بن کرد")
    return _json({"ok": True, "user": await _user_detail(uid)})


@_admin
async def admin_unban(request, body):
    uid = _to_int(body.get("user_id"), 0)
    await _ensure_tables()
    await _exec("DELETE FROM banned_users WHERE user_id=%s", (uid,))
    _banned.discard(uid)
    await _notify(uid, "✅ محرومیت شما برداشته شد. خوش برگشتی!")
    return _json({"ok": True, "user": await _user_detail(uid)})


# ═══════════ جوین اجباری (رفع باگ مالکیت پیام) ═══════════
async def verify_membership_owned(update, context) -> bool:
    """مثل utils.verify_membership ولی پیام جوین به نام همان کاربر ثبت می‌شود و نتیجه مثبت کش می‌شود"""
    user = update.effective_user
    if not user:
        return False
    is_joined, missing = await _utils.check_membership_quiet(context.bot, user.id)
    if is_joined:
        return True
    text, kb = _utils.get_join_text(missing), _utils.get_join_keyboard()
    q = update.callback_query
    m = None
    if q:
        await _utils.safe_answer(q, "❌ هنوز عضو نشدی!", show_alert=True)
        if not _not_owner(q):
            m = await _utils.safe_edit(q, text, kb)
        if m is None:
            try:
                m = await q.from_user.send_message(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                m = None
    elif update.effective_message:
        try:
            m = await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"ارسال پیام جوین ناموفق: {e}")
    if m:
        _utils.remember_owner(m, user.id)
    return False


verify_membership_owned._zar = True


async def _h_check_membership(update, context):
    """دکمه «عضو شدم»: فقط صاحب پیام جوین منو را می‌بیند؛ بقیه فقط نتیجه‌ی عضویت خودشان را"""
    q = update.callback_query
    if not q.message or not _utils:
        return
    owners = _utils.menu_owners.get((q.message.chat_id, q.message.message_id))
    if owners is not None and q.from_user.id in owners:
        return  # صاحب پیام → هندلر اصلی bot.py
    is_joined, missing = await _utils.check_membership_force(context.bot, q.from_user.id)
    if is_joined:
        await _utils.safe_answer(q, "✅ عضویتت تأیید شد!\nبرای باز شدن منوی خودت /menu را بفرست.", show_alert=True)
    else:
        await _utils.safe_answer(q, "❌ هنوز عضو نشدی:\n" + "\n".join(f"• {x}" for x in missing), show_alert=True)
    raise _stop()


# ═══════════ لیدربورد (۵ نفر اول + رتبه خودت) ═══════════
async def _leaderboard_text(uid: int) -> str:
    excl, args = "", ()
    if _banned:
        ids = list(_banned)[:2000]
        excl = f" WHERE user_id NOT IN ({','.join(['%s'] * len(ids))})"
        args = tuple(ids)
    top = await _fetch(f"SELECT user_id, first_name, balance + bank_balance AS w FROM users{excl} "
                       "ORDER BY w DESC LIMIT 5", args)
    me = await _fetch("SELECT balance + bank_balance AS w FROM users WHERE user_id=%s", (uid,), one=True)
    my_w = int(me["w"] or 0) if me else 0
    where = "WHERE balance + bank_balance > %s" + (excl.replace(" WHERE", " AND") if excl else "")
    r = await _fetch(f"SELECT COUNT(*) AS c FROM users {where}", (my_w, *args), one=True)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    lines = [f"{medals[i]} {_esc((row['first_name'] or 'بی‌نام')[:20])}{' 👈' if int(row['user_id']) == uid else ''}"
             f" — <b>{_fmt(row['w'])}</b>" for i, row in enumerate(top)]
    return ("🏆 <b>ثروتمندترین‌های زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "—")
            + f"\n━━━━━━━━━━━━━━━━━━\n👤 رتبه‌ی تو: <b>{_fmt(int(r['c']) + 1)}</b>\n💰 ثروت تو: <b>{_fmt(my_w)}</b>"
            "\n<i>(ثروت = موجودی + بانک)</i>")


async def _h_lb_cb(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    q = update.callback_query
    if _not_owner(q):
        await _utils.safe_answer(q, "❌ این منو برای شما نیست!\nبرای منوی خودت /menu را بفرست.", show_alert=True)
        raise _stop()
    if not await _utils.verify_membership(update, context):
        raise _stop()
    text = await _leaderboard_text(q.from_user.id)
    await _utils.safe_answer(q)
    m = await _utils.safe_edit(q, text, M([[B("🔄 بروزرسانی", callback_data="lb:menu")],
                                           [B("🔙 بازگشت", callback_data="menu:main")]]))
    if m:
        _utils.remember_owner(m, q.from_user.id)
    raise _stop()


# ═══════════ فروشگاه: منو و ورود از پیوی ═══════════
async def _shop_menu_content():
    from telegram import InlineKeyboardButton as B
    prods = await _shop_products()
    if prods:
        text = ("💎 <b>خرید کوین و لول</b>\n━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(f"• <b>{_esc(p['title'])}</b> — {_price_line(p)}" for p in prods)
                + "\n\n👇 محصول مورد نظر را انتخاب کن:")
        rows = [[B(f"💎 {p['title'][:40]}", callback_data=f"shop:p:{p['id']}")] for p in prods]
    else:
        text = "💎 <b>خرید کوین و لول</b>\n━━━━━━━━━━━━━━━━━━\n😔 فعلاً محصولی برای فروش موجود نیست."
        rows = []
    rows.append([B("🔙 بازگشت", callback_data="menu:main")])
    return text, rows


async def _h_start_shop(update, context):
    """/start shop → فروشگاه | /start webapp → لینک ورود کازینو (برای پروکسی/مرورگر)"""
    if not context.args:
        return
    arg = context.args[0].lower()
    if arg == "webapp":
        if _utils and not await _utils.verify_membership(update, context):
            raise _stop()
        await db.ensure_user(update.effective_user)
        base = (getattr(config, "WEBAPP_PUBLIC_URL", "") or "").rstrip("/")
        token = _utils.generate_browser_token(update.effective_user.id) \
            if _utils and hasattr(_utils, "generate_browser_token") else ""
        if not base or not token:
            await update.effective_message.reply_text(
                "⚠️ لینک ورود هنوز تنظیم نشده — از دکمه‌ی «🎰 کازینو» در منوی ربات وارد شو.")
            raise _stop()
        await update.effective_message.reply_text(
            "🎲 <b>لینک ورود به کازینو</b>\n━━━━━━━━━━━━━━━━━━\n👇 روی دکمه بزن تا کازینو باز شود:\n"
            f"<a href=\"{base}/?token={token}\">🎰 ورود به کازینو زر</a>\n\n"
            "🔗 این لینک مخصوص توست و ۳۰ روز اعتبار دارد.",
            parse_mode="HTML")
        raise _stop()
    if arg != "shop":
        return
    from telegram import InlineKeyboardMarkup as M
    if _utils and not await _utils.verify_membership(update, context):
        raise _stop()
    await db.ensure_user(update.effective_user)
    text, rows = await _shop_menu_content()
    m = await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=M(rows))
    if _utils:
        _utils.remember_owner(m, update.effective_user.id)
    raise _stop()


# ═══════════════════════════════════════════════
# ═══════════ انبار بازار سیاه (جایگزین اینونتوری) ═══════════
# ═══════════════════════════════════════════════
async def _build_warehouse_text(uid: int) -> str:
    lvl = await _wh_level(uid)
    vip = await _is_vip(uid)
    cap = _wh_capacity(lvl, vip)
    rows = await _fetch("SELECT item_key, COUNT(*) AS c FROM inventory WHERE user_id=%s GROUP BY item_key", (uid,))
    counts = {r["item_key"]: int(r["c"]) for r in rows}
    lines = [f"🏭 <b>انبار من</b> — لول {lvl}/۱۰", "━━━━━━━━━━━━━━━━━━",
             f"📦 ظرفیت هر مهمات: <b>{cap} عدد</b>" + (" (👑 VIP: +۵)" if vip else ""),
             f"🚀 سقف هر وسیله شلیک: <b>{LAUNCHER_MAX_VIP if vip else LAUNCHER_MAX} عدد</b>"]
    if lvl < WH_MAX_LEVEL:
        lines.append(f"⬆️ هزینه ارتقا به لول {lvl + 1}: <b>{_fmt(_wh_upgrade_cost(lvl))}</b> زرکوین")
    else:
        lines.append("🏭 انبار در حداکثر لول است!")
    lines.append("")
    projs = [(k, v) for k, v in _bm_items().items() if v.get("type") == "projectile" and counts.get(k, 0) > 0]
    if projs:
        lines.append("📦 مهمات داخل انبار:")
        for k, v in projs:
            lines.append(f" {v['emoji']} {v['name']}: {counts[k]}/{cap}")
    else:
        lines.append("📭 هنوز مهماتی در انبار نیست.")
    return "\n".join(lines)


def _warehouse_kb():
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    return M([[B("⬆️ ارتقای انبار", callback_data="wh:upgrade")],
              [B("🔙 بازگشت به بازار سیاه", callback_data="bm:menu:0")]])


async def _h_wh_upgrade(update, context):
    """ارتقای انبار — هزینه: ۲^لول فعلی × ۱٬۰۰۰٬۰۰۰ زرکوین"""
    q = update.callback_query
    if _not_owner(q):
        await _utils.safe_answer(q, "❌ این منو برای شما نیست!\nبرای منوی خودت /menu را بفرست.", show_alert=True)
        raise _stop()
    if not await _utils.verify_membership(update, context):
        raise _stop()
    uid = q.from_user.id
    lvl = await _wh_level(uid)
    if lvl >= WH_MAX_LEVEL:
        await _utils.safe_answer(q, "🏭 انبار در حداکثر لول (۱۰) است!", show_alert=True)
        raise _stop()
    cost = _wh_upgrade_cost(lvl)
    if not await db.deduct_balance(uid, cost):
        await _utils.safe_answer(q, f"❌ موجودی کافی نیست!\nهزینه ارتقا: {_fmt(cost)} زرکوین", show_alert=True)
        raise _stop()
    await _exec("UPDATE users SET warehouse_level=%s WHERE user_id=%s", (lvl + 1, uid))
    _invalidate(uid)
    m = await _utils.safe_edit(q, await _build_warehouse_text(uid), _warehouse_kb())
    if m:
        _utils.remember_owner(m, uid)
    await _utils.safe_answer(q, f"✅ انبار به لول {lvl + 1} ارتقا یافت!", show_alert=True)
    raise _stop()


# ═══════════════════════════════════════════════
# ═══════════ قفل برداشت بانک (۵ ساعت بعد از واریز) ═══════════
# ═══════════════════════════════════════════════
_orig_bank_deposit = None
_orig_bank_withdraw = None
_orig_accrue = None
_orig_peek = None


async def _bank_deposit_locked(uid, amount, *a, **k):
    ok = await _orig_bank_deposit(uid, amount, *a, **k)
    if ok:
        try:
            await _ensure_tables()
            await _exec("UPDATE users SET last_bank_deposit=%s WHERE user_id=%s", (time.time(), uid))
        except Exception:
            pass
    return ok


async def _bank_withdraw_locked(uid, amount, *a, **k):
    try:
        await _ensure_tables()
        r = await _fetch("SELECT last_bank_deposit FROM users WHERE user_id=%s", (uid,), one=True)
        last = float(r["last_bank_deposit"]) if r and r["last_bank_deposit"] else 0
        if last and time.time() - last < BANK_LOCK_SECONDS:
            return False
    except Exception:
        pass
    return await _orig_bank_withdraw(uid, amount, *a, **k)


_bank_deposit_locked._zar = True
_bank_withdraw_locked._zar = True


async def _h_bank_lock(update, context):
    """پیام قشنگ برای برداشت قفل‌شده (قبل از هندلر متنی bot.py)"""
    msg = update.effective_message
    if not msg or not msg.text or not _utils:
        return
    state = _utils.user_states.get(update.effective_user.id)
    if not state or state.get("action") != "bank_withdraw":
        return
    uid = update.effective_user.id
    try:
        await _ensure_tables()
        r = await _fetch("SELECT last_bank_deposit FROM users WHERE user_id=%s", (uid,), one=True)
        last = float(r["last_bank_deposit"]) if r and r["last_bank_deposit"] else 0
    except Exception:
        return
    remain = BANK_LOCK_SECONDS - (time.time() - last)
    if remain <= 0:
        return
    _utils.user_states.pop(uid, None)
    mins = max(1, math.ceil(remain / 60))
    await msg.reply_text(
        "🔒 <b>برداشت از بانک قفل است</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"بعد از واریز به بانک، تا <b>{BANK_LOCK_SECONDS // 3600} ساعت</b> نمی‌توانی برداشت کنی.\n"
        f"⏳ زمان باقی‌مانده: <b>{mins} دقیقه</b>")
    raise _stop()


# ═══════════════════════════════════════════════
# ═══════════ بونوس VIP روی درآمد ═══════════
# ═══════════════════════════════════════════════
async def _vip_bonus(uid, asset_income: int, bank_balance: int):
    """+۱۰٪ درآمد ملک/کارگر و +۳٪ سود بانک (مجموع ۵٪ به‌جای ۲٪)"""
    try:
        if not await _is_vip(uid):
            return 0, 0
        return int(asset_income * 0.10), int(bank_balance * 0.03)
    except Exception:
        return 0, 0


async def _accrue_vip(uid, *a, **k):
    res = await _orig_accrue(uid, *a, **k)
    try:
        if not res or len(res) < 3:
            return res
        asset_income, bank_interest, total = int(res[0] or 0), int(res[1] or 0), int(res[2] or 0)
        u = await db.get_user(uid)
        bank = int(u["bank_balance"] or 0) if u else 0
        b_asset, b_bank = await _vip_bonus(uid, asset_income, bank)
        bonus = b_asset + b_bank
        if bonus > 0:
            await db.add_balance(uid, bonus)
            res = (asset_income + b_asset, bank_interest + b_bank, total + bonus)
    except Exception:
        logger.exception("vip accrue bonus error")
    return res


async def _peek_vip(uid, *a, **k):
    res = await _orig_peek(uid, *a, **k)
    try:
        if not res or len(res) < 3:
            return res
        asset_income, bank_interest, total = int(res[0] or 0), int(res[1] or 0), int(res[2] or 0)
        u = await db.get_user(uid)
        bank = int(u["bank_balance"] or 0) if u else 0
        b_asset, b_bank = await _vip_bonus(uid, asset_income, bank)
        res = (asset_income + b_asset, bank_interest + b_bank, total + b_asset + b_bank)
    except Exception:
        logger.exception("vip peek bonus error")
    return res


_accrue_vip._zar = True
_peek_vip._zar = True


# ═══════════ سرور ═══════════
_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; connect-src 'self'")


@web.middleware
async def _security_mw(request: web.Request, handler):
    resp = web.Response(status=204) if request.method == "OPTIONS" else await handler(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith(("/api/", "/admin")):
        resp.headers["Cache-Control"] = "no-store"
    if request.path.startswith("/admin"):
        resp.headers["X-Frame-Options"] = "DENY"
    if not request.path.startswith("/api/"):
        resp.headers["Content-Security-Policy"] = _CSP
    return resp


async def handle_index(request):
    try:
        html = MINIAPP_HTML.read_text(encoding="utf-8")
    except FileNotFoundError:
        return web.Response(text="miniapp.html not found", status=500)
    try:
        s = await _get_settings()
        theme = {k[6:]: v for k, v in s.items() if k.startswith("theme:") and re.fullmatch(r"#[0-9a-fA-F]{6}", v or "")}
        if theme:
            css = ":root{" + "".join(f"--{k}:{v};" for k, v in theme.items()) + "}"
            html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    except Exception:
        pass
    return web.Response(text=html, content_type="text/html", charset="utf-8", headers={"Cache-Control": "no-cache"})


async def handle_health(request):
    return _json({"ok": True, "redis": _redis_on(), "games": len(_active_games), "queue": len(_waiting)})


async def handle_config(request):
    """اطلاعات عمومی برای صفحه‌ی ورود مینی‌اپ (بدون احراز هویت) — نام کاربری ربات برای ساخت لینک ورود"""
    un = ""
    if _bot_app:
        try:
            un = _bot_app.bot.username or ""
        except Exception:
            un = ""
    if not un:
        m = re.search(r"t\.me/([A-Za-z0-9_]+)", getattr(config, "WEBAPP_DEEP_LINK", "") or "")
        un = m.group(1) if m else ""
    return _json({"ok": True, "bot_username": un,
                  "webapp_url": (getattr(config, "WEBAPP_PUBLIC_URL", "") or "").rstrip("/")})


def create_app() -> web.Application:
    app = web.Application(middlewares=[_security_mw], client_max_size=128 * 1024)
    for path in ("/", "/miniapp", "/webapp", "/casino", "/app"):
        app.router.add_get(path, handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/admin", admin_page)
    app.router.add_get("/admin/", admin_page)
    admin_routes = {
        "stats": admin_stats, "search": admin_search, "user": admin_user, "adjust": admin_adjust,
        "gifts/list": admin_gifts_list, "gifts/create": admin_gifts_create,
        "gifts/toggle": admin_gifts_toggle, "gifts/delete": admin_gifts_delete,
        "shop/products": admin_shop_products, "shop/save": admin_shop_save, "shop/toggle": admin_shop_toggle,
        "shop/delete": admin_shop_delete, "shop/orders": admin_shop_orders, "shop/approve": admin_shop_approve,
        "shop/reject": admin_shop_reject, "shop/settings": admin_shop_settings,
        "ban": admin_ban, "unban": admin_unban, "bot/toggle": admin_bot_toggle,
        "admins/list": admin_admins_list, "admins/add": admin_admins_add, "admins/remove": admin_admins_remove,
        "vip/list": admin_vip_list, "settings/get": admin_settings_get, "settings/save": admin_settings_save,
    }
    for p, h in admin_routes.items():
        app.router.add_post(f"/admin/api/{p}", h)
    app.router.add_get("/admin/receipt/{oid}", admin_receipt)
    routes = {
        "/api/me": api_me, "/api/balance": api_balance, "/api/solo/state": api_solo_state,
        "/api/solo/mines/start": api_mines_start, "/api/solo/mines/reveal": api_mines_reveal,
        "/api/solo/mines/cashout": api_mines_cashout, "/api/solo/hilo/start": api_hilo_start,
        "/api/solo/hilo/guess": api_hilo_guess, "/api/solo/hilo/cashout": api_hilo_cashout,
        "/api/match/join": api_match_join, "/api/match/cancel": api_match_cancel,
        "/api/match/status": api_match_status, "/api/game/state": api_game_state,
        "/api/game/action": api_game_action, "/api/game/leave": api_game_leave,
    }
    for p, h in routes.items():
        app.router.add_post(p, h)
    app.router.add_post("/api/solo/{game}", api_solo_instant)  # چرخ، موشک، سکه، کارت، رولت، پنالتی
    return app


_runner: web.AppRunner | None = None
_sweeper_task: asyncio.Task | None = None


async def start_webapp(*args, **kwargs):
    global _runner, _sweeper_task
    if _runner is not None:
        return _runner
    try:
        if not _redis_on():
            await redis_client.init_redis()
    except Exception as e:
        logger.warning(f"⚠️ init_redis ناموفق: {e}")
    port = int(kwargs.get("port") or getattr(config, "WEBAPP_PORT", 8080))
    runner = web.AppRunner(create_app(), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, kwargs.get("host") or "0.0.0.0", port).start()
    except OSError as e:
        await runner.cleanup()
        logger.error(f"❌ پورت {port} آزاد نیست (احتمالاً سرور قبلاً بالا آمده): {e}")
        if _sweeper_task is None:
            _sweeper_task = asyncio.create_task(_sweeper())
        return None
    _runner = runner
    _sweeper_task = asyncio.create_task(_sweeper())
    if ADMIN_PASSWORD == "admin":
        logger.warning("⚠️ رمز پنل مدیریت پیش‌فرض (admin) است — متغیر ADMIN_PASSWORD را تنظیم کن!")
    logger.info(f"🎲 مینی‌اپ و پنل مدیریت روی پورت {port} اجرا شد (Redis: {'✅' if _redis_on() else '❌'})")
    return _runner


async def stop_webapp(*args, **kwargs):
    global _runner, _sweeper_task
    if _sweeper_task:
        _sweeper_task.cancel()
        try:
            await _sweeper_task
        except (asyncio.CancelledError, Exception):
            pass
        _sweeper_task = None
    try:
        for uid, w in list(_waiting.items()):
            await _queue_remove(uid)
            await db.add_balance(uid, w["bet"])
        for g in list(_active_games.values()):
            if not g.finished:
                await _settle(g, None, "سرور ری‌استارت شد — پول برگشت داده شد")
        for uid in list(_solo_sessions):
            await _close_solo_session(uid)
    except Exception:
        logger.exception("refund on shutdown failed")
    if _runner is not None:
        try:
            await _runner.cleanup()
        except Exception:
            pass
        _runner = None


# نام‌های جایگزین برای سازگاری با bot.py
start_server = start_webapp_server = run_webapp = init_webapp = start_webapp
stop_server = stop_webapp_server = shutdown_webapp = close_webapp = stop_webapp
build_app = make_app = create_app


def __getattr__(name):
    """هر تابع قدیمی دیگری که bot.py صدا بزند → بی‌اثر (به‌جای کرش)"""
    if name.startswith("__"):
        raise AttributeError(name)

    async def _noop(*a, **k):
        logger.warning(f"webapp.{name} دیگر وجود ندارد — نادیده گرفته شد")
    return _noop
