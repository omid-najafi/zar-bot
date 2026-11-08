# -*- coding: utf-8 -*-
import logging
import random
from datetime import datetime
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import config
import utils
import db

logger = logging.getLogger("zarcoin")


# ═══════════ داستان‌های خلاقانه هر خانم ═══════════
GIRL_STORIES = {
    "fox": {
        "intro": "🦊 <b>{user}</b> با <b>خانم روباه</b> رفت داخل اتاق VIP... 🚪💋",
        "lose": "وای وای وای! 😒\nیهو خانم روباه گفت: «ببخشید، یادم اومد ظرفا رو نشستم!» و از پنجره پرید بیرون! 🪟😂\n\n🔙 فقط <b>{back}</b> از {paid} برگشت\n📉 ضرر: <b>{loss}</b>",
        "win": "دمت گرم رفیق! 😍\nخانم روباه گفت: «ای بابا، تو دیگه کی هستی!» و یه مشت زرکوین ریخت کف دستت! 💸\n\n📈 سود خالص: <b>{profit}</b>",
        "baby": "بابا ایول! 😱\nخانم روباه با چشمای گرد گفت: «عزیزم... یه روباه کوچولو تو راهه!» 🍼🦊\n\n💰 جایزه کل: {gross}\n💸 هزینه سیسمونی: {baby_cost}\n✅ دریافتی: <b>{received}</b>\n📈 سود خالص: <b>{profit}</b>\n✨ +{xp} XP"
    },
    "angela": {
        "intro": "👱‍♀️ <b>{user}</b> با <b>خانم آنجلا</b> رفت داخل اتاق مخصوص... 🚪🔥",
        "lose": "دلت پاره شد! 😒\nخانم آنجلا یهو گفت: «آخه تو به من نمی‌خوری!» و با ابهت رفت! 🏃‍♀️\n\n🔙 فقط <b>{back}</b> از {paid} برگشت\n📉 ضرر: <b>{loss}</b>",
        "win": "ای جانم! 😍\nخانم آنجلا گفت: «تو بهترین مرد دنیایی!» و <b>{received}</b> بهت داد! 💸\n\n📈 سود خالص: <b>{profit}</b>",
        "baby": "لعنتی چیکار کردی! 😱\nخانم آنجلا گفت: «فکر کنم... حامله شدم!» 🍼👶\n\n💰 جایزه کل: {gross}\n💸 هزینه سیسمونی: {baby_cost}\n✅ دریافتی: <b>{received}</b>\n📈 سود خالص: <b>{profit}</b>\n✨ +{xp} XP"
    },
    "lana": {
        "intro": "👩 <b>{user}</b> با <b>خانم لانا</b> رفت داخل اتاق لاکچری... 🚪✨",
        "lose": "پوکیدی! 😒\nخانم لانا گفت: «ببخشید، یادم رفت گوشیم رو شارژ کنم!» و رفت! 📱😅\n\n🔙 فقط <b>{back}</b> از {paid} برگشت\n📉 ضرر: <b>{loss}</b>",
        "win": "عشقی! 😍\nخانم لانا گفت: «تو یه جنتلمن واقعی هستی!» و <b>{received}</b> بهت داد! 💸\n\n📈 سود خالص: <b>{profit}</b>",
        "baby": "خدا رحم کرد! 😱\nخانم لانا گفت: «فکر کنم یه بچه تو راهه!» 🍼\n\n💰 جایزه کل: {gross}\n💸 هزینه سیسمونی: {baby_cost}\n✅ دریافتی: <b>{received}</b>\n📈 سود خالص: <b>{profit}</b>\n✨ +{xp} XP"
    },
    "alexis": {
        "intro": "👩‍🦰 <b>{user}</b> با <b>خانم الکسیس</b> رفت داخل سوئیت ویژه... 🚪💎",
        "lose": "ای بابا! 😒\nخانم الکسیس گفت: «ببخشید، باید برم مانیکورم!» و رفت! 💅😂\n\n🔙 فقط <b>{back}</b> از {paid} برگشت\n📉 ضرر: <b>{loss}</b>",
        "win": "ای ول! 😍\nخانم الکسیس گفت: «تو دیوونه‌ام کردی!» و <b>{received}</b> بهت داد! 💸\n\n📈 سود خالص: <b>{profit}</b>",
        "baby": "یوهو! 😱\nخانم الکسیس گفت: «عزیزم، دوقلو باردارم!» 🍼🍼\n\n💰 جایزه کل: {gross}\n💸 هزینه سیسمونی: {baby_cost}\n✅ دریافتی: <b>{received}</b>\n📈 سود خالص: <b>{profit}</b>\n✨ +{xp} XP"
    },
    "eden": {
        "intro": "👸 <b>{user}</b> با <b>خانم اِدِن</b> رفت داخل اتاق پادشاهی... 🚪👑",
        "lose": "نچ! 😒\nخانم اِدِن گفت: «تو لیاقت من رو نداری!» و با ابهت رفت! 🚶‍♀️😤\n\n🔙 فقط <b>{back}</b> از {paid} برگشت\n📉 ضرر: <b>{loss}</b>",
        "win": "شاهزاده شدی! 😍\nخانم اِدِن گفت: «تو شایسته یه پادشاهی!» و <b>{received}</b> بهت داد! 💸\n\n📈 سود خالص: <b>{profit}</b>",
        "baby": "ملکه باردار شد! 😱\nخانم اِدِن گفت: «یه ولیعهد تو راهه!» 🍼👶👑\n\n💰 جایزه کل: {gross}\n💸 هزینه سیسمونی: {baby_cost}\n✅ دریافتی: <b>{received}</b>\n📈 سود خالص: <b>{profit}</b>\n✨ +{xp} XP"
    }
}


def _check_cooldown(user):
    """برگرداندن (is_on_cooldown, remaining_text)"""
    if not user: return False, None
    last = user.get("last_kabareh")
    if not last: return False, None
    try:
        last_dt = datetime.fromisoformat(last)
        elapsed = (datetime.now(utils.TEHRAN) - last_dt).total_seconds()
        cooldown = config.KABAREH_COOLDOWN_HOURS * 3600
        if elapsed < cooldown:
            remaining = int(cooldown - elapsed)
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            secs = remaining % 60
            if hours > 0:
                txt = f"{hours} ساعت و {mins} دقیقه"
            elif mins > 0:
                txt = f"{mins} دقیقه و {secs} ثانیه"
            else:
                txt = f"{secs} ثانیه"
            return True, txt
    except Exception:
        pass
    return False, None


def _menu_kb(is_unlocked: bool):
    if not is_unlocked:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 باز کردن کاباره (25M)", callback_data="kabareh:unlock")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦊 روباه (2M)", callback_data="kabareh:select:fox")],
        [InlineKeyboardButton("👱‍♀️ آنجلا (3M)", callback_data="kabareh:select:angela")],
        [InlineKeyboardButton("👩 لانا (4M)", callback_data="kabareh:select:lana")],
        [InlineKeyboardButton("👩‍🦰 الکسیس (5M)", callback_data="kabareh:select:alexis")],
        [InlineKeyboardButton("👸 اِدِن (6M)", callback_data="kabareh:select:eden")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]
    ])


def _confirm_kb(girl_key: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بریم حال کنیم!", callback_data=f"kabareh:play:{girl_key}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="kabareh:menu")]
    ])


def _menu_text(user) -> str:
    is_unlocked = bool(user.get("kabareh_unlocked", 0)) if user else False
    
    if not is_unlocked:
        return (
            "🎭 <b>کاباره زر</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💰 هزینه باز کردن: <b>{utils.fmt(config.KABAREH_UNLOCK_COST)}</b>\n\n"
            "🦊 روباه (2M) | 👱‍♀️ آنجلا (3M) | 👩 لانا (4M)\n"
            "👩‍🦰 الکسیس (5M) | 👸 اِدِن (6M)\n\n"
            "🎲 شانس‌ها:\n"
            "• 60% باخت (نصف پول برمی‌گرده)\n"
            "• 30% برد (دو برابر پول برمی‌گرده)\n"
            "• 10% بچه‌دار (سه برابر منهای 1M + 2000 XP)\n\n"
            "برای باز کردن کلیک کن 👇"
        )
    
    base = "🎭 <b>کاباره زر</b>\n━━━━━━━━━━━━━━━━━━\n"
    
    on_cd, txt = _check_cooldown(user)
    if on_cd:
        base += f"⏳ <b>صبر کن عزیزم!</b>\n"
        base += f"تا کاباره بعدی: <b>{txt}</b>\n\n"
    else:
        base += "با کی می‌خوای حال کنی؟ 😏\n\n"
    
    base += "🎲 شانس‌ها:\n"
    base += "60% باخت | 30% برد | 10% بچه‌دار"
    return base


def _confirm_text(girl_key: str) -> str:
    girl = config.KABAREH_GIRLS[girl_key]
    return (
        f"🎭 <b>تایید</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👩 همراه: {girl['emoji']} <b>{girl['name']}</b>\n"
        f"💰 هزینه: <b>{utils.fmt(girl['price'])}</b>\n\n"
        f"⚠️ <b>شانس‌ها:</b>\n"
        f"• 60% باخت (نصف پول برمی‌گرده)\n"
        f"• 30% برد (دو برابر پول برمی‌گرده)\n"
        f"• 10% بچه‌دار (سه برابر منهای 1M + 2000 XP)\n\n"
        f"⏰ <i>بعد از این بازی، 24 ساعت باید صبر کنی!</i>\n\n"
        f"مطمئنی؟ 😏"
    )


async def handle_callback(query, context, data, user_id):
    try:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        logger.info(f"🎭 Kabareh: {action} for {user_id}")

        # ─────────── منو ───────────
        if action == "menu":
            user = await db.get_user(user_id)
            msg = await utils.safe_edit(query, _menu_text(user), _menu_kb(bool(user.get("kabareh_unlocked", 0)) if user else False))
            if msg: utils.remember_owner(msg, user_id)
            await utils.safe_answer(query); return

        # ─────────── باز کردن ───────────
        if action == "unlock":
            user = await db.get_user(user_id)
            if not user:
                await utils.safe_answer(query, "❌ خطا", show_alert=True); return
            if user.get("kabareh_unlocked"):
                await utils.safe_answer(query, "✅ قبلاً باز شده!", show_alert=True); return
            if int(user["balance"]) < config.KABAREH_UNLOCK_COST:
                await utils.safe_answer(query, f"❌ نیاز: {utils.fmt(config.KABAREH_UNLOCK_COST)}\nموجودی: {utils.fmt(int(user['balance']))}", show_alert=True); return
            ok = await db.unlock_kabareh(user_id)
            if ok:
                user = await db.get_user(user_id)
                await utils.safe_answer(query, "🎉 کاباره باز شد! حالا می‌تونی بری حال کنی!", show_alert=True)
                msg = await utils.safe_edit(query, _menu_text(user), _menu_kb(True))
                if msg: utils.remember_owner(msg, user_id)
            else:
                await utils.safe_answer(query, "❌ خطا", show_alert=True)
            return

        # ─────────── انتخاب خانم ───────────
        if action == "select":
            girl_key = parts[2] if len(parts) > 2 else ""
            if girl_key not in config.KABAREH_GIRLS:
                await utils.safe_answer(query, "❌ نامعتبر", show_alert=True); return
            
            user = await db.get_user(user_id)
            
            # چک کول‌داون
            on_cd, txt = _check_cooldown(user)
            if on_cd:
                await utils.safe_answer(query, f"⏳ صبر کن!\n\nتا کاباره بعدی: <b>{txt}</b>", show_alert=True); return
            
            msg = await utils.safe_edit(query, _confirm_text(girl_key), _confirm_kb(girl_key))
            if msg: utils.remember_owner(msg, user_id)
            await utils.safe_answer(query); return

        # ─────────── بازی! ───────────
        if action == "play":
            girl_key = parts[2] if len(parts) > 2 else ""
            girl = config.KABAREH_GIRLS.get(girl_key)
            if not girl:
                await utils.safe_answer(query, "❌ نامعتبر", show_alert=True); return

            user = await db.get_user(user_id)
            if not user:
                await utils.safe_answer(query, "❌ خطا", show_alert=True); return
            
            # چک کول‌داون
            on_cd, txt = _check_cooldown(user)
            if on_cd:
                await utils.safe_answer(query, f"⏳ صبر کن عزیزم!\n\nتا کاباره بعدی: <b>{txt}</b>", show_alert=True); return
            
            price = girl["price"]
            if int(user["balance"]) < price:
                await utils.safe_answer(query, f"❌ نیاز: {utils.fmt(price)}\nموجودی: {utils.fmt(int(user['balance']))}", show_alert=True); return

            if not await db.deduct_balance(user_id, price):
                await utils.safe_answer(query, "❌ موجودی!", show_alert=True); return

            # ثبت کول‌داون
            await db.set_last_kabareh(user_id, datetime.now(utils.TEHRAN).isoformat())

            roll = random.random()
            baby = False
            story = GIRL_STORIES[girl_key]
            user_name = utils.escape(query.from_user.first_name)

            if roll < 0.60:
                # باخت 60%
                back = int(price * 0.5)
                await db.add_balance(user_id, back)
                body = story["lose"].format(
                    back=utils.fmt(back),
                    paid=utils.fmt(price),
                    loss=utils.fmt(price - back))
            elif roll < 0.90:
                # برد 30%
                received = price * 2
                await db.add_balance(user_id, received)
                body = story["win"].format(
                    received=utils.fmt(received),
                    profit=utils.fmt(received - price))
            else:
                # بچه‌دار 10%
                baby = True
                gross = price * 3
                received = gross - config.KABAREH_BABY_COST
                await db.add_balance(user_id, received)
                body = story["baby"].format(
                    gross=utils.fmt(gross),
                    baby_cost=utils.fmt(config.KABAREH_BABY_COST),
                    received=utils.fmt(received),
                    profit=utils.fmt(received - price),
                    xp=config.KABAREH_BABY_XP)

            text = (
                f"{story['intro'].format(user=user_name)}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"{body}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏰ <i>دفعه بعدی: {config.KABAREH_COOLDOWN_HOURS} ساعت دیگه</i>"
            )

            msg = await utils.safe_edit(query, text, _menu_kb(True))
            if msg: utils.remember_owner(msg, user_id)
            await utils.safe_answer(query)

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
                    except Exception: pass
            return

        await utils.safe_answer(query)
    except Exception as e:
        logger.exception(f"🎭 Kabareh error: {e}")
        try: await utils.safe_answer(query, f"❌ {str(e)[:60]}", show_alert=True)
        except Exception: pass
