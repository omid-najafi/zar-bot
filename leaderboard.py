# -*- coding: utf-8 -*-
"""🏆 لیدربورد ربات زرکوین"""
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db

logger = logging.getLogger("zarcoin")

MEDALS = ["🥇", "🥈", "🥉"]


async def build_leaderboard_text(user_id: int) -> str:
    """ساخت متن لیدربورد + رتبه کاربر"""
    top_users, user_rank = await db.get_leaderboard(limit=15, around_user_id=user_id)

    lines = ["🏆 <b>لیدربورد زرکوین</b>", "━━━━━━━━━━━━━━━━━━", ""]

    if not top_users:
        lines.append("📭 هنوز کاربری ثبت نشده.")
        return "\n".join(lines)

    for i, u in enumerate(top_users, 1):
        try:
            medal = MEDALS[i - 1] if i <= 3 else f"{i}."
            name = utils.escape(u.get("first_name") or "بی‌نام")
            total = int(u.get("total_wealth") or 0)
            lines.append(f"{medal} {name}")
            lines.append(f"    💰 {utils.fmt(total)} زرکوین")
            lines.append("")
        except Exception as e:
            logger.warning(f"⚠️ خطا در پردازش ردیف {i}: {e}")
            continue

    # رتبه کاربر
    try:
        user = await db.get_user(user_id)
    except Exception as e:
        logger.warning(f"⚠️ get_user در لیدربورد: {e}")
        user = None

    if user:
        try:
            user_total = int(user.get("balance") or 0) + int(user.get("bank_balance") or 0)
        except (TypeError, ValueError):
            user_total = 0
        if user_rank:
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"📊 <b>رتبه شما: {user_rank}</b>")
            lines.append(f"💰 <b>ثروت شما: {utils.fmt(user_total)}</b> زرکوین")
        else:
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"📊 ثروت شما: <b>{utils.fmt(user_total)}</b> زرکوین")
    else:
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("ℹ️ برای دیدن رتبه خودتان، ابتدا /start را بفرستید.")

    return "\n".join(lines)


def leaderboard_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄refresh", callback_data="lb:refresh")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])


async def handle_callback(query, context, data, user_id):
    try:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else "menu"

        if action in ("menu", "refresh"):
            await db.ensure_user(query.from_user)
            text = await build_leaderboard_text(user_id)
            msg = await utils.safe_edit(query, text, leaderboard_kb())
            if msg:
                utils.remember_owner(msg, user_id)
            await utils.safe_answer(query)
            return

        await utils.safe_answer(query)
    except Exception as e:
        logger.exception(f"Leaderboard error: {e}")
        try:
            await utils.safe_answer(query, "❌ خطا", show_alert=True)
        except Exception:
            pass
