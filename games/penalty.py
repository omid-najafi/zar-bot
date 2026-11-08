import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

def kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚽ شوت!", callback_data="pen:shoot")]])

async def start_game(update, amount):
    user_id = update.effective_user.id
    utils.penalty_games[user_id] = {"entry": amount, "chat_id": update.effective_chat.id}
    msg = await update.message.reply_text(f"⚽ <b>پنالتی</b>\n💰 ورودی: {utils.fmt(amount)}\n\nآماده‌ای؟ شوت کن!", parse_mode=ParseMode.HTML, reply_markup=kb())
    utils.remember_owner(msg, user_id)

async def handle_callback(query, context, data, user_id):
    if data != "pen:shoot": return
    game = utils.penalty_games.pop(user_id, None)
    if not game:
        await query.answer("❌ بازی فعالی نداری", show_alert=True); return
        
    if random.random() < 0.5:
        full = game["entry"] * 2
        prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
        await db.add_balance(user_id, prize)
        text = f"⚽ <b>گل!!!</b> 🎉\n\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
    else:
        text = f"⚽ <b>دروازه‌بان گرفت!</b> 😢\n\n💸 متأسفانه {utils.fmt(game['entry'])} زرکوین از دست رفت."
        
    await utils.safe_edit(query, text, utils.back_games_kb())
    await query.answer()
