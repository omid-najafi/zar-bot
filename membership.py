# -*- coding: utf-8 -*-
"""سیستم جوین اجباری — بررسی عضویت در کانال‌ها و گروه"""
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import config
import db

logger = logging.getLogger("zarcoin")


def get_join_keyboard():
    """کیبورد دکمه‌های عضویت در کانال‌ها و گروه"""
    buttons = []
    for ch in config.REQUIRED_CHANNELS:
        buttons.append([InlineKeyboardButton(f"📢 {ch['name']}", url=ch["url"])])
    if config.REQUIRED_GROUP:
        buttons.append([InlineKeyboardButton(f"💬 {config.REQUIRED_GROUP['name']}", url=config.REQUIRED_GROUP["url"])])
    buttons.append([InlineKeyboardButton("✅ عضو شدم، بررسی کن!", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)


def get_join_text() -> str:
    """متن پیام جوین اجباری"""
    text = (
        "🔒 <b>برای استفاده از ربات، ابتدا باید عضو کانال‌ها و گروه زیر بشی:</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    for ch in config.REQUIRED_CHANNELS:
        text += f"📢 {ch['name']}\n"
    if config.REQUIRED_GROUP:
        text += f"💬 {config.REQUIRED_GROUP['name']}\n"
    text += "\n👇 روی دکمه‌های زیر بزن و عضو شو، بعد دکمه «✅ عضو شدم» رو بزن:"
    return text


async def check_membership(bot, user_id: int) -> tuple[bool, list]:
    """
    بررسی عضویت کاربر در همه کانال‌ها و گروه.
    خروجی: (is_fully_joined, list_of_missing_names)
    """
    missing = []
    
    # بررسی کانال‌ها
    for ch in config.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch["name"])
        except BadRequest as e:
            logger.warning(f"❌ خطا در بررسی کانال {ch['name']}: {e}")
            # اگر ربات ادمین نباشد یا کانال پیدا نشود، عضو در نظر گرفته نمی‌شود
            missing.append(ch["name"])
        except Exception as e:
            logger.exception(f"❌ خطای غیرمنتظره در بررسی کانال {ch['name']}: {e}")
            missing.append(ch["name"])
    
    # بررسی گروه
    if config.REQUIRED_GROUP:
        try:
            member = await bot.get_chat_member(chat_id=config.REQUIRED_GROUP["id"], user_id=user_id)
            if member.status in ("left", "kicked"):
                missing.append(config.REQUIRED_GROUP["name"])
        except BadRequest as e:
            logger.warning(f"❌ خطا در بررسی گروه {config.REQUIRED_GROUP['name']}: {e}")
            missing.append(config.REQUIRED_GROUP["name"])
        except Exception as e:
            logger.exception(f"❌ خطای غیرمنتظره در بررسی گروه {config.REQUIRED_GROUP['name']}: {e}")
            missing.append(config.REQUIRED_GROUP["name"])
    
    return len(missing) == 0, missing


async def send_join_message(update, context):
    """ارسال پیام جوین اجباری با دکمه‌ها"""
    text = get_join_text()
    kb = get_join_keyboard()
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def verify_and_continue(update, context, callback_data: str = None):
    """
    بررسی عضویت و ادامه عملیات.
    خروجی: True اگر کاربر عضو باشد (ادامه بده)، False اگر عضو نباشد (پیام جوین فرستاده شد).
    """
    user_id = update.effective_user.id
    bot = context.bot
    
    is_joined, missing = await check_membership(bot, user_id)
    
    if is_joined:
        return True
    
    # اگر عضو نبود، پیام جوین اجباری بفرست
    text = (
        "❌ <b>هنوز عضو کانال‌ها و گروه نشدی!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"لطفاً عضو این‌ها شو:\n"
        + "\n".join(f"• {name}" for name in missing) +
        "\n\nبعد دوباره دکمه «✅ عضو شدم» رو بزن."
    )
    
    kb = get_join_keyboard()
    
    if update.callback_query:
        await update.callback_query.answer("❌ هنوز عضو نشدی!", show_alert=True)
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    
    return False
