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

logger = logging.getLogger("zarcoin.webapp")

# ═══════════ مسیرها ═══════════
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MINIAPP_HTML = TEMPLATES_DIR / "miniapp.html"

# ═══════════ ساختار داده‌های درون‌حافظه‌ای ═══════════
# صف مچ‌میکینگ: { game_key: { user_id: MatchEntry } }
_match_queues: dict[str, dict[int, "MatchEntry"]] = {}

# بازی‌های فعال: { game_id: GameState }
_active_games: dict[str, "GameState"] = {}

# نگاشت user_id → game_id (برای پیدا کردن سریع بازی کاربر)
_user_games: dict[int, str] = {}


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
    """
    if not init_data_raw:
        return None
    bot_token = config.BOT_TOKEN
    if not bot_token:
        logger.error("❌ BOT_TOKEN تنظیم نشده — اعتبارسنجی initData غیرممکن")
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
    except Exception:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # ساخت data-check-string با کلیدها به ترتیب الفبایی
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    # کلید محرمانه: HMAC(SHA256, bot_token, "WebAppData")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        logger.warning("⚠️ initData نامعتبر — هش مطابقت ندارد")
        return None

    # اعتبارسنجی auth_date (پیر بودن بیش از ۱ روز رد شود)
    auth_date = parsed.get("auth_date")
    if auth_date:
        try:
            if time.time() - int(auth_date) > 86400:
                logger.warning("⚠️ initData خیلی قدیمی است")
                return None
        except ValueError:
            return None

    user_json = parsed.get("user")
    if not user_json:
        return None
    try:
        user = json.loads(user_json)
    except Exception:
        return None
    return user


async def _get_user_for_request(request: web.Request) -> dict | None:
    """استخراج و اعتبارسنجی کاربر از درخواست"""
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.query.get("init_data")
        or (await _read_body_initdata(request))
    )
    tg_user = validate_init_data(init_data)
    if not tg_user:
        return None
    user_id = tg_user.get("id")
    if not user_id:
        return None
    # اطمینان از وجود کاربر در DB
    db_user = await db.get_user(int(user_id))
    if not db_user:
        # اگر هنوز ثبت نشده، یک رکورد موقت می‌سازیم
        try:
            db_user = await db.ensure_user(type("U", (), {
                "id": int(user_id),
                "first_name": tg_user.get("first_name", ""),
                "last_name": tg_user.get("last_name", ""),
                "username": tg_user.get("username", ""),
                "language_code": tg_user.get("language_code", "fa"),
                "is_bot": False,
            })())
        except Exception as e:
            logger.exception(f"ensure_user در مینی‌اپ ناموفق: {e}")
            return None
    return db_user


async def _read_body_initdata(request: web.Request) -> str:
    """برای POST با body شامل init_data"""
    try:
        body = await request.json()
        if isinstance(body, dict):
            return body.get("init_data", "")
    except Exception:
        pass
    return ""


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
    """پیوستن به صف مچ‌میکینگ برای یک بازی دونفره"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    try:
        body = await request.json()
    except Exception:
        return json_err("درخواست نامعتبر", 400)
    game_key = body.get("game_key")
    bet = int(body.get("bet", 0))
    if game_key not in config.MINIAPP_GAMES:
        return json_err("بازی نامعتبر", 400)
    game = config.MINIAPP_GAMES[game_key]
    if game["type"] != "2p":
        return json_err("این بازی دونفره نیست — از endpoint تک‌نفره استفاده کنید", 400)
    if bet < game["min_bet"] or bet > game["max_bet"]:
        return json_err(f"مبلغ شرط باید بین {game['min_bet']:,} و {game['max_bet']:,} باشد", 400)
    if int(user.get("balance", 0)) < bet:
        return json_err("موجودی کافی نیست", 400, "balance")

    # اگر کاربر از قبل در یک بازی فعال است، نپذیر
    if user_id in _user_games:
        return json_err("شما از قبل در یک بازی فعال هستید", 400, "in_game")

    # اگر کاربر از قبل در صف است، نپذیر
    queue = _match_queues.setdefault(game_key, {})
    if user_id in queue:
        return json_err("شما از قبل در صف هستید", 400, "in_queue")

    # پاکسازی ورودی‌های منقضی شده
    _cleanup_queue(game_key)

    # پیدا کردن حریف منتظر با همان شرط
    for opponent_id, opp_entry in list(queue.items()):
        if opponent_id == user_id:
            continue
        if opp_entry.bet != bet:
            continue
        # اطمینان از موجودی حریف
        opp_db = await db.get_user(opponent_id)
        if not opp_db or int(opp_db.get("balance", 0)) < bet:
            queue.pop(opponent_id, None)
            continue
        # حریف پیدا شد — بازی بساز
        queue.pop(opponent_id, None)
        game_id = f"g{int(time.time()*1000)}{random.randint(100,999)}"
        players = [
            {"user_id": opponent_id, "name": opp_entry.name, "avatar": opp_entry.avatar, "balance": int(opp_db.get("balance", 0))},
            {"user_id": user_id, "name": user.get("first_name", "") or "بی‌نام", "avatar": "", "balance": int(user.get("balance", 0))},
        ]
        gs = GameState(game_id, game_key, players, bet)
        _active_games[game_id] = gs
        _user_games[opponent_id] = game_id
        _user_games[user_id] = game_id
        # مقداردهی اولیه بازی
        await _init_game_state(gs)
        logger.info(f"🎮 بازی شروع شد: {game_id} ({game_key}) — {players[0]['name']} vs {players[1]['name']}")
        return json_ok({
            "matched": True,
            "game_id": game_id,
            "game_key": game_key,
            "players": players,
            "bet": bet,
            "pot": bet * 2,
        })

    # حریف نیست — به صف اضافه کن
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

    # اگر در صف است
    for game_key, queue in _match_queues.items():
        if user_id in queue:
            entry = queue[user_id]
            elapsed = int(time.time() - entry.joined_at)
            remaining = max(0, config.MATCHMAKING_TIMEOUT - elapsed)
            if remaining == 0:
                queue.pop(user_id, None)
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
    """لغو مچ‌میکینگ"""
    user = await _get_user_for_request(request)
    if not user:
        return json_err("احراز هویت ناموفق", 401, "auth")
    user_id = int(user.get("user_id", 0))
    removed = False
    for game_key, queue in _match_queues.items():
        if user_id in queue:
            queue.pop(user_id, None)
            removed = True
            logger.info(f"❌ کاربر {user_id} مچ‌میکینگ {game_key} را لغو کرد")
    return json_ok({"cancelled": removed})


def _cleanup_queue(game_key: str):
    """حذف ورودی‌های منقضی شده از صف"""
    queue = _match_queues.get(game_key, {})
    now = time.time()
    expired = [uid for uid, e in queue.items() if now - e.joined_at > config.MATCHMAKING_TIMEOUT]
    for uid in expired:
        queue.pop(uid, None)


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
    payload = body.get("payload", {}) or {}
    gid = body.get("game_id") or _user_games.get(user_id)
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
    if not gid or gid not in _active_games:
        return json_err("بازی یافت نشد", 404, "no_game")
    gs = _active_games[gid]
    if gs.finished:
        return json_err("بازی تمام شده", 400, "finished")
    # کاربر تسلیم می‌شود — حریف برنده
    opponent_id = next((p["user_id"] for p in gs.players if p["user_id"] != user_id), None)
    await _finish_game(gs, winner_id=opponent_id, reason="surrender", loser_id=user_id)
    return json_ok(_serialize_game_state(gs, user_id))


def _serialize_game_state(gs: GameState, viewer_id: int) -> dict:
    """سریالایز وضعیت بازی برای کاربر — دست‌های حریف پنهان می‌شوند"""
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
        "data": gs.data,
    }
    # برای بازی‌های ورق‌بازی، دست حریف را پنهان کن
    if gs.game_key in ("hokm", "poker", "blackjack"):
        hands = gs.data.get("hands", [])
        visible_hands = []
        for i, hand in enumerate(hands):
            if gs.players[i]["user_id"] == viewer_id:
                visible_hands.append(hand)
            else:
                # برای پوکر/بلک‌جک، در پایان دست حریف را نشان بده
                if gs.finished:
                    visible_hands.append(hand)
                else:
                    visible_hands.append([{"hidden": True} for _ in hand])
        s["data"] = dict(gs.data)
        s["data"]["hands"] = visible_hands
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
    """پایان بازی — پاداش به برنده، کارمزد کم می‌شود"""
    if gs.finished:
        return
    gs.finished = True
    gs.winner = winner_id
    gs.state = "finished"
    gs.data["finish_reason"] = reason
    # کارمزد از کل پاداش کم می‌شود
    commission = int(gs.pot * config.MINIAPP_COMMISSION_RATE)
    prize = gs.pot - commission
    if winner_id is None:
        # مساوی — به هر دو نفر نصف شرط برگردانده شود
        half = gs.bet - int(commission / 2)
        for p in gs.players:
            await db.add_balance(p["user_id"], half)
        gs.data["prize_each"] = half
    else:
        await db.add_balance(winner_id, prize)
        gs.data["winner_prize"] = prize
    # پاک کردن بازی پس از مدت کوتاه (تا کاربر نتیجه را ببیند)
    asyncio.get_event_loop().call_later(30, _purge_game, gs.game_id)
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
        data["actions_this_phase"] += 1
        data["history"].append({"player_idx": player_idx, "action": "check"})
        await _poker_advance(gs)
        return {"ok": True, "checked": True, "phase": data["phase"]}

    if action == "raise":
        raise_amount = int(payload.get("amount", 0))
        if raise_amount <= 0:
            raise GameError("مبلغ raise نامعتبر")
        player = await db.get_user(user_id)
        if not player or int(player.get("balance", 0)) < raise_amount:
            raise GameError("موجودی کافی برای raise نیست")
        await db.deduct_balance(user_id, raise_amount)
        gs.pot += raise_amount
        data["pot_per_player"][player_idx] += raise_amount
        data["current_bet"] = data["pot_per_player"][player_idx]
        data["actions_this_phase"] += 1
        data["history"].append({"player_idx": player_idx, "action": "raise", "amount": raise_amount})
        # بعد از raise، حریف باید call یا fold کند
        gs.turn_idx = (player_idx + 1) % 2
        # در ساده‌سازی، هر دو بازیکن یک اکشن داشته باشند کافی است
        await _poker_advance(gs)
        return {"ok": True, "raised": True, "amount": raise_amount, "phase": data["phase"]}

    raise GameError("اکشن نامعتبر")


async def _poker_advance(gs: GameState):
    """پیشروی فاز پوکر"""
    data = gs.data
    # هر دو بازیکن باید در این فاز اکشن کرده باشند
    if data["actions_this_phase"] < 2:
        gs.turn_idx = (gs.turn_idx + 1) % 2
        return
    # فاز بعدی
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
    data["actions_this_phase"] = 0
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
    player_idx = next((i for i, p in enumerate(gs.players) if p["user_id"] == user_id), None)
    if player_idx is None:
        raise GameError("شما در این بازی نیستید")
    if gs.turn_idx != player_idx:
        raise GameError("نوبت شما نیست")
    data = gs.data
    if data["phase"] != "play":
        raise GameError("بازی در مرحله بازی نیست")

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
        # نوبت حریف اگر هر دو stand شده باشند، در غیر این صورت می‌تواند ادامه دهد
        gs.turn_idx = (player_idx + 1) % 2
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
    bet = int(body.get("bet", 0))
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
        return {"outcome": f"🎉 جکپات! {outcome} — {mult}x", "win": win}
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        win = int(bet * 0.5)
        return {"outcome": f"≈ تقریباً! {outcome} — ۰.۵x", "win": win}
    return {"outcome": f"{outcome} — باخت", "win": 0}


def _play_dice(bet: int, body: dict) -> dict:
    """تاس: کاربر پیش‌بینی می‌کند بالای ۷ یا زیر ۷ یا مساوی ۷"""
    prediction = body.get("payload", {}).get("prediction", "over")  # over, under, equal
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
    return {"outcome": msg, "win": win}


def _play_wheel(bet: int, body: dict) -> dict:
    """چرخ شانس: ۸ بخش با ضرایب مختلف"""
    segments = [
        (0.5, "0.5x"), (1.5, "1.5x"), (2, "2x"), (0, "💥"),
        (3, "3x"), (1, "1x"), (5, "5x"), (0.5, "0.5x"),
    ]
    idx = random.randint(0, len(segments) - 1)
    mult, label = segments[idx]
    win = int(bet * mult)
    return {"outcome": f"🎡 روی {label} متوقف شد — {'+' + str(win) if win > 0 else 'باخت'}", "win": win}


# ═══════════ API: خروج از مینی‌اپ ═══════════
async def handle_health(request: web.Request):
    return json_ok({"status": "ok", "games": list(config.MINIAPP_GAMES.keys())})


# ═══════════ ساخت و اجرای اپ ═══════════
def create_app() -> web.Application:
    app = web.Application()
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
    # middleware برای CORS و no-cache
    return app


_web_runner: web.AppRunner | None = None


async def start_webapp():
    """شروع سرور مینی‌اپ — از bot.py فراخوانی می‌شود"""
    global _web_runner
    if _web_runner is not None:
        return
    app = create_app()
    _web_runner = web.AppRunner(app)
    await _web_runner.setup()
    site = web.TCPSite(_web_runner, "0.0.0.0", config.WEBAPP_PORT)
    await site.start()
    logger.info(f"🚀 مینی‌اپ روی پورت {config.WEBAPP_PORT} اجرا شد")
    if config.WEBAPP_PUBLIC_URL:
        logger.info(f"🌐 URL عمومی: {config.WEBAPP_PUBLIC_URL}")


async def stop_webapp():
    global _web_runner
    if _web_runner:
        await _web_runner.cleanup()
        _web_runner = None
        logger.info("🛑 سرور مینی‌اپ متوقف شد")
