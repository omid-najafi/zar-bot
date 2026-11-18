# -*- coding: utf-8 -*-
"""
⚽ پنالتی — نسخه مینی‌اپ (تک‌نفره)
یکی از ۳ گوشه را انتخاب کن؛ اگر دروازه‌بان جای دیگری شیرجه بزند گل است (احتمال ۲/۳، جایزه ×۱٫۴۵)
"""
import random

from games.casino import legacy_notice

rng = random.SystemRandom()
DIRECTIONS = ("left", "center", "right")
GOAL_MULT = 1.45


def miniapp_play(body: dict) -> dict:
    shot = body.get("dir")
    if shot not in DIRECTIONS:
        raise ValueError("جهت شوت را انتخاب کن")
    keeper = rng.choice(DIRECTIONS)
    goal = keeper != shot
    return {"dir": shot, "keeper": keeper, "goal": goal, "won": goal, "mult": GOAL_MULT if goal else 0}


SOLO_INSTANT = {"penalty": miniapp_play}

# ─── سازگاری با کد قدیمی bot.py ───
handle_callback = legacy_notice
start_game = legacy_notice


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return legacy_notice
