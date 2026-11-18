# -*- coding: utf-8 -*-
"""
🎲 سرور مینی‌اپ قمارخانه زر (Telegram WebApp)
─────────────────────────────────────────────
- اعتبارسنجی initData تلگرام (HMAC) + توکن مرورگر
- مچ‌میکینگ با تایم‌اوت برای بازی‌های دونفره (Redis یا حافظه)
- بازی‌های تک‌نفره: چرخ شانس، موشک (کرش)، مین‌یاب، بالا/پایین، شیر یا خط
- بازی‌های دونفره: پوکر تگزاس هولدم، حکم، بلک‌جک، چهار در یک ردیف، سنگ کاغذ قیچی، دوز
- همه‌ی منطق بازی سمت سرور است (کلاینت فقط نمایش می‌دهد) → تقلب‌ناپذیر
- escrow: شرط هنگام ورود به صف کم می‌شود و در لغو/تایم‌اوت/خاموشی سرور برمی‌گردد
"""
import asyncio
import base64
import hashlib
import hmac
import itertools
import json
import logging
import math
import random
import secrets
import time
import urllib.parse
from pathlib import Path

from aiohttp import web

import config
import db
import redis_client

try:
    import utils as _utils
except Exception:  # pragma: no cover
    _utils = None

logger = logging.getLogger("zarcoin.webapp")

# ═══════════ مسیرها ═══════════
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MINIAPP_HTML = TEMPLATES_DIR / "miniapp.html"

# ═══════════ تنظیمات ═══════════
_rng = random.SystemRandom()
COMMISSION_RATE = float(getattr(config, "MINIAPP_COMMISSION_RATE", 0.05))
MATCH_TIMEOUT = int(getattr(config, "MATCHMAKING_TIMEOUT", 60))
TURN_TIMEOUT = int(getattr(config, "MINIAPP_TURN_TIMEOUT", 45))
FINISHED_GAME_TTL = 180          # نگه‌داری بازی تمام‌شده برای نمایش نتیجه
SOLO_SESSION_TTL = 3600          # بازی تک‌نفره‌ی نیمه‌تمام بعد از ۱ ساعت بسته می‌شود
SWEEP_INTERVAL = 3

# ═══════════ لیست بازی‌ها ═══════════
# (اسلات و تاس حذف شدند — پوکر به تگزاس هولدم تبدیل شد)
_DEFAULT_GAMES = {
    # ─── تک‌نفره ───
    "wheel": {"name": "چرخ شانس", "emoji": "🎡", "type": "1p", "min_bet": 1_000, "max_bet": 2_000_000,
              "desc": "چرخ را بچرخان — تا ۵ برابر جایزه"},
    "crash": {"name": "موشک", "emoji": "🚀", "type": "1p", "min_bet": 1_000, "max_bet": 2_000_000,
              "desc": "ضریب هدف را انتخاب کن؛ موشک قبل از انفجار برسد برنده‌ای"},
    "mines": {"name": "مین‌یاب", "emoji": "💣", "type": "1p", "min_bet": 1_000, "max_bet": 2_000_000,
              "desc": "خانه‌های امن را باز کن و به‌موقع برداشت کن"},
    "hilo": {"name": "بالا پایین", "emoji": "🎴", "type": "1p", "min_bet": 1_000, "max_bet": 2_000_000,
             "desc": "کارت بعدی بالاتر است یا پایین‌تر؟ ضریب‌ها جمع می‌شوند"},
    "coin": {"name": "شیر یا خط", "emoji": "🪙", "type": "1p", "min_bet": 1_000, "max_bet": 5_000_000,
             "desc": "۵۰/۵۰ — برد ۱٫۹ برابر"},
    # ─── دونفره ───
    "holdem": {"name": "پوکر تگزاس هولدم", "emoji": "♠️", "type": "2p", "min_bet": 10_000, "max_bet": 10_000_000,
               "desc": "هدز‌آپ: ۲ کارت دست + ۵ کارت زمین، با کال/رِیز/فولد"},
    "hokm": {"name": "حکم", "emoji": "🃏", "type": "2p", "min_bet": 10_000, "max_bet": 10_000_000,
             "desc": "حکم دونفره — هر کس ۷ دست ببرد برنده است"},
    "blackjack": {"name": "بلک‌جک", "emoji": "🂡", "type": "2p", "min_bet": 5_000, "max_bet": 5_000_000,
                  "desc": "نزدیک‌تر به ۲۱ بدون سوختن برنده است"},
    "connect4": {"name": "چهار در یک ردیف", "emoji": "🔴", "type": "2p", "min_bet": 5_000, "max_bet": 5_000_000,
                 "desc": "اولین نفری که ۴ مهره پشت‌سرهم بچیند"},
    "rps": {"name": "سنگ کاغذ قیچی", "emoji": "✊", "type": "2p", "min_bet": 1_000, "max_bet": 5_000_000,
            "desc": "سه دست — هر کس ۲ دست ببرد"},
    "ttt": {"name": "دوز", "emoji": "⭕", "type": "2p", "min_bet": 1_000, "max_bet": 5_000_000,
            "desc": "سه در یک خط — کلاسیک دونفره"},
}


def _build_games() -> dict:
    """ادغام لیست پیش‌فرض با MINIAPP_GAMES در config (فقط min/max و نام قابل override است)"""
    cfg = getattr(config, "MINIAPP_GAMES", {}) or {}
    games = {}
    for key, g in _DEFAULT_GAMES.items():
        merged = dict(g)
        src = cfg.get(key) or (cfg.get("poker") if key == "holdem" and "holdem" not in cfg else None)
        if isinstance(src, dict):
            for f in ("min_bet", "max_bet"):
                v = src.get(f)
                if isinstance(v, int) and v > 0:
                    merged[f] = v
            if key in cfg:
                for f in ("name", "emoji", "desc"):
                    if src.get(f):
                        merged[f] = src[f]
        if merged["max_bet"] < merged["min_bet"]:
            merged["max_bet"] = merged["min_bet"]
        games[key] = merged
    return games


GAMES = _build_games()

# ═══════════ ساختار داده‌های درون‌حافظه‌ای ═══════════
_match_queues: dict[str, dict[int, "MatchEntry"]] = {}   # fallback وقتی Redis نیست
_waiting: dict[int, dict] = {}                            # کاربرانی که escrow دارند و در صف‌اند
_active_games: dict[str, "GameState"] = {}
_user_games: dict[int, str] = {}
_solo_sessions: dict[int, dict] = {}                      # مین‌یاب / بالا‌پایین
_user_locks: dict[int, asyncio.Lock] = {}
_matchmaking_lock = asyncio.Lock()
_bg_tasks: set = set()


def _ulock(uid: int) -> asyncio.Lock:
    lk = _user_locks.get(uid)
    if lk is None:
        lk = asyncio.Lock()
        _user_locks[uid] = lk
    return lk


class MatchEntry:
    """یک کاربر در صف انتظار برای حریف"""
    __slots__ = ("user_id", "name", "balance", "bet", "joined_at", "avatar")

    def __init__(self, user_id, name, balance, bet, avatar=""):
        self.user_id = user_id
        self.name = name
        self.balance = balance
        self.bet = bet
        self.avatar = avatar
        self.joined_at = time.time()


class GameState:
    """حالت یک بازی دونفره‌ی فعال"""
    __slots__ = (
        "game_id", "game_key", "players", "bet", "contrib", "data", "waiting", "deadline",
        "created_at", "updated_at", "finished", "finished_at", "winner", "reason", "payout",
        "lock", "version",
    )

    def __init__(self, game_id, game_key, players, bet):
        now = time.time()
        self.game_id = game_id
        self.game_key = game_key
        self.players = players  # [{user_id, name}]
        self.bet = bet
        self.contrib = {p["user_id"]: bet for p in players}
        self.data = {}
        self.waiting = set()
        self.deadline = now + TURN_TIMEOUT
        self.created_at = now
        self.updated_at = now
        self.finished = False
        self.finished_at = 0.0
        self.winner = None
        self.reason = ""
        self.payout = 0
        self.lock = asyncio.Lock()
        self.version = 0

    @property
    def pot(self) -> int:
        return sum(self.contrib.values())

    def uids(self) -> list:
        return [p["user_id"] for p in self.players]

    def opp(self, uid: int) -> int:
        a, b = self.uids()
        return b if uid == a else a

    def name(self, uid: int) -> str:
        for p in self.players:
            if p["user_id"] == uid:
                return p["name"]
        return "بازیکن"

    def touch(self):
        now = time.time()
        self.updated_at = now
        self.deadline = now + TURN_TIMEOUT
        self.version += 1


# ═══════════ ابزارها ═══════════
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _to_int(v, default=None):
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or abs(v) > 1e15:
            return default
        return int(v)
    if isinstance(v, str):
        s = v.translate(_FA_DIGITS).replace(",", "").replace("،", "").replace("_", "").strip()
        if 0 < len(s) <= 15 and s.lstrip("-").isdigit():
            return int(s)
    return default


def _to_float(v, default=None):
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.translate(_FA_DIGITS).replace("٫", ".").strip())
        except ValueError:
            return default
    else:
        return default
    if f != f or math.isinf(f):
        return default
    return f


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


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
    name = (user.get("first_name") or user.get("username") or "بازیکن").strip()
    return name[:32] or "بازیکن"


def _redis_on() -> bool:
    try:
        return bool(redis_client.is_redis_available())
    except Exception:
        return False


def _spawn(coro):
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


async def _track_async(uid: int, solo: bool, won: bool):
    """ثبت پیشرفت ماموریت‌ها — هیچ‌وقت نباید جریان بازی را خراب کند"""
    try:
        base_play = getattr(config, "BASE_XP_PLAY_GAME", 15)
        base_win = getattr(config, "BASE_XP_WIN_GAME", 30)
        await db.progress_mission(uid, "play_any_game", 1, base_xp=base_play)
        if solo:
            await db.progress_mission(uid, "play_casino", 1, base_xp=0)
        if won:
            await db.progress_mission(uid, "win_any_game", 1, base_xp=base_win)
            if solo:
                await db.progress_mission(uid, "win_casino", 1, base_xp=0)
    except Exception as e:
        logger.debug(f"progress_mission در مینی‌اپ ناموفق: {e}")


def _track(uid: int, solo: bool, won: bool):
    _spawn(_track_async(uid, solo, won))


async def _take_bet(uid: int, game_key: str, bet) -> str | None:
    """اعتبارسنجی و کسر شرط. خروجی: پیام خطا یا None"""
    g = GAMES.get(game_key)
    if not g:
        return "بازی نامعتبر است"
    if not isinstance(bet, int) or bet <= 0:
        return "مبلغ شرط نامعتبر است"
    if bet < g["min_bet"]:
        return f"حداقل شرط {_fmt(g['min_bet'])} است"
    if bet > g["max_bet"]:
        return f"حداکثر شرط {_fmt(g['max_bet'])} است"
    ok = await db.deduct_balance(uid, bet)
    if not ok:
        return "موجودی کافی نیست"
    return None


# ═══════════ اعتبارسنجی initData ═══════════
def validate_init_data(init_data_raw: str) -> dict | None:
    """اعتبارسنجی initData تلگرام طبق مستندات رسمی. خروجی: dict کاربر یا None"""
    if not init_data_raw:
        return None
    bot_token = config.BOT_TOKEN
    if not bot_token:
        logger.error("❌ BOT_TOKEN تنظیم نشده — اعتبارسنجی initData غیرممکن")
        return None
    try:
        parsed = urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True)
    except Exception:
        return None
    pairs = {}
    received_hash = None
    for k, v in parsed:
        if k == "hash":
            received_hash = v
        else:
            pairs[k] = v
    if not received_hash:
        return None

    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        logger.warning("⚠️ initData نامعتبر — هش مطابقت ندارد")
        return None

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            if time.time() - int(auth_date_raw) > 86400:
                logger.warning("⚠️ initData خیلی قدیمی است")
                return None
        except ValueError:
            return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except Exception:
        return None
    return user if isinstance(user, dict) else None


# ═══════════ توکن مرورگر ═══════════
_BROWSER_TOKEN_TTL = 86400 * 30


def validate_browser_token(token: str) -> int | None:
    """اعتبارسنجی توکن مرورگر (ساخته‌شده در utils.py) — خروجی user_id یا None"""
    if not token or "." not in token:
        return None
    try:
        raw_b64, sig = token.rsplit(".", 1)
        padded = raw_b64 + "=" * (-len(raw_b64) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        expected_sig = hmac.new(config.BOT_TOKEN.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("⚠️ توکن مرورگر نامعتبر — امضا مطابقت ندارد")
            return None
        payload = json.loads(raw)
        if payload.get("exp", 0) < time.time():
            logger.warning("⚠️ توکن مرورگر منقضی شده")
            return None
        return int(payload.get("uid", 0)) or None
    except Exception:
        return None


async def _get_user_for_request(request: web.Request) -> dict | None:
    """استخراج و اعتبارسنجی کاربر از header/query (body دست نمی‌خورد)"""
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data") or ""
    user_id = None
    tg_user_fields = None
    if init_data:
        tg_user = validate_init_data(init_data)
        if tg_user:
            user_id = tg_user.get("id")
            tg_user_fields = tg_user
    if not user_id:
        browser_token = request.headers.get("X-Browser-Token") or request.query.get("token") or ""
        if browser_token:
            user_id = validate_browser_token(browser_token)
    if not user_id:
        return None
    try:
        db_user = await db.get_user(int(user_id))
    except Exception as e:
        logger.exception(f"⚠️ db.get_user خطا داد: {e}")
        return None
    if not db_user and tg_user_fields:
        try:
            db_user = await db.ensure_user(type("U", (), {
                "id": int(user_id),
                "first_name": tg_user_fields.get("first_name", ""),
                "last_name": tg_user_fields.get("last_name", ""),
                "username": tg_user_fields.get("username", ""),
                "language_code": tg_user_fields.get("language_code", "fa"),
                "is_bot": False,
            })())
        except Exception as e:
            logger.exception(f"ensure_user در مینی‌اپ ناموفق: {e}")
            return None
    if not db_user:
        return None
    user = dict(db_user)
    user["user_id"] = int(user_id)
    if tg_user_fields and tg_user_fields.get("first_name"):
        user["first_name"] = tg_user_fields.get("first_name")
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


# ═══════════ کارت‌ها ═══════════
SUITS = "SHDC"
SUIT_SORT = "SHCD"  # رنگ‌ها یکی در میان


def _new_deck() -> list:
    deck = [(r, s) for s in SUITS for r in range(2, 15)]
    _rng.shuffle(deck)
    return deck


def _cj(c) -> dict:
    return {"r": c[0], "s": c[1], "id": f"{c[0]}{c[1]}"}


def _rand_card():
    return (_rng.randint(2, 14), _rng.choice(SUITS))


# ═══════════════════════════════════════════════
# ═══════════ بازی‌های تک‌نفره ═══════════
# ═══════════════════════════════════════════════
WHEEL_SEGMENTS = [0, 1.5, 0, 2, 0.5, 0, 5, 0, 1.5, 0.5, 0, 0.5]  # EV ≈ 0.96


@_auth
async def api_wheel(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    async with _ulock(uid):
        err = await _take_bet(uid, "wheel", bet)
        if err:
            return _err(err)
        idx = _rng.randrange(len(WHEEL_SEGMENTS))
        mult = WHEEL_SEGMENTS[idx]
        win = int(bet * mult)
        if win > 0:
            await db.add_balance(uid, win)
        _track(uid, True, win > bet)
        return _json({"ok": True, "index": idx, "mult": mult, "win": win, "profit": win - bet,
                      "balance": await _balance(uid)})


@_auth
async def api_crash(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    target = _to_float(body.get("target"))
    if target is None or target < 1.01 or target > 100:
        return _err("ضریب هدف باید بین ۱٫۰۱ تا ۱۰۰ باشد")
    target = round(target, 2)
    async with _ulock(uid):
        err = await _take_bet(uid, "crash", bet)
        if err:
            return _err(err)
        r = _rng.random()
        crash = math.floor((0.96 / (1.0 - r)) * 100) / 100
        crash = max(1.0, min(crash, 1000.0))
        won = crash >= target
        win = int(bet * target) if won else 0
        if win > 0:
            await db.add_balance(uid, win)
        _track(uid, True, won)
        return _json({"ok": True, "crash": crash, "target": target, "won": won, "win": win,
                      "profit": win - bet, "balance": await _balance(uid)})


@_auth
async def api_coin(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    side = body.get("side")
    if side not in ("heads", "tails"):
        return _err("شیر یا خط را انتخاب کن")
    async with _ulock(uid):
        err = await _take_bet(uid, "coin", bet)
        if err:
            return _err(err)
        result = _rng.choice(("heads", "tails"))
        won = result == side
        win = int(bet * 1.9) if won else 0
        if win > 0:
            await db.add_balance(uid, win)
        _track(uid, True, won)
        return _json({"ok": True, "result": result, "won": won, "win": win, "profit": win - bet,
                      "balance": await _balance(uid)})


# ─── مین‌یاب ───
MINES_CELLS = 25
MINES_EDGE = 0.97


def _mines_mult(k: int, m: int) -> float:
    if k <= 0:
        return 1.0
    p = 1.0
    for i in range(k):
        p *= (MINES_CELLS - i) / (MINES_CELLS - m - i)
    return round(p * MINES_EDGE, 4)


def _solo_view(s: dict | None, reveal: bool = False) -> dict | None:
    if not s:
        return None
    if s["type"] == "mines":
        k = len(s["revealed"])
        safe_left = MINES_CELLS - s["count"] - k
        v = {
            "type": "mines", "bet": s["bet"], "count": s["count"], "revealed": list(s["revealed"]),
            "mult": _mines_mult(k, s["count"]),
            "next_mult": _mines_mult(k + 1, s["count"]) if safe_left > 0 else None,
            "potential": int(s["bet"] * _mines_mult(k, s["count"])) if k else 0,
            "finished": s.get("finished", False),
        }
        if reveal or s.get("finished"):
            v["mines"] = sorted(s["mines"])
        return v
    if s["type"] == "hilo":
        r = s["card"][0]
        p_hi = (14 - r) / 13
        p_lo = (r - 2) / 13
        return {
            "type": "hilo", "bet": s["bet"], "card": _cj(s["card"]), "mult": round(s["mult"], 4),
            "steps": s["steps"],
            "hi_mult": round(s["mult"] * 0.97 / p_hi, 2) if p_hi > 0 else None,
            "lo_mult": round(s["mult"] * 0.97 / p_lo, 2) if p_lo > 0 else None,
            "potential": int(s["bet"] * s["mult"]) if s["steps"] else 0,
            "history": [_cj(c) for c in s["history"][-8:]],
            "finished": s.get("finished", False),
        }
    return None


@_auth
async def api_solo_state(request, user):
    uid = user["user_id"]
    return _json({"ok": True, "session": _solo_view(_solo_sessions.get(uid)), "balance": await _balance(uid)})


@_auth
async def api_mines_start(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    count = _to_int(body.get("mines"), 3)
    if count not in (1, 3, 5, 10, 15, 20):
        return _err("تعداد مین نامعتبر است")
    async with _ulock(uid):
        if uid in _solo_sessions:
            return _err("یک بازی نیمه‌تمام داری — اول آن را تمام کن", code="active_session",
                        session=_solo_view(_solo_sessions[uid]))
        err = await _take_bet(uid, "mines", bet)
        if err:
            return _err(err)
        s = {"type": "mines", "bet": bet, "count": count, "mines": set(_rng.sample(range(MINES_CELLS), count)),
             "revealed": [], "created": time.time()}
        _solo_sessions[uid] = s
        return _json({"ok": True, "session": _solo_view(s), "balance": await _balance(uid)})


async def _mines_cashout(uid: int, s: dict) -> int:
    k = len(s["revealed"])
    win = int(s["bet"] * _mines_mult(k, s["count"]))
    s["finished"] = True
    _solo_sessions.pop(uid, None)
    if win > 0:
        await db.add_balance(uid, win)
    _track(uid, True, win > s["bet"])
    return win


@_auth
async def api_mines_reveal(request, user):
    uid = user["user_id"]
    body = await _body(request)
    idx = _to_int(body.get("idx"), -1)
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "mines":
            return _err("بازی مین‌یاب فعالی نداری", code="no_session")
        if not 0 <= idx < MINES_CELLS or idx in s["revealed"]:
            return _err("خانه نامعتبر است")
        if idx in s["mines"]:
            s["finished"] = True
            _solo_sessions.pop(uid, None)
            _track(uid, True, False)
            v = _solo_view(s, reveal=True)
            v["boom"] = idx
            return _json({"ok": True, "session": v, "result": "lose", "win": 0, "balance": await _balance(uid)})
        s["revealed"].append(idx)
        if len(s["revealed"]) >= MINES_CELLS - s["count"]:
            win = await _mines_cashout(uid, s)
            return _json({"ok": True, "session": _solo_view(s, reveal=True), "result": "win", "win": win,
                          "balance": await _balance(uid)})
        return _json({"ok": True, "session": _solo_view(s), "result": None, "balance": await _balance(uid)})


@_auth
async def api_mines_cashout(request, user):
    uid = user["user_id"]
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "mines":
            return _err("بازی مین‌یاب فعالی نداری", code="no_session")
        if not s["revealed"]:
            return _err("حداقل یک خانه باز کن")
        win = await _mines_cashout(uid, s)
        return _json({"ok": True, "session": _solo_view(s, reveal=True), "result": "win", "win": win,
                      "balance": await _balance(uid)})


# ─── بالا پایین ───
@_auth
async def api_hilo_start(request, user):
    uid = user["user_id"]
    body = await _body(request)
    bet = _to_int(body.get("bet"))
    async with _ulock(uid):
        if uid in _solo_sessions:
            return _err("یک بازی نیمه‌تمام داری — اول آن را تمام کن", code="active_session",
                        session=_solo_view(_solo_sessions[uid]))
        err = await _take_bet(uid, "hilo", bet)
        if err:
            return _err(err)
        card = _rand_card()
        s = {"type": "hilo", "bet": bet, "card": card, "mult": 1.0, "steps": 0, "history": [card],
             "created": time.time()}
        _solo_sessions[uid] = s
        return _json({"ok": True, "session": _solo_view(s), "balance": await _balance(uid)})


async def _hilo_cashout(uid: int, s: dict) -> int:
    win = int(s["bet"] * s["mult"])
    s["finished"] = True
    _solo_sessions.pop(uid, None)
    if win > 0:
        await db.add_balance(uid, win)
    _track(uid, True, win > s["bet"])
    return win


@_auth
async def api_hilo_guess(request, user):
    uid = user["user_id"]
    body = await _body(request)
    direction = body.get("dir")
    if direction not in ("hi", "lo"):
        return _err("حدس نامعتبر است")
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "hilo":
            return _err("بازی بالا‌پایین فعالی نداری", code="no_session")
        r = s["card"][0]
        p = (14 - r) / 13 if direction == "hi" else (r - 2) / 13
        if p <= 0:
            return _err("این حدس ممکن نیست")
        nxt = _rand_card()
        won = nxt[0] > r if direction == "hi" else nxt[0] < r
        s["history"].append(nxt)
        if not won:
            s["finished"] = True
            s["card"] = nxt
            _solo_sessions.pop(uid, None)
            _track(uid, True, False)
            return _json({"ok": True, "session": _solo_view(s), "result": "lose", "next": _cj(nxt), "win": 0,
                          "balance": await _balance(uid)})
        s["mult"] = min(s["mult"] * 0.97 / p, 1000.0)
        s["steps"] += 1
        s["card"] = nxt
        return _json({"ok": True, "session": _solo_view(s), "result": None, "next": _cj(nxt),
                      "balance": await _balance(uid)})


@_auth
async def api_hilo_cashout(request, user):
    uid = user["user_id"]
    async with _ulock(uid):
        s = _solo_sessions.get(uid)
        if not s or s["type"] != "hilo":
            return _err("بازی بالا‌پایین فعالی نداری", code="no_session")
        if s["steps"] < 1:
            return _err("حداقل یک حدس درست لازم است")
        win = await _hilo_cashout(uid, s)
        return _json({"ok": True, "session": _solo_view(s), "result": "win", "win": win,
                      "balance": await _balance(uid)})


async def _close_solo_session(uid: int):
    """بستن خودکار: اگر پیشرفت داشته → برداشت، وگرنه شرط برمی‌گردد"""
    s = _solo_sessions.get(uid)
    if not s:
        return
    try:
        if s["type"] == "mines" and s["revealed"]:
            await _mines_cashout(uid, s)
        elif s["type"] == "hilo" and s["steps"] > 0:
            await _hilo_cashout(uid, s)
        else:
            _solo_sessions.pop(uid, None)
            await db.add_balance(uid, s["bet"])
    except Exception:
        logger.exception("بستن سشن تک‌نفره ناموفق")


# ═══════════════════════════════════════════════
# ═══════════ بازی‌های دونفره ═══════════
# ═══════════════════════════════════════════════
async def _settle(g: GameState, winner, reason: str):
    """پایان بازی و پرداخت. winner=None یعنی مساوی (برگشت سهم هر نفر)"""
    if g.finished:
        return
    g.finished = True
    g.finished_at = time.time()
    g.winner = winner
    g.reason = reason
    g.waiting = set()
    g.version += 1
    try:
        if winner is None:
            for uid, amount in g.contrib.items():
                if amount > 0:
                    await db.add_balance(uid, amount)
            g.payout = 0
        else:
            pot = g.pot
            fee = int(pot * COMMISSION_RATE)
            g.payout = pot - fee
            await db.add_balance(winner, g.payout)
    except Exception:
        logger.exception(f"❌ پرداخت بازی {g.game_id} ناموفق")
    for uid in g.uids():
        if _user_games.get(uid) == g.game_id:
            _user_games.pop(uid, None)
        _track(uid, False, uid == winner)


# ─── دوز ───
_TTT_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


async def ttt_init(g: GameState):
    a, b = g.uids()
    g.data = {"board": [0] * 9, "marks": {a: 1, b: 2}, "line": None}
    g.waiting = {a}


async def ttt_action(g: GameState, uid: int, body: dict):
    if uid not in g.waiting:
        return "نوبت تو نیست"
    i = _to_int(body.get("cell"), -1)
    board = g.data["board"]
    if not 0 <= i < 9 or board[i]:
        return "این خانه قابل انتخاب نیست"
    mark = g.data["marks"][uid]
    board[i] = mark
    for line in _TTT_LINES:
        if all(board[x] == mark for x in line):
            g.data["line"] = list(line)
            await _settle(g, uid, f"{g.name(uid)} سه‌تا در یک خط چید")
            return None
    if all(board):
        await _settle(g, None, "صفحه پر شد — مساوی")
        return None
    g.waiting = {g.opp(uid)}
    return None


def ttt_view(g: GameState, uid: int) -> dict:
    return {"board": g.data["board"], "my_mark": g.data["marks"][uid], "line": g.data["line"]}


# ─── چهار در یک ردیف ───
C4_ROWS, C4_COLS = 6, 7


async def c4_init(g: GameState):
    a, b = g.uids()
    g.data = {"board": [0] * (C4_ROWS * C4_COLS), "discs": {a: 1, b: 2}, "line": None, "last": None}
    g.waiting = {a}


def _c4_line(board, r, c, d):
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        cells = [(r, c)]
        for sign in (1, -1):
            rr, cc = r + dr * sign, c + dc * sign
            while 0 <= rr < C4_ROWS and 0 <= cc < C4_COLS and board[rr * C4_COLS + cc] == d:
                cells.append((rr, cc))
                rr += dr * sign
                cc += dc * sign
        if len(cells) >= 4:
            return [x * C4_COLS + y for x, y in cells]
    return None


async def c4_action(g: GameState, uid: int, body: dict):
    if uid not in g.waiting:
        return "نوبت تو نیست"
    c = _to_int(body.get("col"), -1)
    if not 0 <= c < C4_COLS:
        return "ستون نامعتبر است"
    board = g.data["board"]
    d = g.data["discs"][uid]
    for r in range(C4_ROWS - 1, -1, -1):
        if board[r * C4_COLS + c] == 0:
            board[r * C4_COLS + c] = d
            g.data["last"] = r * C4_COLS + c
            line = _c4_line(board, r, c, d)
            if line:
                g.data["line"] = line
                await _settle(g, uid, f"{g.name(uid)} چهار مهره پشت‌سرهم چید")
                return None
            if all(board):
                await _settle(g, None, "صفحه پر شد — مساوی")
                return None
            g.waiting = {g.opp(uid)}
            return None
    return "این ستون پر است"


def c4_view(g: GameState, uid: int) -> dict:
    return {"board": g.data["board"], "my_disc": g.data["discs"][uid], "line": g.data["line"],
            "last": g.data["last"], "rows": C4_ROWS, "cols": C4_COLS}


# ─── سنگ کاغذ قیچی (۳ دست) ───
_RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


async def rps_init(g: GameState):
    a, b = g.uids()
    g.data = {"score": {a: 0, b: 0}, "picks": {}, "history": [], "round": 1}
    g.waiting = {a, b}


async def rps_action(g: GameState, uid: int, body: dict):
    pick = body.get("pick")
    if pick not in _RPS_BEATS:
        return "انتخاب نامعتبر است"
    if uid not in g.waiting:
        return "این دست را انتخاب کرده‌ای — منتظر حریف باش"
    d = g.data
    d["picks"][uid] = pick
    g.waiting.discard(uid)
    if len(d["picks"]) < 2:
        return None
    a, b = g.uids()
    pa, pb = d["picks"][a], d["picks"][b]
    w = None
    if _RPS_BEATS[pa] == pb:
        w = a
    elif _RPS_BEATS[pb] == pa:
        w = b
    if w:
        d["score"][w] += 1
    d["history"].append({"picks": {a: pa, b: pb}, "winner": w})
    d["picks"] = {}
    if d["score"][a] >= 2 or d["score"][b] >= 2:
        win = a if d["score"][a] > d["score"][b] else b
        await _settle(g, win, f"{g.name(win)} دو دست برد")
        return None
    if d["round"] >= 9:
        if d["score"][a] == d["score"][b]:
            await _settle(g, None, "۹ دست تمام شد — مساوی")
        else:
            win = a if d["score"][a] > d["score"][b] else b
            await _settle(g, win, f"{g.name(win)} با امتیاز بیشتر برد")
        return None
    d["round"] += 1
    g.waiting = {a, b}
    return None


def rps_view(g: GameState, uid: int) -> dict:
    d = g.data
    o = g.opp(uid)
    hist = []
    for h in d["history"]:
        res = "draw" if h["winner"] is None else ("win" if h["winner"] == uid else "lose")
        hist.append({"me": h["picks"][uid], "opp": h["picks"][o], "result": res})
    return {"score_me": d["score"][uid], "score_opp": d["score"][o], "my_pick": d["picks"].get(uid),
            "opp_picked": o in d["picks"], "round": d["round"], "history": hist}


# ─── بلک‌جک (دونفره) ───
def _bj_value(cards) -> int:
    total, aces = 0, 0
    for r, _ in cards:
        if r == 14:
            total += 11
            aces += 1
        elif r >= 10:
            total += 10
        else:
            total += r
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


async def _bj_resolve(g: GameState):
    a, b = g.uids()
    va, vb = _bj_value(g.data["hands"][a]), _bj_value(g.data["hands"][b])
    ba, bb = va > 21, vb > 21
    if ba and bb:
        await _settle(g, None, "هر دو سوختید — مساوی")
    elif ba:
        await _settle(g, b, f"{g.name(a)} سوخت ({va})")
    elif bb:
        await _settle(g, a, f"{g.name(b)} سوخت ({vb})")
    elif va == vb:
        await _settle(g, None, f"امتیاز برابر ({va}) — مساوی")
    else:
        w = a if va > vb else b
        await _settle(g, w, f"{g.name(w)} با {max(va, vb)} در برابر {min(va, vb)} برد")


async def bj_init(g: GameState):
    deck = _new_deck()
    a, b = g.uids()
    hands = {a: [deck.pop(), deck.pop()], b: [deck.pop(), deck.pop()]}
    done = {u: _bj_value(hands[u]) == 21 for u in (a, b)}
    g.data = {"deck": deck, "hands": hands, "done": done}
    g.waiting = {u for u in (a, b) if not done[u]}
    if not g.waiting:
        await _bj_resolve(g)


async def bj_action(g: GameState, uid: int, body: dict):
    act = body.get("action")
    if uid not in g.waiting:
        return "نوبت تو تمام شده — منتظر حریف باش"
    d = g.data
    if act == "hit":
        d["hands"][uid].append(d["deck"].pop())
        v = _bj_value(d["hands"][uid])
        if v >= 21:
            d["done"][uid] = True
            g.waiting.discard(uid)
    elif act == "stand":
        d["done"][uid] = True
        g.waiting.discard(uid)
    else:
        return "حرکت نامعتبر است"
    if not g.waiting:
        await _bj_resolve(g)
    return None


def bj_view(g: GameState, uid: int) -> dict:
    d = g.data
    o = g.opp(uid)
    mine = d["hands"][uid]
    theirs = d["hands"][o]
    show = g.finished
    return {
        "my_cards": [_cj(c) for c in mine], "my_value": _bj_value(mine), "my_done": d["done"][uid],
        "opp_cards": [_cj(c) if (show or i == 0) else None for i, c in enumerate(theirs)],
        "opp_value": _bj_value(theirs) if show else None, "opp_done": d["done"][o],
    }


# ─── حکم دونفره ───
def _sort_hand(hand):
    return sorted(hand, key=lambda c: (SUIT_SORT.index(c[1]), c[0]))


async def hokm_init(g: GameState):
    deck = _new_deck()
    a, b = g.uids()
    hakem = _rng.choice((a, b))
    other = g.opp(hakem)
    hands = {hakem: _sort_hand([deck.pop() for _ in range(5)]), other: []}
    g.data = {"deck": deck, "hands": hands, "hakem": hakem, "trump": None, "phase": "trump",
              "table": [], "tricks": {a: 0, b: 0}, "last_trick": None}
    g.waiting = {hakem}


async def hokm_action(g: GameState, uid: int, body: dict):
    d = g.data
    if uid not in g.waiting:
        return "نوبت تو نیست"
    if d["phase"] == "trump":
        suit = body.get("suit")
        if suit not in SUITS:
            return "خال حکم نامعتبر است"
        d["trump"] = suit
        hakem = d["hakem"]
        other = g.opp(hakem)
        d["hands"][hakem] = _sort_hand(d["hands"][hakem] + [d["deck"].pop() for _ in range(8)])
        d["hands"][other] = _sort_hand([d["deck"].pop() for _ in range(13)])
        d["phase"] = "play"
        g.waiting = {hakem}
        return None
    cid = str(body.get("card") or "")
    hand = d["hands"][uid]
    card = next((c for c in hand if f"{c[0]}{c[1]}" == cid), None)
    if not card:
        return "این کارت در دست تو نیست"
    if d["table"]:
        led = d["table"][0][1][1]
        if card[1] != led and any(c[1] == led for c in hand):
            return "باید هم‌خال بازی کنی"
    hand.remove(card)
    d["table"].append((uid, card))
    if len(d["table"]) == 1:
        g.waiting = {g.opp(uid)}
        return None
    (u1, c1), (u2, c2) = d["table"]
    if c2[1] == c1[1]:
        w = u2 if c2[0] > c1[0] else u1
    elif c2[1] == d["trump"]:
        w = u2
    else:
        w = u1
    d["tricks"][w] += 1
    d["last_trick"] = {"cards": list(d["table"]), "winner": w}
    d["table"] = []
    if d["tricks"][w] >= 7:
        await _settle(g, w, f"{g.name(w)} هفت دست برد")
        return None
    g.waiting = {w}
    return None


def hokm_view(g: GameState, uid: int) -> dict:
    d = g.data
    o = g.opp(uid)
    hand = d["hands"][uid]
    led = d["table"][0][1][1] if d["table"] else None
    has_led = led is not None and any(c[1] == led for c in hand)
    my_turn = uid in g.waiting and d["phase"] == "play"
    cards = []
    for c in hand:
        j = _cj(c)
        j["playable"] = bool(my_turn and (not has_led or c[1] == led))
        cards.append(j)
    lt = None
    if d["last_trick"]:
        lt = {"cards": [{"card": _cj(c), "mine": u == uid} for u, c in d["last_trick"]["cards"]],
              "i_won": d["last_trick"]["winner"] == uid}
    return {
        "phase": d["phase"], "trump": d["trump"], "i_am_hakem": d["hakem"] == uid,
        "my_hand": cards, "opp_count": len(d["hands"][o]),
        "table": [{"card": _cj(c), "mine": u == uid} for u, c in d["table"]],
        "tricks_me": d["tricks"][uid], "tricks_opp": d["tricks"][o], "last_trick": lt,
    }


# ─── پوکر تگزاس هولدم (هدز‌آپ) ───
HAND_NAMES = ["کارت بالا", "یک جفت", "دو جفت", "سه‌تایی", "استریت", "فلاش", "فول هاوس", "چهارتایی",
              "استریت فلاش"]
STREET_NAMES = ["پیش از فلاپ", "فلاپ", "ترن", "ریور", "شودان"]
HOLDEM_MAX_RAISES = 3


def _eval5(cs) -> tuple:
    ranks = sorted((c[0] for c in cs), reverse=True)
    flush = len({c[1] for c in cs}) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_high = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_high = 5
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    shape = [n for _, n in groups]
    gr = [r for r, _ in groups]
    if straight_high and flush:
        return (8, straight_high)
    if shape[0] == 4:
        return (7, *gr)
    if shape == [3, 2]:
        return (6, *gr)
    if flush:
        return (5, *ranks)
    if straight_high:
        return (4, straight_high)
    if shape[0] == 3:
        return (3, *gr)
    if shape == [2, 2, 1]:
        return (2, *gr)
    if shape[0] == 2:
        return (1, *gr)
    return (0, *ranks)


def _best_hand(cards) -> tuple:
    if len(cards) < 5:
        ranks = sorted((c[0] for c in cards), reverse=True)
        if len(ranks) == 2 and ranks[0] == ranks[1]:
            return (1, ranks[0])
        return (0, *ranks)
    return max(_eval5(combo) for combo in itertools.combinations(cards, 5))


def _hand_name(score: tuple) -> str:
    if score[0] == 8 and score[1] == 14:
        return "رویال فلاش"
    return HAND_NAMES[score[0]]


def _board_visible(street: int) -> int:
    return [0, 3, 4, 5, 5][min(street, 4)]


async def holdem_init(g: GameState):
    deck = _new_deck()
    a, b = g.uids()
    g.data = {
        "hole": {a: [deck.pop(), deck.pop()], b: [deck.pop(), deck.pop()]},
        "board": [deck.pop() for _ in range(5)],   # فقط سمت سرور — به‌تدریج نمایش داده می‌شود
        "street": 0, "sbets": {a: 0, b: 0}, "acted": set(), "raises": 0,
        "raise_size": max(1, g.bet), "log": [], "showdown": False, "folded": None,
    }
    g.waiting = {a}


def _holdem_log(g: GameState, text: str):
    g.data["log"].append(text)
    g.data["log"] = g.data["log"][-6:]


async def _holdem_next_street(g: GameState):
    d = g.data
    a, b = g.uids()
    d["street"] += 1
    d["sbets"] = {a: 0, b: 0}
    d["acted"] = set()
    d["raises"] = 0
    if d["street"] >= 4:
        d["showdown"] = True
        sa = _best_hand(d["hole"][a] + d["board"])
        sb = _best_hand(d["hole"][b] + d["board"])
        d["final"] = {a: _hand_name(sa), b: _hand_name(sb)}
        if sa == sb:
            await _settle(g, None, f"دست برابر ({_hand_name(sa)}) — پات تقسیم شد")
        else:
            w = a if sa > sb else b
            await _settle(g, w, f"{g.name(w)} با {d['final'][w]} برد")
        return
    _holdem_log(g, f"— {STREET_NAMES[d['street']]} —")
    g.waiting = {b}  # بعد از فلاپ بازیکن دوم اول حرکت می‌کند


async def holdem_action(g: GameState, uid: int, body: dict):
    d = g.data
    if uid not in g.waiting:
        return "نوبت تو نیست"
    act = body.get("action")
    o = g.opp(uid)
    diff = d["sbets"][o] - d["sbets"][uid]
    name = g.name(uid)
    if act == "fold":
        d["folded"] = uid
        _holdem_log(g, f"{name} فولد کرد")
        await _settle(g, o, f"{name} فولد کرد")
        return None
    if act == "check":
        if diff > 0:
            return "باید کال یا فولد کنی"
        _holdem_log(g, f"{name} چک کرد")
    elif act == "call":
        if diff <= 0:
            _holdem_log(g, f"{name} چک کرد")
        else:
            if not await db.deduct_balance(uid, diff):
                return "موجودی کافی برای کال نداری — می‌توانی فولد کنی"
            g.contrib[uid] += diff
            d["sbets"][uid] += diff
            _holdem_log(g, f"{name} کال کرد ({_fmt(diff)})")
    elif act == "raise":
        if d["raises"] >= HOLDEM_MAX_RAISES:
            return "سقف رِیز این مرحله پر شده"
        rs = d["raise_size"]
        if await _balance(o) < rs:
            return "حریف موجودی کافی برای رِیز بیشتر ندارد"
        amount = max(0, diff) + rs
        if not await db.deduct_balance(uid, amount):
            return "موجودی کافی برای رِیز نداری"
        g.contrib[uid] += amount
        d["sbets"][uid] += amount
        d["raises"] += 1
        d["acted"] = {uid}
        _holdem_log(g, f"{name} رِیز کرد (+{_fmt(rs)})")
        g.waiting = {o}
        return None
    else:
        return "حرکت نامعتبر است"
    d["acted"].add(uid)
    if len(d["acted"]) >= 2 and d["sbets"][uid] == d["sbets"][o]:
        await _holdem_next_street(g)
    else:
        g.waiting = {o}
    return None


def holdem_view(g: GameState, uid: int) -> dict:
    d = g.data
    o = g.opp(uid)
    street = d["street"]
    n = 5 if d["showdown"] else _board_visible(street)
    board = d["board"][:n]
    my_score = _best_hand(d["hole"][uid] + board)
    diff = d["sbets"][o] - d["sbets"][uid]
    show_opp = d["showdown"]
    v = {
        "street": street, "street_name": STREET_NAMES[min(street, 4)],
        "board": [_cj(c) for c in board],
        "my_cards": [_cj(c) for c in d["hole"][uid]],
        "opp_cards": [_cj(c) for c in d["hole"][o]] if show_opp else [None, None],
        "my_hand": _hand_name(my_score),
        "opp_hand": d.get("final", {}).get(o) if show_opp else None,
        "can_check": diff <= 0, "call_amount": max(0, diff),
        "raise_amount": max(0, diff) + d["raise_size"], "can_raise": d["raises"] < HOLDEM_MAX_RAISES,
        "my_contrib": g.contrib[uid], "opp_contrib": g.contrib[o],
        "my_street_bet": d["sbets"][uid], "opp_street_bet": d["sbets"][o],
        "log": d["log"], "showdown": d["showdown"],
    }
    return v


GAME_IMPL = {
    "ttt": (ttt_init, ttt_action, ttt_view),
    "connect4": (c4_init, c4_action, c4_view),
    "rps": (rps_init, rps_action, rps_view),
    "blackjack": (bj_init, bj_action, bj_view),
    "hokm": (hokm_init, hokm_action, hokm_view),
    "holdem": (holdem_init, holdem_action, holdem_view),
}


def _game_view(g: GameState, uid: int) -> dict:
    o = g.opp(uid)
    meta = GAMES.get(g.game_key, {})
    if g.finished:
        result = "draw" if g.winner is None else ("win" if g.winner == uid else "lose")
    else:
        result = None
    try:
        state = GAME_IMPL[g.game_key][2](g, uid)
    except Exception:
        logger.exception("view error")
        state = {}
    return {
        "game_id": g.game_id, "game_key": g.game_key, "title": meta.get("name", g.game_key),
        "emoji": meta.get("emoji", "🎮"), "bet": g.bet, "pot": g.pot,
        "me": {"id": uid, "name": g.name(uid)}, "opp": {"id": o, "name": g.name(o)},
        "your_turn": uid in g.waiting, "opp_turn": o in g.waiting,
        "deadline_in": 0 if g.finished else max(0, int(g.deadline - time.time())),
        "turn_timeout": TURN_TIMEOUT,
        "finished": g.finished, "result": result, "reason": g.reason,
        "payout": g.payout if g.winner == uid else 0,
        "version": g.version, "state": state,
    }


# ═══════════ صف مچ‌میکینگ ═══════════
async def _queue_add(game_key: str, bet: int, uid: int, name: str) -> bool:
    entry = MatchEntry(uid, name, 0, bet)
    if _redis_on():
        data = {"name": name, "balance": 0, "avatar": ""}
        ok = await redis_client.add_to_queue(game_key, bet, uid, data)
        if not ok:
            try:
                await redis_client.remove_from_queue(uid)  # پاک‌سازی ورودی‌های کهنه
            except Exception:
                pass
            ok = await redis_client.add_to_queue(game_key, bet, uid, data)
        if not ok:
            return False
    else:
        _match_queues.setdefault(f"{game_key}:{bet}", {})[uid] = entry
    _waiting[uid] = {"game_key": game_key, "bet": bet, "joined_at": entry.joined_at, "name": name}
    return True


async def _queue_remove(uid: int) -> dict | None:
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


async def _queue_pop_opponent(game_key: str, bet: int, uid: int) -> dict | None:
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
                await db.add_balance(oid, bet)  # escrow ورودی کهنه برگردانده می‌شود
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


async def _reclaim_orphan(uid: int) -> int:
    """ورودی صف Redis که از قبل از ری‌استارت مانده → حذف و برگشت پول"""
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


async def _create_game(game_key: str, players: list, bet: int) -> GameState:
    _rng.shuffle(players)
    gid = secrets.token_urlsafe(9)
    g = GameState(gid, game_key, players, bet)
    _active_games[gid] = g
    for p in players:
        _user_games[p["user_id"]] = gid
    async with g.lock:
        await GAME_IMPL[game_key][0](g)
        g.touch()
    logger.info(f"🎮 بازی {game_key} شروع شد: {players[0]['user_id']} vs {players[1]['user_id']} (شرط {bet})")
    return g


def _active_game_of(uid: int) -> GameState | None:
    gid = _user_games.get(uid)
    g = _active_games.get(gid) if gid else None
    if g and not g.finished:
        return g
    if gid and (not g or g.finished):
        _user_games.pop(uid, None)
    return None


def _queue_info(uid: int) -> dict | None:
    w = _waiting.get(uid)
    if not w:
        return None
    meta = GAMES.get(w["game_key"], {})
    return {"game_key": w["game_key"], "bet": w["bet"], "title": meta.get("name", ""),
            "emoji": meta.get("emoji", ""),
            "remaining": max(0, int(MATCH_TIMEOUT - (time.time() - w["joined_at"])))}


# ═══════════ API عمومی ═══════════
@_auth
async def api_me(request, user):
    uid = user["user_id"]
    refunded = 0
    async with _matchmaking_lock:
        refunded = await _reclaim_orphan(uid)
    level = 1
    try:
        if _utils and hasattr(_utils, "calc_level"):
            level = _utils.calc_level(int(user.get("total_xp", 0) or 0))[0]
        else:
            level = int(user.get("level", 1) or 1)
    except Exception:
        pass
    g = _active_game_of(uid)
    games = [{"key": k, **v} for k, v in GAMES.items()]
    return _json({
        "ok": True,
        "user": {"id": uid, "name": _uname(user), "balance": await _balance(uid), "level": level},
        "games": games, "commission": COMMISSION_RATE, "match_timeout": MATCH_TIMEOUT,
        "turn_timeout": TURN_TIMEOUT, "wheel_segments": WHEEL_SEGMENTS,
        "queue": _queue_info(uid), "game_id": g.game_id if g else None,
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
    meta = GAMES.get(game_key)
    if not meta or meta["type"] != "2p":
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
        refunded = 0
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
                return _json({"ok": True, "status": "timeout", "refunded": w["bet"],
                              "balance": await _balance(uid)})
            return _json({"ok": True, "status": "waiting", "queue": _queue_info(uid)})
        refunded = await _reclaim_orphan(uid)
    if refunded:
        return _json({"ok": True, "status": "timeout", "refunded": refunded, "balance": await _balance(uid)})
    return _json({"ok": True, "status": "idle", "balance": await _balance(uid)})


def _find_game(uid: int, gid) -> GameState | None:
    g = _active_games.get(gid) if isinstance(gid, str) else None
    if g is None:
        g = _active_games.get(_user_games.get(uid, ""))
    if g and uid in g.uids():
        return g
    return None


@_auth
async def api_game_state(request, user):
    uid = user["user_id"]
    body = await _body(request)
    g = _find_game(uid, body.get("game_id"))
    if not g:
        return _json({"ok": True, "game": None, "balance": await _balance(uid)})
    await _check_timeout(g)
    return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})


@_auth
async def api_game_action(request, user):
    uid = user["user_id"]
    body = await _body(request)
    g = _find_game(uid, body.get("game_id"))
    if not g:
        return _err("بازی پیدا نشد", 404, "no_game")
    async with g.lock:
        if g.finished:
            return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})
        err = await GAME_IMPL[g.game_key][1](g, uid, body)
        if err:
            return _err(err, game=_game_view(g, uid))
        if not g.finished:
            g.touch()
    return _json({"ok": True, "game": _game_view(g, uid), "balance": await _balance(uid)})


@_auth
async def api_game_leave(request, user):
    uid = user["user_id"]
    body = await _body(request)
    g = _find_game(uid, body.get("game_id"))
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


# ═══════════ پاک‌سازی دوره‌ای ═══════════
async def _sweeper():
    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL)
            now = time.time()
            # تایم‌اوت صف
            async with _matchmaking_lock:
                for uid, w in list(_waiting.items()):
                    if now - w["joined_at"] >= MATCH_TIMEOUT + 15:  # کلاینت معمولاً زودتر خودش اعلام می‌کند
                        await _queue_remove(uid)
                        await db.add_balance(uid, w["bet"])
                        logger.info(f"⌛ تایم‌اوت صف — برگشت {w['bet']} به {uid}")
            # تایم‌اوت نوبت و حذف بازی‌های قدیمی
            for gid, g in list(_active_games.items()):
                if not g.finished:
                    await _check_timeout(g)
                elif now - g.finished_at > FINISHED_GAME_TTL:
                    _active_games.pop(gid, None)
            # سشن‌های تک‌نفره‌ی رهاشده
            for uid, s in list(_solo_sessions.items()):
                if now - s.get("created", now) > SOLO_SESSION_TTL:
                    async with _ulock(uid):
                        await _close_solo_session(uid)
            # پاک‌سازی قفل‌های بلااستفاده
            if len(_user_locks) > 5000:
                for uid, lk in list(_user_locks.items()):
                    if not lk.locked():
                        _user_locks.pop(uid, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sweeper error")


# ═══════════ صفحه و میدلور ═══════════
_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; connect-src 'self'")


@web.middleware
async def _security_mw(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        resp.headers["Content-Security-Policy"] = _CSP
        resp.headers["Cache-Control"] = "no-cache"
    return resp


async def handle_index(request: web.Request):
    try:
        html = MINIAPP_HTML.read_text(encoding="utf-8")
    except FileNotFoundError:
        return web.Response(text="miniapp.html not found", status=500)
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def handle_health(request: web.Request):
    return _json({"ok": True, "redis": _redis_on(), "games": len(_active_games), "queue": len(_waiting)})


def create_app() -> web.Application:
    app = web.Application(middlewares=[_security_mw], client_max_size=64 * 1024)
    for path in ("/", "/miniapp", "/webapp", "/casino", "/app"):
        app.router.add_get(path, handle_index)
    app.router.add_get("/health", handle_health)
    routes = {
        "/api/me": api_me, "/api/balance": api_balance,
        "/api/solo/state": api_solo_state,
        "/api/solo/wheel": api_wheel, "/api/solo/crash": api_crash, "/api/solo/coin": api_coin,
        "/api/solo/mines/start": api_mines_start, "/api/solo/mines/reveal": api_mines_reveal,
        "/api/solo/mines/cashout": api_mines_cashout,
        "/api/solo/hilo/start": api_hilo_start, "/api/solo/hilo/guess": api_hilo_guess,
        "/api/solo/hilo/cashout": api_hilo_cashout,
        "/api/match/join": api_match_join, "/api/match/cancel": api_match_cancel,
        "/api/match/status": api_match_status,
        "/api/game/state": api_game_state, "/api/game/action": api_game_action,
        "/api/game/leave": api_game_leave,
    }
    for path, h in routes.items():
        app.router.add_post(path, h)
    return app


# ═══════════ شروع / توقف ═══════════
_runner: web.AppRunner | None = None
_sweeper_task: asyncio.Task | None = None


async def start_webapp(*args, **kwargs):
    """راه‌اندازی سرور مینی‌اپ (از post_init ربات صدا زده می‌شود)"""
    global _runner, _sweeper_task
    if _runner is not None:
        return _runner
    try:
        if not _redis_on():
            await redis_client.init_redis()
    except Exception as e:
        logger.warning(f"⚠️ init_redis ناموفق: {e}")
    port = int(kwargs.get("port") or getattr(config, "WEBAPP_PORT", 8080))
    host = kwargs.get("host") or "0.0.0.0"
    app = create_app()
    _runner = web.AppRunner(app, access_log=None)
    await _runner.setup()
    site = web.TCPSite(_runner, host, port)
    await site.start()
    _sweeper_task = asyncio.create_task(_sweeper())
    logger.info(f"🎲 مینی‌اپ قمارخانه روی پورت {port} اجرا شد (Redis: {'✅' if _redis_on() else '❌ fallback'})")
    return _runner


async def stop_webapp(*args, **kwargs):
    """توقف سرور + برگرداندن پول صف‌ها و بازی‌های نیمه‌تمام"""
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
        for uid in list(_solo_sessions.keys()):
            await _close_solo_session(uid)
    except Exception:
        logger.exception("refund on shutdown failed")
    if _runner is not None:
        try:
            await _runner.cleanup()
        except Exception:
            pass
        _runner = None
    try:
        await redis_client.close_redis()
    except Exception:
        pass


# نام‌های جایگزین برای سازگاری با نسخه‌های قبلی bot.py
start_server = start_webapp_server = run_webapp = init_webapp = start_webapp
stop_server = stop_webapp_server = shutdown_webapp = close_webapp = stop_webapp
build_app = make_app = create_app
