# -*- coding: utf-8 -*-
"""
🎰 کازینو زر — منطق سمت سرور بازی‌های مینی‌اپ
─────────────────────────────────────────────
تک‌نفره : چرخ شانس، موشک (کرش)، شیر یا خط، کارت شانس، رولت، مین‌یاب، بالا‌پایین
دونفره  : پوکر تگزاس هولدم (رِیز آزاد + آل‌این)، حکم، بلک‌جک

⚠️ منوی متنی کازینوی قدیم حذف شده — همه‌ی بازی‌ها داخل مینی‌اپ هستند.
توابع قدیمی (handle_callback و ...) فقط پیام «منتقل شد» نشان می‌دهند تا هیچ جای ربات خطا ندهد.
"""
import itertools
import logging
import math
import random

import db

logger = logging.getLogger("zarcoin.casino")
rng = random.SystemRandom()

# ═══════════════════════════════════════════════
# ═══════════ سازگاری با نسخه‌ی قدیمی ربات ═══════════
# ═══════════════════════════════════════════════
MOVED_TEXT = "🎰 همه‌ی بازی‌ها به «کازینو» (مینی‌اپ) منتقل شدند!\nاز منوی اصلی روی دکمه‌ی 🎰 کازینو بزن."


def miniapp_keyboard(text: str = "🎰 ورود به کازینو", back: bool = True):
    """کیبورد باز کردن مینی‌اپ (در گروه و پیوی کار می‌کند)"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[miniapp_button(text)]]
    if back:
        rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def miniapp_button(text: str = "🎰 کازینو"):
    """دکمه مینی‌اپ — اولویت با لینک عمیق t.me/bot/app (در گروه هم کار می‌کند)"""
    from telegram import InlineKeyboardButton, WebAppInfo
    import config
    deep = (getattr(config, "WEBAPP_DEEP_LINK", "") or "").strip()
    if deep:
        return InlineKeyboardButton(text, url=deep)
    url = (getattr(config, "WEBAPP_PUBLIC_URL", "") or "").strip()
    if url:
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))
    return InlineKeyboardButton(text, callback_data="menu:main")


def casino_menu_kb(user_id=None):
    return miniapp_keyboard()


async def legacy_notice(*args, **kwargs):
    """جایگزین همه‌ی هندلرهای قدیمی بازی‌های متنی"""
    for a in args:
        if hasattr(a, "answer") and hasattr(a, "data") and hasattr(a, "from_user"):
            try:
                await a.answer(MOVED_TEXT, show_alert=True)
            except Exception:
                pass
            return
    for a in args:
        msg = getattr(a, "effective_message", None) or getattr(a, "message", None)
        if msg is not None and hasattr(msg, "reply_text"):
            try:
                await msg.reply_text(MOVED_TEXT, reply_markup=miniapp_keyboard())
            except Exception:
                pass
            return


handle_callback = legacy_notice


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return legacy_notice


# ═══════════ ابزار ═══════════
def _to_float(v, default=None):
    if isinstance(v, bool):
        return default
    try:
        if isinstance(v, str):
            v = v.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).replace("٫", ".").strip()
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or math.isinf(f):
        return default
    return f


def _to_int(v, default=None):
    f = _to_float(v, None)
    if f is None or abs(f) > 1e15:
        return default
    return int(f)


async def _balance(uid: int) -> int:
    try:
        u = await db.get_user(uid)
        return int(u["balance"]) if u else 0
    except Exception:
        return 0


def _fmt(n) -> str:
    return f"{int(n):,}"


# ═══════════ کارت‌ها ═══════════
SUITS = "SHDC"
SUIT_SORT = "SHCD"


def new_deck() -> list:
    d = [(r, s) for s in SUITS for r in range(2, 15)]
    rng.shuffle(d)
    return d


def cj(c) -> dict:
    return {"r": c[0], "s": c[1], "id": f"{c[0]}{c[1]}"}


def rand_card():
    return (rng.randint(2, 14), rng.choice(SUITS))


# ═══════════════════════════════════════════════
# ═══════════ تک‌نفره‌ی آنی ═══════════
# هر تابع: body → dict شامل mult (ضریب پرداخت روی کل شرط)
# پارامتر نامعتبر → ValueError
# ═══════════════════════════════════════════════
WHEEL_SEGMENTS = [0, 1.5, 0, 2, 0.5, 0, 5, 0, 1.5, 0.5, 0, 0.5]  # EV ≈ 0.96


def play_wheel(body: dict) -> dict:
    idx = rng.randrange(len(WHEEL_SEGMENTS))
    return {"index": idx, "mult": WHEEL_SEGMENTS[idx]}


def play_crash(body: dict) -> dict:
    t = _to_float(body.get("target"))
    if t is None or t < 1.01 or t > 100:
        raise ValueError("ضریب هدف باید بین ۱٫۰۱ تا ۱۰۰ باشد")
    t = round(t, 2)
    r = rng.random()
    crash = max(1.0, min(math.floor((0.96 / (1.0 - r)) * 100) / 100, 1000.0))
    won = crash >= t
    return {"crash": crash, "target": t, "won": won, "mult": t if won else 0}


def play_coin(body: dict) -> dict:
    side = body.get("side")
    if side not in ("heads", "tails"):
        raise ValueError("شیر یا خط را انتخاب کن")
    result = rng.choice(("heads", "tails"))
    won = result == side
    return {"result": result, "won": won, "mult": 1.9 if won else 0}


def play_card(body: dict) -> dict:
    """کارت شانس: رنگ (×۱٫۹) یا خال (×۳٫۸)"""
    pick = body.get("pick")
    if pick not in ("red", "black", "S", "H", "D", "C"):
        raise ValueError("رنگ یا خال را انتخاب کن")
    c = rand_card()
    red = c[1] in "HD"
    if pick in ("red", "black"):
        won = (pick == "red") == red
        mult = 1.9 if won else 0
    else:
        won = c[1] == pick
        mult = 3.8 if won else 0
    return {"card": cj(c), "won": won, "mult": mult}


ROULETTE_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
ROULETTE_BETS = {"red": 2, "black": 2, "even": 2, "odd": 2, "low": 2, "high": 2,
                 "dozen1": 3, "dozen2": 3, "dozen3": 3, "number": 36}


def play_roulette(body: dict) -> dict:
    bt = body.get("type")
    if bt not in ROULETTE_BETS:
        raise ValueError("نوع شرط رولت نامعتبر است")
    num = None
    if bt == "number":
        num = _to_int(body.get("number"), -1)
        if not 0 <= num <= 36:
            raise ValueError("عدد باید بین ۰ تا ۳۶ باشد")
    n = rng.randint(0, 36)
    color = "green" if n == 0 else ("red" if n in ROULETTE_RED else "black")
    won = {
        "red": color == "red", "black": color == "black",
        "even": n != 0 and n % 2 == 0, "odd": n % 2 == 1,
        "low": 1 <= n <= 18, "high": 19 <= n <= 36,
        "dozen1": 1 <= n <= 12, "dozen2": 13 <= n <= 24, "dozen3": 25 <= n <= 36,
        "number": n == num,
    }[bt]
    return {"number": n, "color": color, "won": won, "mult": ROULETTE_BETS[bt] if won else 0}


# ═══════════ مین‌یاب ═══════════
MINES_CELLS = 25
MINES_EDGE = 0.97
MINES_COUNTS = (1, 3, 5, 10, 15, 20)


def mines_mult(k: int, m: int) -> float:
    if k <= 0:
        return 1.0
    p = 1.0
    for i in range(k):
        p *= (MINES_CELLS - i) / (MINES_CELLS - m - i)
    return round(p * MINES_EDGE, 4)


def mines_start(bet: int, count: int) -> dict:
    if count not in MINES_COUNTS:
        raise ValueError("تعداد مین نامعتبر است")
    return {"type": "mines", "bet": bet, "count": count,
            "mines": set(rng.sample(range(MINES_CELLS), count)), "revealed": []}


def mines_reveal(s: dict, idx: int):
    """خروجی: 'lose' | 'win' (همه‌ی خانه‌ها باز شد) | None"""
    if not 0 <= idx < MINES_CELLS or idx in s["revealed"]:
        raise ValueError("خانه نامعتبر است")
    if idx in s["mines"]:
        s["finished"] = True
        s["boom"] = idx
        return "lose"
    s["revealed"].append(idx)
    if len(s["revealed"]) >= MINES_CELLS - s["count"]:
        return "win"
    return None


def mines_payout(s: dict) -> int:
    return int(s["bet"] * mines_mult(len(s["revealed"]), s["count"]))


def mines_view(s: dict, reveal: bool = False) -> dict:
    k = len(s["revealed"])
    safe_left = MINES_CELLS - s["count"] - k
    v = {"type": "mines", "bet": s["bet"], "count": s["count"], "revealed": list(s["revealed"]),
         "mult": mines_mult(k, s["count"]),
         "next_mult": mines_mult(k + 1, s["count"]) if safe_left > 0 else None,
         "potential": mines_payout(s) if k else 0, "finished": s.get("finished", False)}
    if reveal or s.get("finished"):
        v["mines"] = sorted(s["mines"])
        if "boom" in s:
            v["boom"] = s["boom"]
    return v


# ═══════════ بالا پایین ═══════════
def hilo_start(bet: int) -> dict:
    c = rand_card()
    return {"type": "hilo", "bet": bet, "card": c, "mult": 1.0, "steps": 0, "history": [c]}


def hilo_guess(s: dict, direction: str):
    """خروجی: (won: bool, next_card)"""
    if direction not in ("hi", "lo"):
        raise ValueError("حدس نامعتبر است")
    r = s["card"][0]
    p = (14 - r) / 13 if direction == "hi" else (r - 2) / 13
    if p <= 0:
        raise ValueError("این حدس ممکن نیست")
    nxt = rand_card()
    won = nxt[0] > r if direction == "hi" else nxt[0] < r
    s["history"].append(nxt)
    s["card"] = nxt
    if won:
        s["mult"] = min(s["mult"] * 0.97 / p, 1000.0)
        s["steps"] += 1
    else:
        s["finished"] = True
    return won, nxt


def hilo_payout(s: dict) -> int:
    return int(s["bet"] * s["mult"])


def hilo_view(s: dict, reveal: bool = False) -> dict:
    r = s["card"][0]
    p_hi, p_lo = (14 - r) / 13, (r - 2) / 13
    return {"type": "hilo", "bet": s["bet"], "card": cj(s["card"]), "mult": round(s["mult"], 4),
            "steps": s["steps"],
            "hi_mult": round(s["mult"] * 0.97 / p_hi, 2) if p_hi > 0 else None,
            "lo_mult": round(s["mult"] * 0.97 / p_lo, 2) if p_lo > 0 else None,
            "potential": hilo_payout(s) if s["steps"] else 0,
            "history": [cj(c) for c in s["history"][-8:]], "finished": s.get("finished", False)}


# ═══════════════════════════════════════════════
# ═══════════ دونفره ═══════════
# رابط: init(g) / action(g, uid, body) → خطا یا None / view(g, uid)
# پایان بازی: g.finish(winner_uid | None, reason)
# ═══════════════════════════════════════════════

# ─── بلک‌جک ───
def bj_value(cards) -> int:
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


def _bj_resolve(g):
    a, b = g.uids()
    va, vb = bj_value(g.data["hands"][a]), bj_value(g.data["hands"][b])
    if va > 21 and vb > 21:
        g.finish(None, "هر دو سوختید — مساوی")
    elif va > 21:
        g.finish(b, f"{g.name(a)} سوخت ({va})")
    elif vb > 21:
        g.finish(a, f"{g.name(b)} سوخت ({vb})")
    elif va == vb:
        g.finish(None, f"امتیاز برابر ({va}) — مساوی")
    else:
        w = a if va > vb else b
        g.finish(w, f"{g.name(w)} با {max(va, vb)} در برابر {min(va, vb)} برد")


async def bj_init(g):
    deck = new_deck()
    a, b = g.uids()
    hands = {a: [deck.pop(), deck.pop()], b: [deck.pop(), deck.pop()]}
    done = {u: bj_value(hands[u]) == 21 for u in (a, b)}
    g.data = {"deck": deck, "hands": hands, "done": done}
    g.waiting = {u for u in (a, b) if not done[u]}
    if not g.waiting:
        _bj_resolve(g)


async def bj_action(g, uid, body):
    if uid not in g.waiting:
        return "نوبت تو تمام شده — منتظر حریف باش"
    d = g.data
    act = body.get("action")
    if act == "hit":
        d["hands"][uid].append(d["deck"].pop())
        if bj_value(d["hands"][uid]) >= 21:
            d["done"][uid] = True
            g.waiting.discard(uid)
    elif act == "stand":
        d["done"][uid] = True
        g.waiting.discard(uid)
    else:
        return "حرکت نامعتبر است"
    if not g.waiting:
        _bj_resolve(g)
    return None


def bj_view(g, uid) -> dict:
    d = g.data
    o = g.opp(uid)
    show = g.finished
    return {"my_cards": [cj(c) for c in d["hands"][uid]], "my_value": bj_value(d["hands"][uid]),
            "my_done": d["done"][uid],
            "opp_cards": [cj(c) if (show or i == 0) else None for i, c in enumerate(d["hands"][o])],
            "opp_value": bj_value(d["hands"][o]) if show else None, "opp_done": d["done"][o]}


# ─── حکم دونفره ───
def _sort_hand(hand):
    return sorted(hand, key=lambda c: (SUIT_SORT.index(c[1]), c[0]))


async def hokm_init(g):
    deck = new_deck()
    a, b = g.uids()
    hakem = rng.choice((a, b))
    g.data = {"deck": deck, "hands": {hakem: _sort_hand([deck.pop() for _ in range(5)]), g.opp(hakem): []},
              "hakem": hakem, "trump": None, "phase": "trump", "table": [], "tricks": {a: 0, b: 0},
              "last_trick": None}
    g.waiting = {hakem}


async def hokm_action(g, uid, body):
    d = g.data
    if uid not in g.waiting:
        return "نوبت تو نیست"
    if d["phase"] == "trump":
        suit = body.get("suit")
        if suit not in SUITS:
            return "خال حکم نامعتبر است"
        d["trump"] = suit
        hakem, other = d["hakem"], g.opp(d["hakem"])
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
        g.finish(w, f"{g.name(w)} هفت دست برد")
        return None
    g.waiting = {w}
    return None


def hokm_view(g, uid) -> dict:
    d = g.data
    o = g.opp(uid)
    hand = d["hands"][uid]
    led = d["table"][0][1][1] if d["table"] else None
    has_led = led is not None and any(c[1] == led for c in hand)
    my_turn = uid in g.waiting and d["phase"] == "play"
    cards = []
    for c in hand:
        j = cj(c)
        j["playable"] = bool(my_turn and (not has_led or c[1] == led))
        cards.append(j)
    lt = None
    if d["last_trick"]:
        lt = {"cards": [{"card": cj(c), "mine": u == uid} for u, c in d["last_trick"]["cards"]],
              "i_won": d["last_trick"]["winner"] == uid}
    return {"phase": d["phase"], "trump": d["trump"], "i_am_hakem": d["hakem"] == uid, "my_hand": cards,
            "opp_count": len(d["hands"][o]), "table": [{"card": cj(c), "mine": u == uid} for u, c in d["table"]],
            "tricks_me": d["tricks"][uid], "tricks_opp": d["tricks"][o], "last_trick": lt}


# ─── پوکر تگزاس هولدم (هدز‌آپ، رِیز آزاد) ───
HAND_NAMES = ["کارت بالا", "یک جفت", "دو جفت", "سه‌تایی", "استریت", "فلاش", "فول هاوس", "چهارتایی", "استریت فلاش"]
STREET_NAMES = ["پیش از فلاپ", "فلاپ", "ترن", "ریور", "شودان"]
HOLDEM_MAX_RAISES = 4  # حداکثر رِیز در هر مرحله


def eval5(cs) -> tuple:
    ranks = sorted((c[0] for c in cs), reverse=True)
    flush = len({c[1] for c in cs}) == 1
    uniq = sorted(set(ranks), reverse=True)
    sh = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            sh = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            sh = 5
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    shape = [n for _, n in groups]
    gr = [r for r, _ in groups]
    if sh and flush:
        return (8, sh)
    if shape[0] == 4:
        return (7, *gr)
    if shape == [3, 2]:
        return (6, *gr)
    if flush:
        return (5, *ranks)
    if sh:
        return (4, sh)
    if shape[0] == 3:
        return (3, *gr)
    if shape == [2, 2, 1]:
        return (2, *gr)
    if shape[0] == 2:
        return (1, *gr)
    return (0, *ranks)


def best_hand(cards) -> tuple:
    if len(cards) < 5:
        ranks = sorted((c[0] for c in cards), reverse=True)
        if len(ranks) == 2 and ranks[0] == ranks[1]:
            return (1, ranks[0])
        return (0, *ranks)
    return max(eval5(x) for x in itertools.combinations(cards, 5))


def hand_name(score) -> str:
    return "رویال فلاش" if score[0] == 8 and score[1] == 14 else HAND_NAMES[score[0]]


def _holdem_min_raise(g) -> int:
    return max(1, g.bet // 10)


def _hlog(g, text):
    g.data["log"] = (g.data["log"] + [text])[-6:]


def _holdem_showdown(g):
    d = g.data
    a, b = g.uids()
    d["street"] = 4
    d["showdown"] = True
    sa, sb = best_hand(d["hole"][a] + d["board"]), best_hand(d["hole"][b] + d["board"])
    d["final"] = {a: hand_name(sa), b: hand_name(sb)}
    if sa == sb:
        g.finish(None, f"دست برابر ({hand_name(sa)}) — پات تقسیم شد")
    else:
        w = a if sa > sb else b
        g.finish(w, f"{g.name(w)} با {d['final'][w]} برد")


def _holdem_next_street(g):
    d = g.data
    a, b = g.uids()
    if d["street"] >= 3:
        _holdem_showdown(g)
        return
    d["street"] += 1
    d["sbets"] = {a: 0, b: 0}
    d["acted"] = set()
    d["raises"] = 0
    _hlog(g, f"— {STREET_NAMES[d['street']]} —")
    g.waiting = {b}


async def holdem_init(g):
    deck = new_deck()
    a, b = g.uids()
    g.data = {"hole": {a: [deck.pop(), deck.pop()], b: [deck.pop(), deck.pop()]},
              "board": [deck.pop() for _ in range(5)],  # فقط سمت سرور
              "street": 0, "sbets": {a: 0, b: 0}, "acted": set(), "raises": 0,
              "log": [], "showdown": False, "allin": False, "bal": {a: 0, b: 0}}
    g.waiting = {a}


async def holdem_prepare(g):
    """قبل از ساخت view: موجودی بازیکنان برای محاسبه سقف رِیز"""
    for u in g.uids():
        g.data["bal"][u] = await _balance(u)


def _raise_bounds(g, uid):
    d = g.data
    o = g.opp(uid)
    diff = max(0, d["sbets"][o] - d["sbets"][uid])
    mx = max(0, min(d["bal"].get(uid, 0) - diff, d["bal"].get(o, 0)))
    return diff, _holdem_min_raise(g), mx


async def holdem_action(g, uid, body):
    d = g.data
    if uid not in g.waiting:
        return "نوبت تو نیست"
    act = body.get("action")
    o = g.opp(uid)
    diff = d["sbets"][o] - d["sbets"][uid]
    name = g.name(uid)
    if act == "fold":
        _hlog(g, f"{name} فولد کرد")
        g.finish(o, f"{name} فولد کرد")
        return None
    if act == "check":
        if diff > 0:
            return "باید کال یا فولد کنی"
        _hlog(g, f"{name} چک کرد")
    elif act == "call":
        if diff <= 0:
            _hlog(g, f"{name} چک کرد")
        elif await db.deduct_balance(uid, diff):
            g.contrib[uid] += diff
            d["sbets"][uid] += diff
            _hlog(g, f"{name} کال کرد ({_fmt(diff)})")
        else:
            # آل‌این کوتاه: هر چه دارد می‌گذارد و مازاد رِیز به حریف برمی‌گردد
            pay = max(0, await _balance(uid))
            if pay > 0 and not await db.deduct_balance(uid, pay):
                pay = 0
            short = diff - pay
            g.contrib[uid] += pay
            d["sbets"][uid] += pay
            if short > 0:
                g.contrib[o] -= short
                d["sbets"][o] -= short
                await db.add_balance(o, short)
            d["allin"] = True
            _hlog(g, f"{name} آل‌این کال کرد ({_fmt(pay)})")
            _holdem_showdown(g)
            return None
    elif act == "raise":
        if d["raises"] >= HOLDEM_MAX_RAISES:
            return "سقف رِیز این مرحله پر شده"
        await holdem_prepare(g)
        diff0, mn, mx = _raise_bounds(g, uid)
        amount = _to_int(body.get("amount"), 0)
        if mx <= 0:
            return "موجودی تو یا حریف برای رِیز کافی نیست"
        if amount > mx:
            return f"حداکثر رِیز {_fmt(mx)} است"
        if amount < min(mn, mx):
            return f"حداقل رِیز {_fmt(min(mn, mx))} است"
        total = diff0 + amount
        if not await db.deduct_balance(uid, total):
            return "موجودی کافی نیست"
        g.contrib[uid] += total
        d["sbets"][uid] += total
        d["raises"] += 1
        d["acted"] = {uid}
        _hlog(g, f"{name} رِیز کرد (+{_fmt(amount)})" + (" — آل‌این!" if amount == mx else ""))
        g.waiting = {o}
        return None
    else:
        return "حرکت نامعتبر است"
    d["acted"].add(uid)
    if len(d["acted"]) >= 2 and d["sbets"][uid] == d["sbets"][o]:
        _holdem_next_street(g)
    else:
        g.waiting = {o}
    return None


def holdem_view(g, uid) -> dict:
    d = g.data
    o = g.opp(uid)
    street = d["street"]
    n = 5 if d["showdown"] else [0, 3, 4, 5, 5][min(street, 4)]
    board = d["board"][:n]
    diff, mn, mx = _raise_bounds(g, uid)
    show_opp = d["showdown"]
    return {"street": street, "street_name": STREET_NAMES[min(street, 4)], "board": [cj(c) for c in board],
            "my_cards": [cj(c) for c in d["hole"][uid]],
            "opp_cards": [cj(c) for c in d["hole"][o]] if show_opp else [None, None],
            "my_hand": hand_name(best_hand(d["hole"][uid] + board)),
            "opp_hand": d.get("final", {}).get(o) if show_opp else None,
            "can_check": diff <= 0, "call_amount": diff,
            "min_raise": min(mn, mx) if mx > 0 else 0, "max_raise": mx,
            "can_raise": d["raises"] < HOLDEM_MAX_RAISES and mx > 0,
            "my_balance": d["bal"].get(uid, 0),
            "my_contrib": g.contrib[uid], "opp_contrib": g.contrib[o],
            "log": d["log"], "showdown": d["showdown"]}


# ═══════════ ثبت بازی‌ها برای webapp ═══════════
SOLO_INSTANT = {
    "wheel": play_wheel, "crash": play_crash, "coin": play_coin,
    "card": play_card, "roulette": play_roulette,
}

MINIAPP_GAMES = {
    "holdem": {"init": holdem_init, "action": holdem_action, "view": holdem_view, "prepare": holdem_prepare},
    "hokm": {"init": hokm_init, "action": hokm_action, "view": hokm_view},
    "blackjack": {"init": bj_init, "action": bj_action, "view": bj_view},
}


# ═══════════ اتصال خودکار امکانات جدید به ربات ═══════════
# bot.py این ماژول را در ابتدای کار import می‌کند؛ اینجا build اپلیکیشن را hook می‌کنیم
# تا webapp.setup_bot(app) حتماً اجرا شود (حتی اگر خط آن در bot.py اضافه نشده باشد).
def _install_build_hook():
    try:
        from telegram.ext import ApplicationBuilder
    except Exception:
        return
    if getattr(ApplicationBuilder.build, "_zar_hooked", False):
        return
    original = ApplicationBuilder.build

    def build(self, *args, **kwargs):
        app = original(self, *args, **kwargs)
        try:
            import webapp
            webapp.setup_bot(app)
        except Exception:
            logger.exception("❌ webapp.setup_bot اجرا نشد")
        return app

    build._zar_hooked = True
    ApplicationBuilder.build = build


_install_build_hook()
