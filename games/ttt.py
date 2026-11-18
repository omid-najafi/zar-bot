# -*- coding: utf-8 -*-
"""
❌ بازی‌های صفحه‌ای مینی‌اپ: دوز (۳×۳) و چهار در یک ردیف (۶×۷)
بازی متنی قدیمی حذف شده و فقط پیام «منتقل شد» نمایش داده می‌شود.
"""
from games.casino import legacy_notice


def _int(v, default=-1):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ═══════════ دوز ═══════════
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


async def ttt_init(g):
    a, b = g.uids()
    g.data = {"board": [0] * 9, "marks": {a: 1, b: 2}, "line": None}
    g.waiting = {a}


async def ttt_action(g, uid, body):
    if uid not in g.waiting:
        return "نوبت تو نیست"
    i = _int(body.get("cell"))
    board = g.data["board"]
    if not 0 <= i < 9 or board[i]:
        return "این خانه قابل انتخاب نیست"
    mark = g.data["marks"][uid]
    board[i] = mark
    for line in LINES:
        if all(board[x] == mark for x in line):
            g.data["line"] = list(line)
            g.finish(uid, f"{g.name(uid)} سه‌تا در یک خط چید")
            return None
    if all(board):
        g.finish(None, "صفحه پر شد — مساوی")
        return None
    g.waiting = {g.opp(uid)}
    return None


def ttt_view(g, uid) -> dict:
    return {"board": g.data["board"], "my_mark": g.data["marks"][uid], "line": g.data["line"]}


# ═══════════ چهار در یک ردیف ═══════════
ROWS, COLS = 6, 7


async def c4_init(g):
    a, b = g.uids()
    g.data = {"board": [0] * (ROWS * COLS), "discs": {a: 1, b: 2}, "line": None, "last": None}
    g.waiting = {a}


def _c4_line(board, r, c, d):
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        cells = [(r, c)]
        for sign in (1, -1):
            rr, cc = r + dr * sign, c + dc * sign
            while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr * COLS + cc] == d:
                cells.append((rr, cc))
                rr += dr * sign
                cc += dc * sign
        if len(cells) >= 4:
            return [x * COLS + y for x, y in cells]
    return None


async def c4_action(g, uid, body):
    if uid not in g.waiting:
        return "نوبت تو نیست"
    c = _int(body.get("col"))
    if not 0 <= c < COLS:
        return "ستون نامعتبر است"
    board = g.data["board"]
    d = g.data["discs"][uid]
    for r in range(ROWS - 1, -1, -1):
        if board[r * COLS + c] == 0:
            board[r * COLS + c] = d
            g.data["last"] = r * COLS + c
            line = _c4_line(board, r, c, d)
            if line:
                g.data["line"] = line
                g.finish(uid, f"{g.name(uid)} چهار مهره پشت‌سرهم چید")
            elif all(board):
                g.finish(None, "صفحه پر شد — مساوی")
            else:
                g.waiting = {g.opp(uid)}
            return None
    return "این ستون پر است"


def c4_view(g, uid) -> dict:
    return {"board": g.data["board"], "my_disc": g.data["discs"][uid], "line": g.data["line"],
            "last": g.data["last"], "rows": ROWS, "cols": COLS}


MINIAPP_GAMES = {
    "ttt": {"init": ttt_init, "action": ttt_action, "view": ttt_view},
    "connect4": {"init": c4_init, "action": c4_action, "view": c4_view},
}

# ─── سازگاری با کد قدیمی bot.py ───
handle_callback = legacy_notice
create_room = legacy_notice


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return legacy_notice
