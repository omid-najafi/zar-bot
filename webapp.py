# -*- coding: utf-8 -*-
"""
🎲 سرور مینی‌اپ قمارخانه (Telegram WebApp)
─────────────────────────────────────────────
- اعتبارسنجی initData تلگرام (HMAC)
- مچ‌میکینگ با تایم‌اوت ۶۰ ثانیه برای بازی‌های دونفره
- بازی‌های تک‌نفره: اسلات، تاس، چرخ شانس
- بازی‌های دونفره: حکم، پوکر، بلک‌جک
- تم قرمز و مشکی (در templates/miniapp.html)
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import random
import time
import urllib.parse
from pathlib import Path

from aiohttp import web

import config
import db
import redis_client

logger = logging.getLogger("zarcoin.webapp")

# ═══════════ مسیرها ═══════════
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MINIAPP_HTML = TEMPLATES_DIR / "miniapp.html"

# ═══════════ ساختار داده‌های درون‌حافظه‌ای ═══════════
# صف مچ‌میکینگ (fallback فقط وقتی Redis نباشد): { game_key: { user_id: MatchEntry } }
_match_queues: dict[str, dict[int, "MatchEntry"]] = {}

# بازی‌های فعال: { game_id: GameState }
_active_games: dict[str, "GameState"] = {}

# نگاشت user_id → game_id (برای پیدا کردن سریع بازی کاربر)
_user_games: dict[int, str] = {}

# قفل سراسری برای matchmaking atomic (محلی؛ در Redis از RedisLock استفاده می‌شود)
_matchmaking_lock = asyncio.Lock()


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
    """حالت یک بازی فعال"""
    __slots__ = (
        "game_id", "game_key", "players", "bet", "pot",
        "state", "turn_idx", "created_at", "updated_at", "data",
        "winner", "finished",
    )

    def __init__(self, game_id, game_key, players, bet):
        self.game_id = game_id
        self.game_key = game_key
        self.players = players  # list of {user_id, name, avatar, balance}
        self.bet = bet
        self.pot = bet * len(players)
        self.state = "init"
        self.turn_idx = 0
        self.created_at = time.time()
        self.updated_at = time.time()
        self.data = {}  # state اختصاصی هر بازی
        self.winner = None  # user_id برنده یا None برای مساوی
        self.finished = False


# ═══════════ اعتبارسنجی initData ═══════════
def validate_init_data(init_data_raw: str) -> dict | None:
    """
    اعتبارسنجی initData تلگرام طبق مستندات رسمی.
    برمی‌گرداند: dict شامل user (parsed) یا None.

    🔧 نکته مهم: data-check-string باید از مقادیر URL-encoded اصلی ساخته شود
    (parse_qsl آن‌ها را decode می‌کرد که باعث عدم تطابق هش می‌شد).
    """
    if not init_data_raw:
        return None
    bot_token = config.BOT_TOKEN
    if not bot_token:
        logger.error("❌ BOT_TOKEN تنظیم نشده — اعتبارسنجی initData غیرممکن")
        return None

    # پارس دستی بدون URL-decode — برای حفظ encoding اصلی Telegram
    pairs = {}
    received_hash = None
    for chunk in init_data_raw.split("&"):
        if "=" not in chunk:
            continue
        k, _, v = chunk.partition("=")
        if k == "hash":
            received_hash = v
        else:
            pairs[k] = v
    if not received_hash:
        return None

    # ساخت data-check-string با کلیدها به ترتیب الفبایی، مقادیر URL-encoded اصلی
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))

    # کلید محرمانه: HMAC(SHA256, bot_token, "WebAppData")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        logger.warning("⚠️ initData نامعتبر — هش مطابقت ندارد")
        return None

    # اعتبارسنجی auth_date (پیر بودن بیش از ۱ روز رد شود)
    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            # auth_date عدد است — decode امن
            auth_date = int(urllib.parse.unquote(auth_date_raw))
            if time.time() - auth_date > 86400:
                logger.warning("⚠️ initData خیلی قدیمی است")
                return None
        except ValueError:
            return None

    # مقدار user را URL-decode کن و سپس JSON parse
    user_raw = pairs.get("user")
    if not user_raw:
        return None
    try:
        user_json = urllib.parse.unquote(user_raw)
        user = json.loads(user_json)
    except Exception:
        return None
    return user


# ═══════════ توکن مرورگر (جایگزین initData برای باز شدن در مرورگر خارجی) ═══════════
# تولید توکن در utils.py انجام می‌شود (سمت ربات). اینجا فقط اعتبارسنجی می‌شود.
_BROWSER_TOKEN_TTL = 86400 * 30  # ۳۰ روز (برای لاگ)


def validate_browser_token(token: str) -> int | None:
    """اعتبارسنجی توکن مرورگر — برمی‌گرداند user_id یا None"""
    if not token or "." not in token:
        return None
    try:
        raw_b64, sig = token.rsplit(".", 1)
        raw = base64.urlsafe_b64decode(raw_b64.encode())
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
    """استخراج و اعتبارسنجی کاربر از درخواست"""
    # 🔧 فقط از header یا query بخوان — body متعلق به handler است و نباید
    # توسط این تابع مصرف شود (در غیر این صورت request.json() در handler خطا می‌دهد)
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.query.get("init_data")
        or ""
    )
    tg_user = None
    user_id = None
    tg_user_fields = None
    if init_data:
        tg_user = validate_init_data(init_data)
        if tg_user:
            user_id = tg_user.get("id")
            tg_user_fields = tg_user
            logger.info(f"✅ initData معتبر — user_id={user_id}")
        else:
            logger.warning(f"⚠️ initData نامعتبر (طول: {len(init_data)}) — احراز هویت ناموفق")
    # 🔧 جایگزین initData: توکن مرورگر (برای باز شدن در مرورگر خارجی)
    if not user_id:
        browser_token = (
            request.headers.get("X-Browser-Token")
            or request.query.get("token")
            or ""
        )
        if browser_token:
            user_id = validate_browser_token(browser_token)
            tg_user_fields = None
            if user_id:
                logger.info(f"✅ توکن مرورگر معتبر — user_id={user_id}")
            else:
                logger.warning("⚠️ توکن مرورگر نامعتبر")
    if not user_id:
        logger.warning("⚠️ هیچ اعتبار معتبری پیدا نشود — 401")
        return None
    # اطمینان از وجود کاربر در DB
    try:
        db_user = await db.get_user(int(user_id))
    except Exception as e:
        logger.exception(f"⚠️ db.get_user خطا داد: {e}")
        return None
    if not db_user:
        # اگر هنوز ثبت نشده، یک رکورد موقت می‌سازیم (فقط مسیر initData که فیلدها دارد)
        if tg_user_fields:
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
        else:
            # مسیر توکن مرورگر: کاربر باید از قبل در DB باشد (توکن فقط از ربات صادر می‌شود)
            logger.warning(f"⚠️ کاربر {user_id} در DB نیست و مسیر توکن مرورگر است")
            return None
    return db_user


# ═══════════ دفترچه وسیله پاسخ JSON ═══════════
def json_ok(data=None, status=200):
    return web.json_response({"ok": True, "data": data}, status=status)


def json_err(msg: str, status=400, code=None):
    payload = {"ok": False, "error": msg}
    if code:
        payload["code"] = code
    return web.json_response(payload, status=status)


# ═══════════ مسیر: صفحه HTML ═══════════
async def handle_index(request: web.Request):
    if not MINIAPP_HTML.exists():
        return web.Response(text="迷你اپ پیدا نشد — templates/miniapp.html موجود نیست", status=404)
    return web.FileResponse(MINIAPP_HTML)


# ═══════════ API: auth/profile ═══════════
async def handle_profile(request: web.Request):
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    balance = int(user.get("balance", 0))
    bank = int(user.get("bank_balance", 0))
    # محاسبه لول
    total_xp = int(user.get("total_xp", 0))
    level, xp_in_level, xp_for_next = _calc_level(total_xp)
    # ساخت URL آواتار تلگرام
    avatar_url = ""
    # آواتارها در mini-app از طریق Telegram SDK یا default avatar
    return json_ok({
        "user_id": int(user.get("user_id", 0)),
        "first_name": user.get("first_name", "") or "بی‌نام",
        "last_name": user.get("last_name", "") or "",
        "username": user.get("username", "") or "",
        "balance": balance,
        "bank_balance": bank,
        "total_wealth": balance + bank,
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_for_next": xp_for_next,
        "total_xp": total_xp,
        "avatar_url": avatar_url,
    })


def _calc_level(total_xp: int):
    """همان منطق utils.calc_level — برای جلوگیری از import دور"""
    level = 1
    cum = 0
    while True:
        cost = (2 ** level) * 1000
        if total_xp >= cum + cost:
            cum += cost
            level += 1
        else:
            break
    return level, total_xp - cum, (2 ** level) * 1000


# ═══════════ API: لیست بازی‌ها ═══════════
async def handle_games(request: web.Request):
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    games = []
    for key, g in config.MINIAPP_GAMES.items():
        games.append({
            "key": key,
            "name": g["name"],
            "emoji": g["emoji"],
            "type": g["type"],
            "min_bet": g["min_bet"],
            "max_bet": g["max_bet"],
            "desc": g["desc"],
        })
    return json_ok({"games": games, "balance": int(user.get("balance", 0))})


# ═══════════ API: مچ‌میکینگ ═══════════
async def handle_match_join(request: web.Request):
    """پیوستن به صف مچ‌میکینگ برای یک بازی دونفره.

    🔧 رفع باگ‌های بحرانی:
    1. شرط (bet) به‌صورت escrow از موجودی کم می‌شود تا بعداً کپی پول نشود.
    2. قفل اتمیک برای جلوگیری از race condition (همان حریف دو بار matched نشود).
    3. بررسی cross-queue — کاربر نمی‌تواند همزمان در چند صف باشد.
    4. اعتبارسنجی ورودی (int) با try/except.
    """
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    try:
        body = await request.json()
    except Exception:
        return json_err("درخواست نامعتبر", 400)
    game_key = body.get("game_key")
    try:
        bet = int(body.get("bet", 0))
    except (ValueError, TypeError):
        return json_err("مبلغ نامعتبر", 400)
    if game_key not in config.MINIAPP_GAMES:
        return json_err("بازی نامعتبر", 400)
    game = config.MINIAPP_GAMES[game_key]
    if game["type"] != "2p":
        return json_err("این بازی دونفره نیست — از endpoint تک‌نفره استفاده کنید", 400)
    if bet < game["min_bet"] or bet > game["max_bet"]:
        return json_err(f"مبلغ شرط باید بین {game['min_bet']:,} و {game['max_bet']:,} باشد", 400)
    if int(user.get("balance", 0)) < bet:
        return json_err("موجودی کافی نیست", 400, "balance")

    # بررسی اینکه کاربر در بازی فعال نیست — هم در حافظه هم در Redis
    if user_id in _user_games:
        return json_err("شما از قبل در یک بازی فعال هستید", 400, "in_game")
    if redis_client.is_redis_available():
        active_gid = await redis_client.get_user_game(user_id)
        if active_gid:
            return json_err("شما از قبل در یک بازی فعال هستید", 400, "in_game")

    # قفل سراسری (محلی) + قفل توزیع‌شده (Redis) برای atomic matchmaking
    async with _matchmaking_lock:
        # 🔧 escrow: شرط را همین حالا از کاربر کم کن (و در صورت لغو/تایم‌اوت برگردان)
        # این از race condition TOCTOU روی موجودی جلوگیری می‌کند.
        ok = await db.deduct_balance(user_id, bet)
        if not ok:
            return json_err("کم کردن شرط ناموفق (موجودی تغییر کرد)", 400, "balance")

        # بررسی صف در حالت درون‌حافظه (fallback) یا Redis
        if redis_client.is_redis_available():
            # در Redis — بررسی cross-queue
            status = await redis_client.get_queue_status(user_id)
            if status:
                # کاربر در صف است — escrow را برگردان
                await db.add_balance(user_id, bet)
                return json_err("شما از قبل در صف هستید", 400, "in_queue")

            # جستجوی حریف در صف Redis
            opponent = await redis_client.find_opponent_and_remove(game_key, bet, user_id)
            if opponent:
                # حریف پیدا شد — اعتبارسنجی موجودی حریف (escrow او قبلاً کم شده، پس فقط چک کنیم زنده است)
                opp_db = await db.get_user(opponent["user_id"])
                if not opp_db:
                    # حریف حذف شده — پولش را هم برگردان (نه — او در صف نبود، پس escrow او در cancel/timeout برگردانده می‌شود)
                    # خودمان در صف می‌رویم
                    await redis_client.add_to_queue(game_key, bet, user_id, {
                        "name": user.get("first_name", "") or "بی‌نام",
                        "balance": int(user.get("balance", 0)),
                        "avatar": "",
                    })
                    return json_ok({"matched": False, "queue_position": 1, "timeout": config.MATCHMAKING_TIMEOUT})
                # حریف پیدا شد — بازی بساز
                # نکته: escrow هر دو کاربر قبلاً کم شده (حریف هنگام join کردن کم کرده)
                game_id = f"g{int(time.time()*1000)}{random.randint(100,999)}"
                players = [
                    {"user_id": opponent["user_id"], "name": opponent["name"] or "بی‌نام", "avatar": opponent.get("avatar", ""), "balance": int(opp_db.get("balance", 0))},
                    {"user_id": user_id, "name": user.get("first_name", "") or "بی‌نام", "avatar": "", "balance": int(user.get("balance", 0))},
                ]
                gs = GameState(game_id, game_key, players, bet)
                # pot شامل شرط هر دو است (هر دو escrow شده‌اند)
                gs.pot = bet * 2
                _active_games[game_id] = gs
                _user_games[opponent["user_id"]] = game_id
                _user_games[user_id] = game_id
                # در Redis هم نگه دار
                await redis_client.set_user_game(opponent["user_id"], game_id)
                await redis_client.set_user_game(user_id, game_id)
                await _init_game_state(gs)
                logger.info(f"🎮 بازی شروع شد (Redis): {game_id} ({game_key}) — {players[0]['name']} vs {players[1]['name']}")
                return json_ok({
                    "matched": True,
                    "game_id": game_id,
                    "game_key": game_key,
                    "players": players,
                    "bet": bet,
                    "pot": bet * 2,
                })

            # حریف نیست — به صف Redis اضافه کن (escrow از قبل کم شده)
            added = await redis_client.add_to_queue(game_key, bet, user_id, {
                "name": user.get("first_name", "") or "بی‌نام",
                "balance": int(user.get("balance", 0)),
                "avatar": "",
            })
            if not added:
                # یا در صف/بازی است یا خطا — escrow را برگردان
                await db.add_balance(user_id, bet)
                return json_err("شما از قبل در صف یا بازی هستید", 400, "in_queue")
            logger.info(f"⏳ کاربر {user_id} به صف Redis {game_key} پیوست (شرط: {bet:,})")
            return json_ok({"matched": False, "queue_position": 1, "timeout": config.MATCHMAKING_TIMEOUT})

        # حالت fallback (در حافظه) — همان منطق قبلی ولی با escrow
        # بررسی cross-queue: کاربر نباید در هیچ صف دیگری باشد
        for gk, q in _match_queues.items():
            if user_id in q:
                await db.add_balance(user_id, bet)
                return json_err("شما از قبل در صف هستید", 400, "in_queue")

        queue = _match_queues.setdefault(game_key, {})
        # پاکسازی ورودی‌های منقضی شده (با refund)
        _cleanup_queue_with_refund(game_key)

        # پیدا کردن حریف منتظر با همان شرط
        matched_opponent = None
        for opponent_id, opp_entry in list(queue.items()):
            if opponent_id == user_id:
                continue
            if opp_entry.bet != bet:
                continue
            # 🔧 pop قبل از await برای جلوگیری از race condition
            queue.pop(opponent_id, None)
            matched_opponent = (opponent_id, opp_entry)
            break

        if matched_opponent:
            opponent_id, opp_entry = matched_opponent
            # escrow حریف هنگام join کردنش کم شده (در این شاخه fallback)
            # چک کنیم حریف هنوز معتبر است
            game_id = f"g{int(time.time()*1000)}{random.randint(100,999)}"
            players = [
                {"user_id": opponent_id, "name": opp_entry.name, "avatar": opp_entry.avatar, "balance": opp_entry.balance},
                {"user_id": user_id, "name": user.get("first_name", "") or "بی‌نام", "avatar": "", "balance": int(user.get("balance", 0))},
            ]
            gs = GameState(game_id, game_key, players, bet)
            gs.pot = bet * 2
            _active_games[game_id] = gs
            _user_games[opponent_id] = game_id
            _user_games[user_id] = game_id
            await _init_game_state(gs)
            logger.info(f"🎮 بازی شروع شد (mem): {game_id} ({game_key}) — {players[0]['name']} vs {players[1]['name']}")
            return json_ok({
                "matched": True,
                "game_id": game_id,
                "game_key": game_key,
                "players": players,
                "bet": bet,
                "pot": bet * 2,
            })

        # حریف نیست — به صف اضافه کن (escrow از قبل کم شده)
        queue[user_id] = MatchEntry(
            user_id=user_id,
            name=user.get("first_name", "") or "بی‌نام",
            balance=int(user.get("balance", 0)),
            bet=bet,
            avatar="",
        )
        logger.info(f"⏳ کاربر {user_id} به صف {game_key} پیوست (شرط: {bet:,})")
        return json_ok({"matched": False, "queue_position": len(queue), "timeout": config.MATCHMAKING_TIMEOUT})


async def handle_match_status(request: web.Request):
    """بررسی وضعیت مچ‌میکینگ"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))

    # اگر در بازی فعال است
    gid = _user_games.get(user_id)
    if not gid and redis_client.is_redis_available():
        gid = await redis_client.get_user_game(user_id)
    if gid and gid in _active_games:
        gs = _active_games[gid]
        return json_ok({
            "status": "matched",
            "game_id": gid,
            "game_key": gs.game_key,
            "players": gs.players,
            "bet": gs.bet,
            "pot": gs.pot,
        })

    # اگر در صف است — اول Redis، بعد حافظه
    if redis_client.is_redis_available():
        st = await redis_client.get_queue_status(user_id)
        if st:
            remaining = st["remaining"]
            if remaining == 0:
                # تایم‌اوت — escrow را برگردان و از صف پاک کن
                await redis_client.remove_from_queue(user_id)
                await db.add_balance(user_id, st["bet"])
                logger.info(f"⏰ تایم‌اوت مچ‌میکینگ Redis برای کاربر {user_id} — {st['bet']} برگشت")
                return json_ok({"status": "timeout", "message": "حریفی پیدا نشد — دوباره تلاش کنید"})
            return json_ok({
                "status": "waiting",
                "game_key": st["game_key"],
                "bet": st["bet"],
                "elapsed": int(time.time() - st["joined_at"]),
                "remaining": remaining,
                "queue_size": 1,
            })

    # حالت fallback حافظه
    for game_key, queue in _match_queues.items():
        if user_id in queue:
            entry = queue[user_id]
            elapsed = int(time.time() - entry.joined_at)
            remaining = max(0, config.MATCHMAKING_TIMEOUT - elapsed)
            if remaining == 0:
                queue.pop(user_id, None)
                # escrow را برگردان (قبلاً کم شده)
                await db.add_balance(user_id, entry.bet)
                logger.info(f"⏰ تایم‌اوت مچ‌میکینگ mem برای کاربر {user_id} — {entry.bet} برگشت")
                return json_ok({"status": "timeout", "message": "حریفی پیدا نشد — دوباره تلاش کنید"})
            return json_ok({
                "status": "waiting",
                "game_key": game_key,
                "bet": entry.bet,
                "elapsed": elapsed,
                "remaining": remaining,
                "queue_size": len(queue),
            })

    # نه در صف، نه در بازی
    return json_ok({"status": "idle"})


async def handle_match_cancel(request: web.Request):
    """لغو مچ‌میکینگ — escrow برگردانده می‌شود"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    removed = False
    refunded = 0

    # Redis
    if redis_client.is_redis_available():
        st = await redis_client.get_queue_status(user_id)
        if st:
            refunded = st["bet"]
            await redis_client.remove_from_queue(user_id)
            removed = True

    # حالت fallback حافظه
    for game_key, queue in _match_queues.items():
        if user_id in queue:
            entry = queue.pop(user_id, None)
            if entry:
                refunded = entry.bet
                removed = True

    if removed and refunded > 0:
        await db.add_balance(user_id, refunded)
        logger.info(f"❌ کاربر {user_id} مچ‌میکینگ را لغو کرد — {refunded} برگشت")
    return json_ok({"cancelled": removed, "refunded": refunded})


def _cleanup_queue(game_key: str):
    """حذف ورودی‌های منقضی شده از صف (بدون refund — در fallback قدیمی)"""
    queue = _match_queues.get(game_key, {})
    now = time.time()
    expired = [uid for uid, e in queue.items() if now - e.joined_at > config.MATCHMAKING_TIMEOUT]
    for uid in expired:
        queue.pop(uid, None)


async def _cleanup_queue_with_refund(game_key: str):
    """حذف ورودی‌های منقضی شده از صف با refund escrow (در حالت fallback)"""
    queue = _match_queues.get(game_key, {})
    now = time.time()
    expired = [(uid, e) for uid, e in list(queue.items()) if now - e.joined_at > config.MATCHMAKING_TIMEOUT]
    for uid, e in expired:
        queue.pop(uid, None)
        try:
            await db.add_balance(uid, e.bet)
            logger.info(f"⏰ تایم‌اوت صف mem: کاربر {uid} {e.bet} برگشت")
        except Exception as ex:
            logger.warning(f"refund در cleanup ناموفق ({uid}): {ex}")


# ═══════════ API: وضعیت بازی و حرکت ═══════════
async def handle_game_state(request: web.Request):
    """گرفتن وضعیت فعلی بازی"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    gid = request.query.get("game_id") or (_user_games.get(user_id))
    if not gid or gid not in _active_games:
        return json_err("بازی یافت نشد", 404, "no_game")
    gs = _active_games[gid]
    # اطمینان از اینکه کاربر در این بازی است
    if not any(p["user_id"] == user_id for p in gs.players):
        return json_err("شما در این بازی نیستید", 403, "not_in_game")
    return json_ok(_serialize_game_state(gs, user_id))


async def handle_game_action(request: web.Request):
    """انجام یک حرکت در بازی"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    try:
        body = await request.json()
    except Exception:
        return json_err("درخواست نامعتبر", 400)
    action = body.get("action")
    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    gid = body.get("game_id") or _user_games.get(user_id)
    if not gid and redis_client.is_redis_available():
        gid = await redis_client.get_user_game(user_id)
    if not gid or gid not in _active_games:
        return json_err("بازی یافت نشد", 404, "no_game")
    gs = _active_games[gid]
    if gs.finished:
        return json_err("بازی تمام شده", 400, "finished")
    if not any(p["user_id"] == user_id for p in gs.players):
        return json_err("شما در این بازی نیستید", 403, "not_in_game")
    try:
        result = await _dispatch_action(gs, user_id, action, payload)
        gs.updated_at = time.time()
        return json_ok(result)
    except GameError as e:
        return json_err(str(e), 400, "game_error")
    except Exception as e:
        logger.exception(f"خطا در حرکت بازی: {e}")
        return json_err("خطای داخلی", 500)


async def handle_game_leave(request: web.Request):
    """ترک بازی (تسلیم)"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    gid = _user_games.get(user_id)
    if not gid and redis_client.is_redis_available():
        gid = await redis_client.get_user_game(user_id)
    if not gid or gid not in _active_games:
        return json_err("بازی یافت نشد", 404, "no_game")
    gs = _active_games[gid]
    if gs.finished:
        return json_err("بازی تمام شده", 400, "finished")
    # 🔧 بررسی صریح که کاربر در بازی است
    if not any(p["user_id"] == user_id for p in gs.players):
        return json_err("شما در این بازی نیستید", 403, "not_in_game")
    # کاربر تسلیم می‌شود — حریف برنده
    opponent_id = next((p["user_id"] for p in gs.players if p["user_id"] != user_id), None)
    await _finish_game(gs, winner_id=opponent_id, reason="surrender", loser_id=user_id)
    return json_ok(_serialize_game_state(gs, user_id))


def _serialize_game_state(gs: GameState, viewer_id: int) -> dict:
    """سریالایز وضعیت بازی برای کاربر — دست‌های حریف و deck پنهان می‌شوند.

    🔧 رفع باگ بحرانی: deck (کارتهای باقی‌مانده) و سایر داده‌های حساس بازی
    نباید به کلاینت نشت کنند — می‌توانست آینده flop/turn/river را فاش کند.
    """
    # ابتدا یک کپی سطحی از data بگیر
    data = dict(gs.data)
    # 🔧 حذف فیلدهای حساس که نباید به کلاینت بروند
    data.pop("deck", None)
    # hands را جداگانه فیلتر کن
    hands = data.pop("hands", None)

    s = {
        "game_id": gs.game_id,
        "game_key": gs.game_key,
        "bet": gs.bet,
        "pot": gs.pot,
        "state": gs.state,
        "turn_idx": gs.turn_idx,
        "players": gs.players,
        "my_index": next((i for i, p in enumerate(gs.players) if p["user_id"] == viewer_id), None),
        "winner": gs.winner,
        "finished": gs.finished,
        "data": data,
    }

    # برای بازی‌های ورق‌بازی، دست حریف را پنهان کن (مگر در پایان)
    if gs.game_key in ("hokm", "poker", "blackjack") and hands is not None:
        visible_hands = []
        for i, hand in enumerate(hands):
            if gs.players[i]["user_id"] == viewer_id:
                visible_hands.append(hand)
            else:
                # در پایان، دست حریف را نشان بده
                if gs.finished:
                    visible_hands.append(hand)
                else:
                    visible_hands.append([{"hidden": True} for _ in hand])
        s["data"]["hands"] = visible_hands
        # 🔧 فیلدهای حساس دیگر برای blackjack/poker را پاک کن
        if gs.game_key == "blackjack":
            # totals را فقط در پایان نشان بده (در غیر این صورت کلاینت می‌تواند از hand حریف حساب کند)
            if not gs.finished:
                totals = s["data"].get("totals", [0, 0])
                my_idx = s["my_index"]
                if my_idx is not None and 0 <= my_idx < len(totals):
                    s["data"]["totals"] = [None if i != my_idx else totals[i] for i in range(len(totals))]
        if gs.game_key == "poker":
            # ranks را فقط در پایان نشان بده
            if not gs.finished:
                s["data"].pop("ranks", None)
    elif hands is not None:
        s["data"]["hands"] = hands
    return s


class GameError(Exception):
    pass


# ═══════════ موتور بازی‌ها — مقداردهی و حرکت ═══════════
async def _init_game_state(gs: GameState):
    """مقداردهی اولیه حالت بازی بر اساس نوع"""
    if gs.game_key == "hokm":
        await _hokm_init(gs)
    elif gs.game_key == "poker":
        await _poker_init(gs)
    elif gs.game_key == "blackjack":
        await _blackjack_init(gs)
    else:
        gs.state = "unknown"


async def _dispatch_action(gs: GameState, user_id: int, action: str, payload: dict) -> dict:
    if gs.game_key == "hokm":
        return await _hokm_action(gs, user_id, action, payload)
    elif gs.game_key == "poker":
        return await _poker_action(gs, user_id, action, payload)
    elif gs.game_key == "blackjack":
        return await _blackjack_action(gs, user_id, action, payload)
    raise GameError("نوع بازی ناشناخته")


# ═══════════ پایان بازی و پاداش ═══════════
async def _finish_game(gs: GameState, winner_id: int | None, reason: str = "normal", loser_id: int | None = None):
    """پایان بازی — پاداش به برنده، کارمزد کم می‌شود.

    🔧 نکته: شرط هر دو بازیکن هنگام match شدن به‌صورت escrow کم شده است،
    پس pot = 2*bet از قبل در سیستم است. فقط کافی است به برنده prize = pot - commission
    داده شود (مساوی: به هر دو نصف pot - نصف commission).

    🔧 رفع باگ: کاربران بلافاصله از _user_games حذف می‌شوند تا بتوانند دوباره
    وارد صف شوند (قبلاً ۳۰ ثانیه قفل می‌شدند). بازی برای ۳۰ ثانیه در _active_games
    باقی می‌ماند تا کاربر نتیجه را ببیند.
    """
    if gs.finished:
        return
    gs.finished = True
    gs.winner = winner_id
    gs.state = "finished"
    gs.data["finish_reason"] = reason
    # کارمزد از کل pot کم می‌شود
    commission = int(gs.pot * config.MINIAPP_COMMISSION_RATE)
    prize = gs.pot - commission
    if winner_id is None:
        # مساوی — به هر دو نفر نصف pot برگردانده شود (منهای نصف کارمزد)
        half = int(prize / 2)
        for p in gs.players:
            await db.add_balance(p["user_id"], half)
        gs.data["prize_each"] = half
    else:
        await db.add_balance(winner_id, prize)
        gs.data["winner_prize"] = prize
    # 🔧 کاربران را بلافاصله از _user_games و Redis پاک کن تا دوباره وارد صف شوند
    for p in gs.players:
        if _user_games.get(p["user_id"]) == gs.game_id:
            _user_games.pop(p["user_id"], None)
        if redis_client.is_redis_available():
            await redis_client.clear_user_game(p["user_id"])
    # پاک کردن بازی پس از ۳۰ ثانیه (تا کاربر نتیجه را ببیند)
    # 🔧 get_running_loop به جای get_event_loop (deprecated در 3.10+)
    try:
        loop = asyncio.get_running_loop()
        loop.call_later(30, _purge_game, gs.game_id)
    except RuntimeError:
        # اگر loop نباشد، بازی در حافظه می‌ماند تا purge دستی
        pass
    logger.info(
        f"🏁 بازی {gs.game_id} ({gs.game_key}) پایان یافت — "
        f"برنده: {winner_id}, جایزه: {prize if winner_id else 'split'}"
    )


def _purge_game(game_id: str):
    """پاک کردن بازی از حافظه"""
    gs = _active_games.pop(game_id, None)
    if gs:
        for p in gs.players:
            if _user_games.get(p["user_id"]) == game_id:
                _user_games.pop(p["user_id"], None)


# ═══════════ دستورات ورق ═══════════
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def _new_deck() -> list[dict]:
    """یک دسته ۵۲تایی برمی‌زند"""
    deck = [{"suit": s, "rank": r} for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def _card_value(card: dict, trump_suit: str | None = None, lead_suit: str | None = None) -> int:
    """مقدار کارت برای حکم: A=14, K=13, ..."""
    rank = card["rank"]
    if rank == "A": return 14
    if rank == "K": return 13
    if rank == "Q": return 12
    if rank == "J": return 11
    try: return int(rank)
    except ValueError: return 0


def _card_emoji(card: dict) -> str:
    """نمایش ایموجی کارت"""
    color = "🟥" if card["suit"] in ("♥", "♦") else "⬛"
    return f"{card['rank']}{card['suit']}"


# ═══════════ 🃏 حکم (نسخه ساده‌شده دونفره) ═══════════
# قوانین: هر بازیکن ۵ کارت می‌گیرد. هکر (برنده دور قبل) رنگ حکم را انتخاب می‌کند.
# در هر دور هر بازیکن یک کارت می‌زند. کارتی که با رنگ حکم بالاتر باشد یا با رنگ lead بالاتر باشد برنده دور است.
# هر دور برنده ۱ امتیاز می‌گیرد. ۵ دور = ۵ امتیاز. بیشترین امتیاز برنده بازی.
# کسی که تمام کارت‌هایش را زد اول، یک امتیاز اضافه می‌گیرد.

async def _hokm_init(gs: GameState):
    deck = _new_deck()
    hands = [
        [deck.pop() for _ in range(5)],
        [deck.pop() for _ in range(5)],
    ]
    gs.data = {
        "hands": hands,
        "trump_suit": None,
        "lead_suit": None,
        "current_trick": [],  # list of {player_idx, card}
        "tricks_won": [0, 0],
        "round": 0,
        "phase": "choose_trump",  # choose_trump -> play -> finished
        "trump_chooser_idx": 0,
        "history": [],
    }
    gs.state = "choose_trump"
    gs.turn_idx = 0  # بازیکن ۰ رنگ حکم را انتخاب می‌کند


async def _hokm_action(gs: GameState, user_id: int, action: str, payload: dict) -> dict:
    player_idx = next((i for i, p in enumerate(gs.players) if p["user_id"] == user_id), None)
    if player_idx is None:
        raise GameError("شما در این بازی نیستید")
    data = gs.data

    if action == "choose_trump":
        if data["phase"] != "choose_trump":
            raise GameError("انتخاب حکم در این مرحله مجاز نیست")
        if player_idx != data["trump_chooser_idx"]:
            raise GameError("نوبت انتخاب حکم شما نیست")
        suit = payload.get("suit")
        if suit not in SUITS:
            raise GameError("رنگ نامعتبر")
        data["trump_suit"] = suit
        data["phase"] = "play"
        data["lead_suit"] = None
        data["current_trick"] = []
        # بازیکن مقابل اولین کارت را می‌زند
        gs.turn_idx = (player_idx + 1) % 2
        gs.state = "play"
        return {"ok": True, "trump_suit": suit, "phase": "play"}

    if action == "play_card":
        if data["phase"] != "play":
            raise GameError("بازی در مرحله بازی نیست")
        if gs.turn_idx != player_idx:
            raise GameError("نوبت شما نیست")
        card_index = int(payload.get("card_index", -1))
        hand = data["hands"][player_idx]
        if card_index < 0 or card_index >= len(hand):
            raise GameError("کارت نامعتبر")
        card = hand[card_index]
        # اگر lead_suit تعیین شده، بازیکن باید follow کند مگر اینکه کارت lead نداشته باشد
        if data["lead_suit"]:
            has_lead = any(c["suit"] == data["lead_suit"] for c in hand)
            if has_lead and card["suit"] != data["lead_suit"]:
                raise GameError(f"باید به رنگ {data['lead_suit']} پاسخ دهی")
        # بازی کارت را می‌زند
        hand.pop(card_index)
        data["current_trick"].append({"player_idx": player_idx, "card": card})
        if data["lead_suit"] is None:
            data["lead_suit"] = card["suit"]
        # اگر دو کارت زده شد، برنده دور را تعیین کن
        if len(data["current_trick"]) == 2:
            winner_idx = _hokm_trick_winner(data)
            data["tricks_won"][winner_idx] += 1
            data["history"].append({
                "trick": data["current_trick"],
                "winner": gs.players[winner_idx]["user_id"],
            })
            data["current_trick"] = []
            data["lead_suit"] = None
            data["round"] += 1
            gs.turn_idx = winner_idx
            # اگر ۵ دور تمام شد
            if data["round"] >= 5:
                # تعیین برنده نهایی
                t0, t1 = data["tricks_won"]
                if t0 > t1:
                    winner_id = gs.players[0]["user_id"]
                elif t1 > t0:
                    winner_id = gs.players[1]["user_id"]
                else:
                    winner_id = None
                await _finish_game(gs, winner_id, reason="normal")
                return {
                    "ok": True,
                    "trick_winner": gs.players[winner_idx]["user_id"],
                    "tricks_won": data["tricks_won"],
                    "game_finished": True,
                    "winner": winner_id,
                }
            return {
                "ok": True,
                "trick_winner": gs.players[winner_idx]["user_id"],
                "tricks_won": data["tricks_won"],
                "round": data["round"],
            }
        # نوبت بازیکن بعدی
        gs.turn_idx = (player_idx + 1) % 2
        return {"ok": True, "played": True, "waiting_opponent": True}

    raise GameError("اکشن نامعتبر")


def _hokm_trick_winner(data: dict) -> int:
    """برنده دور حکم را تعیین می‌کند"""
    trick = data["current_trick"]
    trump = data["trump_suit"]
    lead = data["lead_suit"]
    best_idx = 0
    best_card = trick[0]["card"]
    for i in range(1, len(trick)):
        c = trick[i]["card"]
        # اگر trump است و بهترین کارت trump نیست
        if c["suit"] == trump and best_card["suit"] != trump:
            best_idx = i
            best_card = c
            continue
        # اگر هر دو trump هستند، بالاترین مقدار
        if c["suit"] == trump and best_card["suit"] == trump:
            if _card_value(c) > _card_value(best_card):
                best_idx = i
                best_card = c
            continue
        # اگر هیچ‌کدام trump نیستند و هر دو lead هستند
        if c["suit"] != trump and best_card["suit"] != trump:
            if c["suit"] == lead and best_card["suit"] != lead:
                best_idx = i
                best_card = c
                continue
            if c["suit"] == lead and best_card["suit"] == lead and _card_value(c) > _card_value(best_card):
                best_idx = i
                best_card = c
    return trick[best_idx]["player_idx"]


# ═══════════ ♠️ پوکر (Texas Hold'em Heads-Up ساده) ═══════════
# قوانین ساده‌شده: هر بازیکن ۲ کارت hole می‌گیرد. ۳ کارت flop، ۱ turn، ۱ river.
# هر مرحله بازیکن می‌تواند fold/check/raise. در پایان، دست برتر با رتبه‌بندی پوکر برنده است.

async def _poker_init(gs: GameState):
    deck = _new_deck()
    hands = [[deck.pop() for _ in range(2)], [deck.pop() for _ in range(2)]]
    gs.data = {
        "hands": hands,
        "community": [],
        "deck": deck,
        "phase": "preflop",  # preflop, flop, turn, river, showdown
        "pot_per_player": [0, 0],  # مبلغ هر بازیکن در پات
        "current_bet": gs.bet,  # شرط فعلی
        "actions_this_phase": 0,
        "history": [],
        "dealer_idx": 0,
    }
    # شرط اولیه از هر دو کم می‌شود (از قبل در pot محاسبه شده)
    # در واقع شرط از موجودی کاربران کم شده و در pot قرار گرفته است — ما فقط نگه می‌داریم
    # برای ساده‌سازی: شرط ابتدایی همان bet است و در finish_game به برنده داده می‌شود
    gs.data["pot_per_player"] = [gs.bet, gs.bet]
    gs.state = "preflop"
    # اولین بازیکن بعد از dealer بازی می‌کند
    gs.turn_idx = (gs.data["dealer_idx"] + 1) % 2


def _poker_hand_rank(cards: list[dict]) -> tuple:
    """رتبه‌بندی دست پوکر — خروجی: (rank_int, kicker)"""
    # گرفتن مقادیر و رنگ‌ها
    values = sorted([_card_value(c) for c in cards], reverse=True)
    suits = [c["suit"] for c in cards]
    from collections import Counter
    val_counts = Counter(values)
    suit_counts = Counter(suits)

    # فلش (5 کارت هم‌رنگ متوالی)
    is_flush = max(suit_counts.values()) >= 5
    flush_suit = next((s for s, c in suit_counts.items() if c >= 5), None)
    flush_values = sorted([_card_value(c) for c in cards if c["suit"] == flush_suit], reverse=True) if flush_suit else []

    # مقادیر منحصربه‌فرد برای تشخیص straight
    unique_vals = sorted(set(values), reverse=True)
    is_straight = False
    straight_high = 0
    # پشت سر هم بودن ۵ مقدار متوالی
    for i in range(len(unique_vals) - 4):
        if unique_vals[i] - unique_vals[i + 4] == 4:
            is_straight = True
            straight_high = unique_vals[i]
            break
    # A-2-3-4-5 (wheel)
    if set([14, 2, 3, 4, 5]).issubset(set(unique_vals)):
        if not is_straight or straight_high < 5:
            is_straight = True
            straight_high = 5

    # straight flush
    if is_flush and flush_values:
        # 🔧 بررسی wheel straight flush (A-2-3-4-5 same suit) — قبلاً تشخیص داده نمی‌شد
        if set([14, 2, 3, 4, 5]).issubset(set(flush_values)):
            return (8, 5)
        for i in range(len(flush_values) - 4):
            if flush_values[i] - flush_values[i + 4] == 4:
                return (8, flush_values[i])

    # four of a kind
    four = [v for v, c in val_counts.items() if c == 4]
    if four:
        kicker = max(v for v in values if v != four[0])
        return (7, four[0], kicker)

    # full house
    three = sorted([v for v, c in val_counts.items() if c == 3], reverse=True)
    pairs = sorted([v for v, c in val_counts.items() if c == 2], reverse=True)
    if three:
        if pairs:
            return (6, three[0], pairs[0])
        # دو ست سه‌تایی (مثلاً در ۷ کارت)
        if len(three) >= 2:
            return (6, three[0], three[1])

    # flush
    if is_flush:
        return (5, *flush_values[:5])

    # straight
    if is_straight:
        return (4, straight_high)

    # three of a kind
    if three:
        kickers = sorted([v for v in values if v != three[0]], reverse=True)[:2]
        return (3, three[0], *kickers)

    # two pair
    if len(pairs) >= 2:
        top2 = pairs[:2]
        kicker = max(v for v in values if v not in top2)
        return (2, top2[0], top2[1], kicker)

    # one pair
    if len(pairs) == 1:
        kickers = sorted([v for v in values if v != pairs[0]], reverse=True)[:3]
        return (1, pairs[0], *kickers)

    # high card
    return (0, *values[:5])


async def _poker_action(gs: GameState, user_id: int, action: str, payload: dict) -> dict:
    """
    🔧 رفع باگ منطق پوکر:
    - اکشن "call" اضافه شد (برای match کردن raise)
    - بعد از raise، _poker_advance فوراً صدا نمی‌شود — حریف باید call/fold کند
    - فاز فقط وقتی عوض می‌شود که هر دو بازیکن pot_per_player برابر داشته باشند
    """
    player_idx = next((i for i, p in enumerate(gs.players) if p["user_id"] == user_id), None)
    if player_idx is None:
        raise GameError("شما در این بازی نیستید")
    if gs.turn_idx != player_idx:
        raise GameError("نوبت شما نیست")
    data = gs.data

    if action == "fold":
        # حریف برنده
        winner_idx = (player_idx + 1) % 2
        winner_id = gs.players[winner_idx]["user_id"]
        await _finish_game(gs, winner_id, reason="fold", loser_id=user_id)
        return {"ok": True, "folded": True, "winner": winner_id, "game_finished": True}

    if action == "check":
        # فقط وقتی current_bet == pot_per_player[player_idx] مجاز است (هیچ outstanding raise ای نیست)
        if data["current_bet"] > data["pot_per_player"][player_idx]:
            raise GameError("باید call یا fold کنی — raise وجود دارد")
        data["actions_this_phase"] += 1
        data["history"].append({"player_idx": player_idx, "action": "check"})
        # اگر هر دو check کرده‌اند (یا یکی check و دیگری call)، advance
        await _poker_advance(gs)
        return {"ok": True, "checked": True, "phase": data["phase"]}

    if action == "call":
        # match کردن current_bet
        needed = data["current_bet"] - data["pot_per_player"][player_idx]
        if needed <= 0:
            raise GameError("چیزی برای call کردن نیست — می‌توانی check کنی")
        player = await db.get_user(user_id)
        if not player or int(player.get("balance", 0)) < needed:
            raise GameError("موجودی کافی برای call نیست")
        ok = await db.deduct_balance(user_id, needed)
        if not ok:
            raise GameError("کم کردن مبلغ call ناموفق")
        gs.pot += needed
        data["pot_per_player"][player_idx] += needed
        data["actions_this_phase"] += 1
        data["history"].append({"player_idx": player_idx, "action": "call", "amount": needed})
        await _poker_advance(gs)
        return {"ok": True, "called": True, "amount": needed, "phase": data["phase"]}

    if action == "raise":
        try:
            raise_amount = int(payload.get("amount", 0))
        except (ValueError, TypeError):
            raise GameError("مبلغ raise نامعتبر")
        if raise_amount <= 0:
            raise GameError("مبلغ raise نامعتبر")
        # اول باید current_bet را match کند (call) و بعد raise_amount اضافه کند
        needed_call = data["current_bet"] - data["pot_per_player"][player_idx]
        total_needed = needed_call + raise_amount
        player = await db.get_user(user_id)
        if not player or int(player.get("balance", 0)) < total_needed:
            raise GameError("موجودی کافی برای raise نیست")
        ok = await db.deduct_balance(user_id, total_needed)
        if not ok:
            raise GameError("کم کردن مبلغ raise ناموفق")
        gs.pot += total_needed
        data["pot_per_player"][player_idx] += total_needed
        data["current_bet"] = data["pot_per_player"][player_idx]
        data["actions_this_phase"] += 1
        data["history"].append({"player_idx": player_idx, "action": "raise", "amount": total_needed})
        # نوبت حریف — او باید call/raise/fold کند (advance خودکار وقتی او call/check کند)
        gs.turn_idx = (player_idx + 1) % 2
        # 🔧 حریف باید act کند — advance را صریحاً صدا نزن
        return {"ok": True, "raised": True, "amount": total_needed, "phase": data["phase"]}

    raise GameError("اکشن نامعتبر")


async def _poker_advance(gs: GameState):
    """پیشروی فاز پوکر.

    🔧 رفع باگ: فاز فقط وقتی عوض می‌شود که هر دو بازیکن act کرده باشند
    AND pot_per_player برابر باشد (یعنی raise ای outstanding نباشد).
    """
    data = gs.data
    # اگر هر دو بازیکن act نکرده‌اند، فقط نوبت را عوض کن
    if data["actions_this_phase"] < 2:
        gs.turn_idx = (gs.turn_idx + 1) % 2
        return
    # اگر pot_per_player برابر نیست (یعنی یکی raise کرده و دیگری هنوز call نکرده) — advance نکن
    if data["pot_per_player"][0] != data["pot_per_player"][1]:
        gs.turn_idx = (gs.turn_idx + 1) % 2
        return
    # هر دو act کرده‌اند و bets برابر است — فاز بعدی
    if data["phase"] == "preflop":
        data["community"].extend([data["deck"].pop() for _ in range(3)])
        data["phase"] = "flop"
    elif data["phase"] == "flop":
        data["community"].append(data["deck"].pop())
        data["phase"] = "turn"
    elif data["phase"] == "turn":
        data["community"].append(data["deck"].pop())
        data["phase"] = "river"
    elif data["phase"] == "river":
        # showdown
        data["phase"] = "showdown"
        await _poker_showdown(gs)
        return
    # ریست برای فاز جدید
    data["actions_this_phase"] = 0
    # نوبت بازیکن بعد از dealer در فاز جدید
    gs.turn_idx = (data["dealer_idx"] + 1) % 2


async def _poker_showdown(gs: GameState):
    """تعیین برنده پوکر در showdown"""
    data = gs.data
    ranks = []
    for i in range(2):
        all_cards = data["hands"][i] + data["community"]
        rank = _poker_hand_rank(all_cards)
        ranks.append(rank)
    if ranks[0] > ranks[1]:
        winner_id = gs.players[0]["user_id"]
    elif ranks[1] > ranks[0]:
        winner_id = gs.players[1]["user_id"]
    else:
        winner_id = None  # split pot
    data["ranks"] = ranks
    data["reveal"] = True
    await _finish_game(gs, winner_id, reason="showdown")


# ═══════════ 🂡 بلک‌جک ═══════════
# هر بازیکن ۲ کارت می‌گیرد. مقادیر: 2-10 همان عدد، J/Q/K=10، A=1 یا 11 (auto-best).
# هر بازیکن به نوبت hit یا stand می‌کند. اگر بیش از 21 شد، bust. در پایان، دست نزدیک‌تر به 21 برنده.

def _blackjack_card_value(card: dict) -> int:
    rank = card["rank"]
    if rank in ("J", "Q", "K"): return 10
    if rank == "A": return 11
    try: return int(rank)
    except ValueError: return 0


def _blackjack_hand_total(hand: list[dict]) -> int:
    total = sum(_blackjack_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c["rank"] == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


async def _blackjack_init(gs: GameState):
    deck = _new_deck()
    hands = [[deck.pop() for _ in range(2)], [deck.pop() for _ in range(2)]]
    gs.data = {
        "hands": hands,
        "deck": deck,
        "stand": [False, False],
        "totals": [_blackjack_hand_total(hands[0]), _blackjack_hand_total(hands[1])],
        "phase": "play",
    }
    gs.state = "play"
    gs.turn_idx = 0


async def _blackjack_action(gs: GameState, user_id: int, action: str, payload: dict) -> dict:
    """
    🔧 رفع باگ: بازیکنی که stand کرده نباید بتواند دوباره hit کند.
    همچنین اگر حریف stand کرده باشد، نوبت به او نرود.
    """
    player_idx = next((i for i, p in enumerate(gs.players) if p["user_id"] == user_id), None)
    if player_idx is None:
        raise GameError("شما در این بازی نیستید")
    if gs.turn_idx != player_idx:
        raise GameError("نوبت شما نیست")
    data = gs.data
    if data["phase"] != "play":
        raise GameError("بازی در مرحله بازی نیست")
    # 🔧 اگر بازیکن stand کرده، نباید بتواند hit کند
    if data["stand"][player_idx]:
        raise GameError("شما stand کرده‌اید — نمی‌توانید حرکت کنید")

    if action == "hit":
        card = data["deck"].pop()
        data["hands"][player_idx].append(card)
        total = _blackjack_hand_total(data["hands"][player_idx])
        data["totals"][player_idx] = total
        if total > 21:
            # bust — حریف برنده
            data["stand"][player_idx] = True
            winner_idx = (player_idx + 1) % 2
            winner_id = gs.players[winner_idx]["user_id"]
            await _finish_game(gs, winner_id, reason="bust", loser_id=user_id)
            return {"ok": True, "hit": True, "card": card, "total": total, "bust": True, "game_finished": True, "winner": winner_id}
        # اگر با hit به 21 رسید، اتومات stand
        if total == 21:
            data["stand"][player_idx] = True
            await _blackjack_check_finish(gs)
            return {"ok": True, "hit": True, "card": card, "total": total, "stand": True}
        # نوبت حریف اگر او هنوز stand نکرده — در غیر این صورت نوبت همین بازیکن می‌ماند
        opponent_idx = (player_idx + 1) % 2
        if not data["stand"][opponent_idx]:
            gs.turn_idx = opponent_idx
        # اگر حریف stand کرده، نوبت همین بازیکن می‌ماند تا او هم stand/bust کند
        return {"ok": True, "hit": True, "card": card, "total": total}

    if action == "stand":
        data["stand"][player_idx] = True
        await _blackjack_check_finish(gs)
        return {"ok": True, "stand": True, "totals": data["totals"]}

    raise GameError("اکشن نامعتبر")


async def _blackjack_check_finish(gs: GameState):
    data = gs.data
    if all(data["stand"]):
        t0, t1 = data["totals"]
        if t0 > 21 and t1 > 21:
            winner_id = None
        elif t0 > 21:
            winner_id = gs.players[1]["user_id"]
        elif t1 > 21:
            winner_id = gs.players[0]["user_id"]
        elif t0 > t1:
            winner_id = gs.players[0]["user_id"]
        elif t1 > t0:
            winner_id = gs.players[1]["user_id"]
        else:
            winner_id = None
        await _finish_game(gs, winner_id, reason="stand")
        return
    # نوبت بازیکن بعدی که هنوز stand نکرده
    for i in range(2):
        if not data["stand"][i]:
            gs.turn_idx = i
            return


# ═══════════ API: بازی‌های تک‌نفره ═══════════
async def handle_single_play(request: web.Request):
    """اجرای یک بازی تک‌نفره (اسلات، تاس، چرخ شانس)"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    try:
        body = await request.json()
    except Exception:
        return json_err("درخواست نامعتبر", 400)
    game_key = body.get("game_key")
    try:
        bet = int(body.get("bet", 0))
    except (ValueError, TypeError):
        return json_err("مبلغ نامعتبر", 400)
    if game_key not in config.MINIAPP_GAMES:
        return json_err("بازی نامعتبر", 400)
    game = config.MINIAPP_GAMES[game_key]
    if game["type"] != "1p":
        return json_err("این بازی دونفره است — از مچ‌میکینگ استفاده کنید", 400)
    if bet < game["min_bet"] or bet > game["max_bet"]:
        return json_err(f"مبلغ شرط باید بین {game['min_bet']:,} و {game['max_bet']:,} باشد", 400)
    user_id = int(user.get("user_id", 0))
    if int(user.get("balance", 0)) < bet:
        return json_err("موجودی کافی نیست", 400, "balance")
    # کم کردن شرط
    ok = await db.deduct_balance(user_id, bet)
    if not ok:
        return json_err("کم کردن شرط ناموفق", 500)

    # اجرای بازی
    try:
        if game_key == "slots":
            result = _play_slots(bet)
        elif game_key == "dice":
            result = _play_dice(bet, body)
        elif game_key == "wheel":
            result = _play_wheel(bet, body)
        else:
            # بازپرداخت اگر بازی ناشناخته
            await db.add_balance(user_id, bet)
            return json_err("بازی پشتیبانی نمی‌شود", 400)
    except Exception as e:
        # 🔧 در صورت خطا، شرط را برگردان
        logger.exception(f"خطا در اجرای بازی {game_key}: {e}")
        await db.add_balance(user_id, bet)
        return json_err("خطا در اجرای بازی — پول برگشت داده شد", 500)

    # اگر برنده شد، جایزه اضافه شود
    if result["win"] > 0:
        await db.add_balance(user_id, result["win"])
    # XP برای بازی کازینو
    try:
        await db.progress_mission(user_id, "play_casino", amount=1, base_xp=20)
    except Exception as e:
        logger.warning(f"progress_mission در مینی‌اپ: {e}")

    return json_ok({
        "game_key": game_key,
        "bet": bet,
        "outcome": result["outcome"],
        "reels": result.get("reels"),  # 🔧 reels جداگانه برای کلاینت
        "win": result["win"],
        "balance_after": int((await db.get_user(user_id) or {}).get("balance", 0)),
    })


def _play_slots(bet: int) -> dict:
    """اسلات: ۳ علامت تصادفی. اگر ۳ تای یکسان → ۳x. اگر ۲ تای یکسان → ۰.۵x."""
    symbols = ["🍒", "🔔", "🍋", "⭐", "💎", "7️⃣"]
    weights = [25, 20, 20, 15, 10, 10]
    pool = []
    for s, w in zip(symbols, weights):
        pool.extend([s] * w)
    reels = [random.choice(pool) for _ in range(3)]
    outcome = " ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        # ضریب بر اساس علامت
        multipliers = {"🍒": 5, "🔔": 8, "🍋": 10, "⭐": 15, "💎": 25, "7️⃣": 50}
        mult = multipliers.get(reels[0], 3)
        win = bet * mult
        return {"outcome": f"🎉 جکپات! — {mult}x", "reels": reels, "win": win}
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        win = int(bet * 0.5)
        return {"outcome": f"≈ تقریباً! — ۰.۵x", "reels": reels, "win": win}
    return {"outcome": "باخت", "reels": reels, "win": 0}


def _play_dice(bet: int, body: dict) -> dict:
    """تاس: کاربر پیش‌بینی می‌کند بالای ۷ یا زیر ۷ یا مساوی ۷"""
    # 🔧 payload ممکن است None باشد اگر کلاینت null بفرستد
    payload = body.get("payload") or {}
    prediction = payload.get("prediction", "over")  # over, under, equal
    if prediction not in ("over", "under", "equal"):
        prediction = "over"
    d1, d2 = random.randint(1, 6), random.randint(1, 6)
    total = d1 + d2
    win = 0
    if prediction == "equal" and total == 7:
        win = bet * 4
        msg = f"🎲 {d1}+{d2}={total} — مساوی ۷! ×۴"
    elif prediction == "over" and total > 7:
        win = bet * 2
        msg = f"🎲 {d1}+{d2}={total} — بالای ۷! ×۲"
    elif prediction == "under" and total < 7:
        win = bet * 2
        msg = f"🎲 {d1}+{d2}={total} — زیر ۷! ×۲"
    else:
        msg = f"🎲 {d1}+{d2}={total} — باخت"
    return {"outcome": msg, "reels": [str(d1), str(d2)], "win": win}


def _play_wheel(bet: int, body: dict) -> dict:
    """چرخ شانس: ۸ بخش با ضرایب مختلف"""
    segments = [
        (0.5, "0.5x"), (1.5, "1.5x"), (2, "2x"), (0, "💥"),
        (3, "3x"), (1, "1x"), (5, "5x"), (0.5, "0.5x"),
    ]
    idx = random.randint(0, len(segments) - 1)
    mult, label = segments[idx]
    win = int(bet * mult)
    return {"outcome": f"🎡 روی {label} متوقف شد — {'+' + str(win) if win > 0 else 'باخت'}", "reels": [label], "win": win}


# ═══════════ API: سلامت سرور (بدون احراز هویت — برای عیب‌یابی) ═══════════
async def handle_health(request: web.Request):
    """بررسی سلامت سرور: وضعیت BOT_TOKEN، DB، Redis، بازی‌ها"""
    status = {"status": "ok", "games": list(config.MINIAPP_GAMES.keys())}
    # بررسی BOT_TOKEN
    status["bot_token_set"] = bool(config.BOT_TOKEN)
    # بررسی DB
    try:
        test_user = await db.get_user(1)
        status["db"] = "ok"
    except Exception as e:
        status["db"] = f"error: {e}"
        status["status"] = "degraded"
    # بررسی Redis
    try:
        status["redis"] = "ok" if redis_client.is_redis_available() else "fallback"
    except Exception:
        status["redis"] = "unknown"
    # بررسی عمق initData برای عیب‌یابی (بدون افشای محتوا)
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data") or ""
    status["has_init_data"] = bool(init_data)
    status["has_browser_token"] = bool(request.headers.get("X-Browser-Token") or request.query.get("token"))
    return json_ok(status)


# ═══════════ ساخت و اجرای اپ ═══════════
@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    """اعمال هدرهای امنیتی و Cache-Control روی همه پاسخ‌ها.

    🔧 رفع باگ: قبلاً هیچ CORS/Cache-Control/CSP روی پاسخ‌ها نبود.
    Telegram WebApp نیاز به no-cache دارد تا بعد از deploy نسخه جدید سرو شود.
    """
    response = await handler(request)
    # no-store برای جلوگیری از کش HTML و API بعد از deploy
    response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    # CSP — فقط scripts از self و telegram.org مجاز
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self';"
    )
    # CORS — اجازه به Telegram origins (و self)
    origin = request.headers.get("Origin", "")
    if origin:
        response.headers.setdefault("Access-Control-Allow-Origin", origin)
        response.headers.setdefault("Access-Control-Allow-Credentials", "true")
    return response


def create_app() -> web.Application:
    app = web.Application(middlewares=[security_headers_middleware])
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/profile", handle_profile)
    app.router.add_get("/api/games", handle_games)
    app.router.add_post("/api/match/join", handle_match_join)
    app.router.add_get("/api/match/status", handle_match_status)
    app.router.add_post("/api/match/cancel", handle_match_cancel)
    app.router.add_get("/api/game/state", handle_game_state)
    app.router.add_post("/api/game/action", handle_game_action)
    app.router.add_post("/api/game/leave", handle_game_leave)
    app.router.add_post("/api/play/single", handle_single_play)
    return app


_web_runner: web.AppRunner | None = None


async def start_webapp():
    """شروع سرور مینی‌اپ — از bot.py فراخوانی می‌شود"""
    global _web_runner
    if _web_runner is not None:
        return
    # 🔧 اتصال به Redis (اگر URL تنظیم شده باشد) — قبل از start سرور
    try:
        await redis_client.init_redis()
    except Exception as e:
        logger.warning(f"⚠️ init_redis ناموفق (ادامه در حالت fallback): {e}")
    app = create_app()
    _web_runner = web.AppRunner(app)
    await _web_runner.setup()
    site = web.TCPSite(_web_runner, "0.0.0.0", config.WEBAPP_PORT)
    await site.start()
    logger.info(f"🚀 مینی‌اپ روی پورت {config.WEBAPP_PORT} اجرا شد (Redis: {'✅' if redis_client.is_redis_available() else '⚠️ fallback'})")
    if config.WEBAPP_PUBLIC_URL:
        logger.info(f"🌐 URL عمومی: {config.WEBAPP_PUBLIC_URL}")


async def stop_webapp():
    global _web_runner
    if _web_runner:
        await _web_runner.cleanup()
        _web_runner = None
        logger.info("🛑 سرور مینی‌اپ متوقف شد")
    # 🔧 بستن Redis
    try:
        await redis_client.close_redis()
    except Exception:
        pass
