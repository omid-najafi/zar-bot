# -*- coding: utf-8 -*-
"""ماژول کاباره زر — تمام منطق و UI در همین فایل"""
import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import config
import utils
import db


def menu_kb(is_unlocked: bool):
    """کیبورد منوی کاباره — قبل و بعد از باز شدن"""
    if not is_unlocked:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"🔓 باز کردن کاباره ({utils.fmt(config.KABAREH_UNLOCK_COST)} زرکوین)",
                callback_data="kabareh:unlock"
            )],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦊 خانم روباه (2M)", callback_data="kabareh:select:fox")],
        [InlineKeyboardButton("👱‍♀️ خانم آنجلا (3M)", callback_data="kabareh:select:angela")],
        [InlineKeyboardButton("👩 خانم لانا (4M)", callback_data="kabareh:select:lana")],
        [InlineKeyboardButton("👩‍🦰 خانم الکسیس (5M)", callback_data="kabareh:select:alexis")],
        [InlineKeyboardButton("👸 خانم اِدِن (6M)", callback_data="kabareh:select:eden")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]
    ])


def confirm_kb(girl_key: str):
    """کیبورد تایید قبل از بازی"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بریم حال کنیم!", callback_data=f"kabareh:play:{girl_key}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="kabareh:menu")]
    ])


def build_menu_text(is_unlocked: bool) -> str:
    if not is_unlocked:
        return (
            "🎭 <b>کاباره زر</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💰 هزینه باز کردن: <b>{utils.fmt(config.KABAREH_UNLOCK_COST)}</b> زرکوین\n\n"
            "پس از باز کردن می‌تونی با خانم‌های کاباره حال کنی:\n"
            "🦊 روباه (2M) | 👱‍♀️ آنجلا (3M) | 👩 لانا (4M)\n"
            "👩‍🦰 الکسیس (5M) | 👸 اِدِن (6M)\n\n"
            "🎲 شانس‌ها:\n"
            "• 60% باخت (نصف پول برمی‌گرده)\n"
            "• 30% برد (دو برابر پول برمی‌گرده)\n"
            "• 10% بچه‌دار (سه برابر منهای 1M + 2000 XP)\n\n"
            "برای باز کردن کلیک کن 👇"
        )
    return (
        "🎭 <b>کاباره زر</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "با کی می‌خوای حال کنی؟ 😏\n\n"
        "🎲 شانس‌ها:\n"
        "• 60% باخت | • 30% برد | • 10% بچه‌دار (+2000 XP)"
    )


def build_confirm_text(girl_key: str) -> str:
    girl = config.KABAREH_GIRLS[girl_key]
    return (
        f"🎭 <b>تایید</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👩 همراه: {girl['emoji']} <b>{girl['name']}</b>\n"
        f"💰 هزینه: <b>{utils.fmt(girl['price'])}</b> زرکوین\n\n"
        f"⚠️ <b>شانس‌ها:</b>\n"
        f"• 60% باخت (نصف پول برمی‌گرده)\n"
        f"• 30% برد (دو برابر پول برمی‌گرده)\n"
        f"• 10% بچه‌دار (سه برابر منهای 1M + 2000 XP)\n\n"
        f"مطمئنی؟ 😏"
    )


async def handle_callback(query, context, data, user_id):
    """روتر اصلی کاباره — همه دکمه‌های kabareh:* به اینجا می‌رسن"""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # ─────────── منوی اصلی کاباره ───────────
    if action == "menu":
        user = await db.get_user(user_id)
        unlocked = bool(user.get("kabareh_unlocked", 0)) if user else False
        msg = await utils.safe_edit(query, build_menu_text(unlocked), menu_kb(unlocked))
        utils.remember_owner(msg, user_id)
        await utils.safe_answer(query)
        return

    # ─────────── باز کردن کاباره ───────────
    if action == "unlock":
        user = await db.get_user(user_id)
        if not user:
            await utils.safe_answer(query, "❌ خطا در دریافت اطلاعات", show_alert=True); return
        if user.get("kabareh_unlocked"):
            await utils.safe_answer(query, "✅ کاباره قبلاً باز شده!", show_alert=True); return
        if int(user["balance"]) < config.KABAREH_UNLOCK_COST:
            await utils.safe_answer(
                query,
                f"❌ موجودی کافی نیست!\nنیاز: {utils.fmt(config.KABAREH_UNLOCK_COST)}",
                show_alert=True)
            return

        ok = await db.unlock_kabareh(user_id)
        if ok:
            await utils.safe_answer(query, "🎉 کاباره با موفقیت باز شد!", show_alert=True)
            msg = await utils.safe_edit(query, build_menu_text(True), menu_kb(True))
            utils.remember_owner(msg, user_id)
        else:
            await utils.safe_answer(query, "❌ خطا در باز کردن کاباره!", show_alert=True)
        return

    # ─────────── انتخاب خانم ───────────
    if action == "select":
        girl_key = parts[2] if len(parts) > 2 else ""
        if girl_key not in config.KABAREH_GIRLS:
            await utils.safe_answer(query, "❌ نامعتبر", show_alert=True); return
        msg = await utils.safe_edit(query, build_confirm_text(girl_key), confirm_kb(girl_key))
        utils.remember_owner(msg, user_id)
        await utils.safe_answer(query)
        return

    # ─────────── بازی! ───────────
    if action == "play":
        girl_key = parts[2] if len(parts) > 2 else ""
        girl = config.KABAREH_GIRLS.get(girl_key)
        if not girl:
            await utils.safe_answer(query, "❌ نامعتبر", show_alert=True); return

        user = await db.get_user(user_id)
        if not user:
            await utils.safe_answer(query, "❌ خطا", show_alert=True); return

        price = girl["price"]
        if int(user["balance"]) < price:
            await utils.safe_answer(
                query, f"❌ موجودی کافی نیست!\nنیاز: {utils.fmt(price)}", show_alert=True)
            return

        # کسر اولیه
        if not await db.deduct_balance(user_id, price):
            await utils.safe_answer(query, "❌ موجودی کافی نیست!", show_alert=True); return

        roll = random.random()
        baby = False

        if roll < 0.60:
            # 60% — خوشش نیومد (نصف برمی‌گرده)
            reward = int(price * 0.5)
            await db.add_balance(user_id, reward)
            text = (
                f"😒 <b>خوشش نیومد!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👩 {girl['emoji']} <b>{girl['name']}</b> ازت خوشش نیومد...\n\n"
                f"💰 پرداختی: {utils.fmt(price)}\n"
                f"🔙 برگشتی: <b>{utils.fmt(reward)}</b>\n"
                f"📉 ضرر: <b>{utils.fmt(price - reward)}</b>"
            )
        elif roll < 0.90:
            # 30% — خوشش اومد (دو برابر)
            reward = price * 2
            await db.add_balance(user_id, reward)
            text = (
                f"😍 <b>خوشش اومد!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👩 {girl['emoji']} <b>{girl['name']}</b> خیلی ازت خوشش اومد!\n\n"
                f"💰 دریافتی: <b>{utils.fmt(reward)}</b> زرکوین\n"
                f"📈 سود: <b>{utils.fmt(reward - price)}</b>"
            )
        else:
            # 10% — بچه‌دار
            baby = True
            gross = price * 3
            reward = gross - config.KABAREH_BABY_COST
            await db.add_balance(user_id, reward)
            text = (
                f"👶 <b>بچه‌دار شدید!</b> 🎉\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👩 {girl['emoji']} <b>{girl['name']}</b> حامله شد!\n\n"
                f"💰 جایزه کل: {utils.fmt(gross)}\n"
                f"💸 هزینه وسایل بچه: <b>{utils.fmt(config.KABAREH_BABY_COST)}</b>\n"
                f"✅ دریافتی: <b>{utils.fmt(reward)}</b>\n"
                f"📈 سود خالص: <b>{utils.fmt(reward - price)}</b>\n\n"
                f"✨ <b>+{config.KABAREH_BABY_XP} XP</b>"
            )

        msg = await utils.safe_edit(query, text, menu_kb(True))
        utils.remember_owner(msg, user_id)
        await utils.safe_answer(query)

        # XP برای بچه‌دار
        if baby:
            new_xp, new_level, leveled_up = await db.add_xp(user_id, config.KABAREH_BABY_XP)
            if leveled_up:
                try:
                    await context.bot.send_message(
                        query.message.chat_id,
                        f"🎉 <b>لول آپ!</b>\n\n"
                        f"به لول <b>{new_level}</b> رسیدی! 🌟\n"
                        f"✨ XP فعلی: <b>{utils.fmt(new_xp)}</b>",
                        parse_mode=ParseMode.HTML)
                except Exception:
                    pass
        return

    # fallback
    await utils.safe_answer(query)
