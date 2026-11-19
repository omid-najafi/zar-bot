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
MAX_BET = int(os.getenv("MINIAPP_MAX_BET") or getattr(config, "MINIAPP_MAX_BET", 100_000_000))
FINISHED_GAME_TTL = 180
SOLO_SESSION_TTL = 3600
SWEEP_INTERVAL = 3
LAUNCH_COOLDOWN = int(getattr(config, "LAUNCH_COOLDOWN_SECONDS", 3600))  # خنک شدن هر وسیله شلیک
MAX_LEVEL = 50

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
    cfg = getattr(config, "MINIAPP_GAMES", {}) or {}
    games = {}
    for key, g in _DEFAULT_GAMES.items():
        merged = dict(g)
        src = cfg.get(key) or (cfg.get("poker") if key == "holdem" else None)
        if isinstance(src, dict) and isinstance(src.get("min_bet"), int) and src["min_bet"] > 0:
            merged["min_bet"] = src["min_bet"]
        merged["max_bet"] = max(MAX_BET, merged["min_bet"])
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


async def _track_async(uid: int, game_key: str, solo: bool, won: bool):
    try:
        mk = _MISSION_KEYS.get(game_key) or ("casino" if solo else None)
        await db.progress_mission(uid, "play_any_game", 1, base_xp=getattr(config, "BASE_XP_PLAY_GAME", 15))
        if mk:
            await db.progress_mission(uid, f"play_{mk}", 1, base_xp=0)
        if won:
            await db.progress_mission(uid, "win_any_game", 1, base_xp=getattr(config, "BASE_XP_WIN_GAME", 30))
            if mk:
                await db.progress_mission(uid, f"win_{mk}", 1, base_xp=0)
    except Exception as e:
        logger.debug(f"progress_mission ناموفق: {e}")


def _track(uid: int, game_key: str, solo: bool, won: bool):
    _spawn(_track_async(uid, game_key, solo, won))


async def _take_bet(uid: int, game_key: str, bet) -> str | None:
    g = GAMES.get(game_key)
    if not g:
        return "بازی نامعتبر است"
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
                try:
                    await cur.execute("ALTER TABLE inventory ADD COLUMN last_used DOUBLE NULL DEFAULT NULL")
                except Exception:
                    pass  # ستون از قبل وجود دارد
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


GRANT_KINDS = ("coins", "bank", "xp", "levels", "property", "worker", "item")


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
        if info.get("type") == "defense":
            await cur.execute("SELECT COUNT(*) AS c FROM inventory WHERE user_id=%s AND item_key=%s", (uid, key))
            add = max(0, min(n, 1 - int((await cur.fetchone())["c"])))
        for _ in range(add):
            await cur.execute("INSERT INTO inventory (user_id, item_key, purchased_at) VALUES (%s,%s,%s)",
                              (uid, key, _now_iso()))
        return add
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
    if tg and tg.get("first_name"):
        user["first_name"] = tg["first_name"]
    return user


def _auth(handler):
    async def wrapper(request: web.Request):
        user = await _get_user_for_request(request)
        if not user:
            return _err("احراز هویت ناموفق بود — مینی‌اپ را از داخل ربات باز کن", 401, "auth")
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
        _track(uid, key, True, win > bet)
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
    _track(uid, key, True, amount > s["bet"])


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
        _track(uid, g.game_key, False, uid == winner)


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
        "games": [dict(key=k, **v) for k, v in GAMES.items()], "commission": COMMISSION_RATE,
        "match_timeout": MATCH_TIMEOUT, "turn_timeout": TURN_TIMEOUT, "max_bet": MAX_BET,
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
    u = await _fetch("SELECT user_id, username, first_name, balance, bank_balance, total_xp, level, card_number, "
                     "created_at FROM users WHERE user_id=%s", (uid,), one=True)
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
        "in_game": uid in _user_games, "in_queue": uid in _waiting,
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
        "level": _calc_level(int(r["total_xp"] or 0))} for r in rows]})


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
    n1 = sum(1 for g in GAMES.values() if g["type"] == "1p")
    n2 = sum(1 for g in GAMES.values() if g["type"] == "2p")
    return ("🎰 <b>کازینو زر</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🎯 {n1} بازی تک‌نفره | ⚔️ {n2} بازی دونفره آنلاین\n"
            f"💰 حداکثر شرط: {_fmt(MAX_BET)}\n\n👇 برای ورود به کازینو بزن:")


def patch_bot_ui():
    """منوی اصلی: حذف «🎮 بازی‌ها» و افزودن «🎰 کازینو» (مینی‌اپ) + به‌روزرسانی راهنما"""
    if _utils:
        from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

        def build_main_menu_kb():
            return M([
                [B("🏦 بانک", callback_data="bank:menu"), B("🏠 ملک‌ها", callback_data="prop:menu")],
                [B("👷 کارگرها", callback_data="worker:menu"), casino.miniapp_button("🎰 کازینو")],
                [B("🎯 ماموریت‌ها", callback_data="mission:menu"), B("💸 انتقال", callback_data="transfer:start")],
                [B("🎭 کاباره زر", callback_data="kabareh:menu"), B("🏆 لیدربورد", callback_data="lb:menu")],
                [B("💀 بازار سیاه", callback_data="bm:menu:0"), B("💎 خرید کوین و لول", callback_data="shop:menu")],
                [B("📚 راهنما", callback_data="help:menu")],
            ])

        _utils.build_main_menu_kb = build_main_menu_kb
        _utils.MAIN_MENU_KB = build_main_menu_kb()
        _utils.GAMES_MENU_KB = casino.miniapp_keyboard()
        _utils.BACK_GAMES_KB = M([[B("🔙 بازگشت", callback_data="menu:main")]])
    # تخریب حمله: پول + ملک/کارگر تصادفی (bot.py همین db.apply_damage را صدا می‌زند)
    global _orig_apply_damage
    if not getattr(getattr(db, "apply_damage", None), "_zar", False):
        _orig_apply_damage = getattr(db, "apply_damage", None)
        db.apply_damage = apply_damage_split
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


async def _h_bm_guard(update, context):
    """از هر سیستم دفاعی فقط ۱ عدد"""
    q = update.callback_query
    parts = (q.data or "").split(":")
    key = parts[2] if len(parts) > 2 else ""
    if key not in _defense_keys():
        return
    uid = q.from_user.id
    if q.message and _utils and not _utils.is_menu_owner(q.message.chat_id, q.message.message_id, uid):
        return
    try:
        have = await _count_items(uid, key)
    except Exception:
        return
    if have >= 1:
        try:
            await q.answer("🛡️ از هر سیستم دفاعی فقط ۱ عدد می‌تونی داشته باشی و الان یکی داری!", show_alert=True)
        except Exception:
            pass
        raise _stop()


async def _h_bm_post(update, context):
    """اطمینان نهایی: اگر به هر دلیلی بیش از ۱ پدافند ثبت شد، اضافه حذف و پولش برمی‌گردد"""
    q = update.callback_query
    parts = (q.data or "").split(":")
    key = parts[2] if len(parts) > 2 else ""
    if key not in _defense_keys():
        return
    uid = q.from_user.id
    try:
        have = await _count_items(uid, key)
        if have > 1:
            removed = await _exec("DELETE FROM inventory WHERE user_id=%s AND item_key=%s ORDER BY id DESC LIMIT %s",
                                  (uid, key, have - 1))
            refund = removed * int(_bm_items()[key]["price"])
            if refund:
                await db.add_balance(uid, refund)
                await context.bot.send_message(q.message.chat_id if q.message else uid,
                                               f"🛡️ از هر سیستم دفاعی فقط ۱ عدد مجاز است — {_fmt(refund)} برگشت داده شد.")
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
    launchers = [k for k, v in _bm_items().items() if v.get("type") == "launcher" and proj in v.get("launches", [])]
    if not launchers:
        return
    uid = update.effective_user.id
    try:
        await _ensure_tables()
        ph = ",".join(["%s"] * len(launchers))
        rows = await _fetch(f"SELECT id, item_key, last_used FROM inventory WHERE user_id=%s AND item_key IN ({ph})",
                            (uid, *launchers))
        if not rows or await _count_items(uid, proj) <= 0:
            return  # هندلر اصلی پیام «وسیله/مهمات نداری» را می‌دهد
        proj_count = await _count_items(uid, proj)
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
    from telegram.ext import CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters
    patch_bot_ui()
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\s*هدیه\s*زر(\s+\S+)?\s*$"), _h_gift), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\s*(کازینو\s*زربات|زر\s*بازی)\s*$"),
                                   _h_casino_text), group=-2)
    app.add_handler(CallbackQueryHandler(_h_help_cb, pattern=r"^help:(menu|p:\d+)$"), group=-2)
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
        except Exception:
            logger.exception("ساخت جداول جدید ناموفق")

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
    درصد تخریب از کل ثروت هدف (کیف پول + بانک + ارزش خرید ملک‌ها و کارگرها) حساب می‌شود
    و به‌صورت تصادفی بین پول و دارایی‌ها تقسیم می‌شود. ملک/کارگرهای نابودشده تصادفی انتخاب می‌شوند.
    خروجی: ارزش کل خسارت (برای پیام bot.py)
    """
    try:
        pct = max(0.0, min(float(damage_percent), 1.0))
        target_id = int(target_id)
    except (TypeError, ValueError):
        return 0
    if pct <= 0:
        return 0

    async def run(cur):
        await cur.execute("SELECT balance, bank_balance FROM users WHERE user_id=%s FOR UPDATE", (target_id,))
        u = await cur.fetchone()
        if not u:
            return None
        bal, bank = max(0, int(u["balance"] or 0)), max(0, int(u["bank_balance"] or 0))
        await cur.execute("SELECT id, asset_type, asset_key, purchase_price FROM assets WHERE user_id=%s FOR UPDATE",
                          (target_id,))
        assets = list(await cur.fetchall())
        cash = bal + bank
        total = cash + sum(int(a["purchase_price"] or 0) for a in assets)
        dmg = int(total * pct)
        if dmg <= 0:
            return None
        if not assets:
            money_part = dmg
        elif cash <= 0:
            money_part = 0
        else:
            money_part = int(dmg * _rng.uniform(0.25, 0.75))  # سهم تصادفی پول
        budget = dmg - money_part
        _rng.shuffle(assets)
        removed, left = [], []
        for a in assets:
            price = int(a["purchase_price"] or 0)
            if price <= budget:
                removed.append(a)
                budget -= price
            else:
                left.append(a)
        # باقی‌مانده‌ی بودجه: با احتمال متناسب یک دارایی گران‌تر هم نابود می‌شود
        if budget > 0 and left:
            c = _rng.choice(left)
            price = int(c["purchase_price"] or 1)
            if _rng.random() < budget / price:
                removed.append(c)
                budget = 0
        money_part = min(cash, money_part + budget)
        from_bal = min(bal, money_part)
        from_bank = money_part - from_bal
        await cur.execute("UPDATE users SET balance = balance - %s, bank_balance = bank_balance - %s WHERE user_id=%s",
                          (from_bal, from_bank, target_id))
        if removed:
            ids = [int(a["id"]) for a in removed]
            await cur.execute(f"DELETE FROM assets WHERE id IN ({','.join(['%s'] * len(ids))})", ids)
        asset_value = sum(int(a["purchase_price"] or 0) for a in removed)
        return {"money": money_part, "assets": [(a["asset_type"], a["asset_key"]) for a in removed],
                "asset_value": asset_value, "total": money_part + asset_value}

    try:
        res = await _tx(run)
    except Exception:
        logger.exception("apply_damage_split error — استفاده از نسخه قدیمی")
        if _orig_apply_damage:
            return await _orig_apply_damage(target_id, damage_percent, *args, **kwargs)
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
          f"🏠 <b>ملک‌ها</b> و 👷 <b>کارگرها:</b> حداکثر {getattr(c, 'MAX_PER_KEY', 5)} از هر نوع — سود روزانه ۳۵٪\n"
          "💸 <b>برداشت درآمد:</b> از بخش ملک یا کارگر، درآمد انباشته را برداشت کن\n"
          "💸 <b>انتقال:</b> بالای ۱ میلیون کارمزد ۱٪\n"
          "🔒 هر کاربر فقط می‌تواند از منوی خودش استفاده کند")
    p2 = ("🎰 <b>راهنما — کازینو (مینی‌اپ)</b>\n━━━━━━━━━━━━━━━━━━\n"
          "از منوی اصلی روی «🎰 کازینو» بزن یا بنویس <b>کازینو زربات</b>\n\n"
          f"🎯 <b>تک‌نفره ({len(one)}):</b>\n" + "، ".join(f"{g['emoji']} {g['name']}" for g in one) + "\n\n"
          f"⚔️ <b>دونفره آنلاین ({len(two)}):</b>\n" + "، ".join(f"{g['emoji']} {g['name']}" for g in two) + "\n\n"
          f"💰 حداکثر شرط: {_fmt(MAX_BET)} زرکوین\n"
          f"⏳ یافتن حریف: حداکثر {MATCH_TIMEOUT} ثانیه (وگرنه پول برمی‌گردد)\n"
          f"⏰ زمان هر نوبت: {TURN_TIMEOUT} ثانیه\n"
          f"💵 کارمزد برنده‌ی دونفره: {int(COMMISSION_RATE * 100)}٪ — مساوی = برگشت کامل پول")
    p3 = ("💎 <b>راهنما — فروشگاه، هدیه و سرگرمی</b>\n━━━━━━━━━━━━━━━━━━\n"
          "💎 <b>خرید کوین و لول:</b> از منوی اصلی محصول را انتخاب کن و با ⭐ استارز تلگرام یا 💳 کارت به کارت بپرداز. "
          "خرید کارت به کارت بعد از تأیید رسید توسط مدیر تحویل می‌شود.\n\n"
          "🎁 <b>کد هدیه:</b> بنویس <code>هدیه زر کد</code> — از هر کد فقط یک بار\n\n"
          f"🎭 <b>کاباره زر:</b> نیاز به لول {getattr(c, 'KABAREH_MIN_LEVEL', 4)}+ | "
          f"باز کردن با {_fmt(getattr(c, 'KABAREH_UNLOCK_COST', 0))} | روزی یک بار\n\n"
          "🏆 <b>لیدربورد:</b> رتبه‌بندی بر اساس ثروت (موجودی + بانک)")
    p4 = ("💀 <b>راهنما — بازار سیاه</b>\n━━━━━━━━━━━━━━━━━━\n"
          f"🚀 <b>وسایل شلیک</b> (الزامی برای شلیک — تعداد نامحدود):\n{items('launcher')}\n\n"
          f"💥 <b>مهمات</b> (مصرفی):\n{items('projectile')}\n\n"
          f"🛡️ <b>دفاعی</b> (از هر کدام فقط ۱ عدد):\n{items('defense')}")
    p5 = ("🎯 <b>راهنما — حمله و دفاع</b>\n━━━━━━━━━━━━━━━━━━\n"
          "۱. وسیله شلیک و مهمات را از بازار سیاه بخر\n۲. روی پیام هدف ریپلای کن\n۳. دستور شلیک را بفرست:\n"
          + cmds + "\n\n⚠️ <b>قوانین:</b>\n"
          f" • هر وسیله شلیک بعد از شلیک {LAUNCH_COOLDOWN // 60} دقیقه خنک می‌شود؛ با چند وسیله می‌توانی پشت‌سرهم شلیک کنی\n"
          " • درصد تخریب از کل ثروت هدف (پول + بانک + ارزش ملک‌ها و کارگرها) است و تصادفی بین پول و "
          "ملک/کارگرها تقسیم می‌شود؛ ملک و کارگرهای نابودشده تصادفی انتخاب می‌شوند\n"
          " • بمب‌ها قابل دفاع نیستند، فقط موشک و پهباد\n"
          " • هر شلیک یک مهمات مصرف می‌کند")
    return [p1, p2, p3, p4, p5]


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
def _owner_ids() -> set:
    ids = {int(getattr(config, "OWNER_ID", 0) or 0)}
    for x in (os.getenv("SHOP_ADMIN_IDS") or "").split(","):
        if x.strip().isdigit():
            ids.add(int(x.strip()))
    ids.discard(0)
    return ids


async def _get_setting(k: str, default: str = "") -> str:
    await _ensure_tables()
    r = await _fetch("SELECT v FROM zar_settings WHERE k=%s", (k,), one=True)
    return (r["v"] if r else "") or default


async def _set_setting(k: str, v: str):
    await _ensure_tables()
    await _exec("INSERT INTO zar_settings (k, v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)", (k, v))


def _clean_rewards(raw) -> tuple:
    raw = raw if isinstance(raw, dict) else {}
    rewards = {}
    for k in ("coins", "bank", "xp", "levels"):
        n = _to_int(raw.get(k), 0) or 0
        if n < 0 or n > 10 ** 15:
            return None, "مقدار جایزه نامعتبر است"
        if n:
            rewards[k] = min(n, MAX_LEVEL) if k == "levels" else n
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

    if act == "menu":
        if not await _utils.verify_membership(update, context):
            raise _stop()
        prods = await _shop_products()
        await _utils.safe_answer(q)
        if prods:
            text = ("💎 <b>خرید کوین و لول</b>\n━━━━━━━━━━━━━━━━━━\n"
                    + "\n".join(f"• <b>{_esc(p['title'])}</b> — {_price_line(p)}" for p in prods)
                    + "\n\n👇 محصول مورد نظر را انتخاب کن:")
            rows = [[B(f"💎 {p['title'][:40]}", callback_data=f"shop:p:{p['id']}")] for p in prods]
        else:
            text = "💎 <b>خرید کوین و لول</b>\n━━━━━━━━━━━━━━━━━━\n😔 فعلاً محصولی برای فروش موجود نیست."
            rows = []
        rows.append([B("🔙 بازگشت", callback_data="menu:main")])
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
            await _utils.safe_answer(q, "🧾 فاکتور در پیوی ربات برایت ارسال شد", show_alert=True)
        except Exception:
            try:
                await context.bot.send_invoice(chat_id=q.message.chat_id, **kw)
                await _utils.safe_answer(q)
            except Exception as e:
                logger.warning(f"send_invoice ناموفق: {e}")
                await _utils.safe_answer(q, "❌ ارسال فاکتور ناموفق بود — اول ربات را در پیوی استارت کن", show_alert=True)
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
        rows = []
        if context.bot.username:
            rows.append([B("📸 ارسال رسید در پیوی ربات", url=f"https://t.me/{context.bot.username}")])
        rows.append([B("❌ لغو سفارش", callback_data=f"shop:cancel:{oid}")])
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
    return web.Response(text=html, content_type="text/html", charset="utf-8", headers={"Cache-Control": "no-cache"})


async def handle_health(request):
    return _json({"ok": True, "redis": _redis_on(), "games": len(_active_games), "queue": len(_waiting)})


def create_app() -> web.Application:
    app = web.Application(middlewares=[_security_mw], client_max_size=128 * 1024)
    for path in ("/", "/miniapp", "/webapp", "/casino", "/app"):
        app.router.add_get(path, handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/admin", admin_page)
    app.router.add_get("/admin/", admin_page)
    admin_routes = {
        "stats": admin_stats, "search": admin_search, "user": admin_user, "adjust": admin_adjust,
        "gifts/list": admin_gifts_list, "gifts/create": admin_gifts_create,
        "gifts/toggle": admin_gifts_toggle, "gifts/delete": admin_gifts_delete,
        "shop/products": admin_shop_products, "shop/save": admin_shop_save, "shop/toggle": admin_shop_toggle,
        "shop/delete": admin_shop_delete, "shop/orders": admin_shop_orders, "shop/approve": admin_shop_approve,
        "shop/reject": admin_shop_reject, "shop/settings": admin_shop_settings,
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
