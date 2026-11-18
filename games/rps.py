# -*- coding: utf-8 -*-
"""
✊ سنگ کاغذ قیچی — نسخه مینی‌اپ (۳ دست؛ هر کس ۲ دست ببرد)
بازی متنی قدیمی حذف شده و فقط پیام «منتقل شد» نمایش داده می‌شود.
"""
from games.casino import legacy_notice

BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
MAX_ROUNDS = 9


async def miniapp_init(g):
    a, b = g.uids()
    g.data = {"score": {a: 0, b: 0}, "picks": {}, "history": [], "round": 1}
    g.waiting = {a, b}


async def miniapp_action(g, uid, body):
    pick = body.get("pick")
    if pick not in BEATS:
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
    w = a if BEATS[pa] == pb else (b if BEATS[pb] == pa else None)
    if w:
        d["score"][w] += 1
    d["history"].append({"picks": {a: pa, b: pb}, "winner": w})
    d["picks"] = {}
    if max(d["score"].values()) >= 2:
        win = a if d["score"][a] > d["score"][b] else b
        g.finish(win, f"{g.name(win)} دو دست برد")
        return None
    if d["round"] >= MAX_ROUNDS:
        if d["score"][a] == d["score"][b]:
            g.finish(None, "۹ دست تمام شد — مساوی")
        else:
            win = a if d["score"][a] > d["score"][b] else b
            g.finish(win, f"{g.name(win)} با امتیاز بیشتر برد")
        return None
    d["round"] += 1
    g.waiting = {a, b}
    return None


def miniapp_view(g, uid) -> dict:
    d = g.data
    o = g.opp(uid)
    hist = [{"me": h["picks"][uid], "opp": h["picks"][o],
             "result": "draw" if h["winner"] is None else ("win" if h["winner"] == uid else "lose")}
            for h in d["history"]]
    return {"score_me": d["score"][uid], "score_opp": d["score"][o], "my_pick": d["picks"].get(uid),
            "opp_picked": o in d["picks"], "round": d["round"], "history": hist}


MINIAPP_GAMES = {"rps": {"init": miniapp_init, "action": miniapp_action, "view": miniapp_view}}

# ─── سازگاری با کد قدیمی bot.py ───
handle_callback = legacy_notice
create_room = legacy_notice


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return legacy_notice
