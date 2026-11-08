import asyncio
import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

def casino_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 اسلات", callback_data="casino:slots"), InlineKeyboardButton("🎲 تاس", callback_data="casino:dice")],
        [InlineKeyboardButton("🪙 شیر یا خط", callback_data="casino:coin"), InlineKeyboardButton("🃏 کارت شانس", callback_data="casino:card")],
        [InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")],
    ])

def casino_back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🎰 بازگشت به کازینو", callback_data="game:casino")]])

def casino_dice_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("دقیقاً 1 (3x)", callback_data="casino:play:dice:exact:1"), InlineKeyboardButton("دقیقاً 2 (3x)", callback_data="casino:play:dice:exact:2"), InlineKeyboardButton("دقیقاً 3 (3x)", callback_data="casino:play:dice:exact:3")],
        [InlineKeyboardButton("دقیقاً 4 (3x)", callback_data="casino:play:dice:exact:4"), InlineKeyboardButton("دقیقاً 5 (3x)", callback_data="casino:play:dice:exact:5"), InlineKeyboardButton("دقیقاً 6 (3x)", callback_data="casino:play:dice:exact:6")],
        [InlineKeyboardButton("زوج (1.5x)", callback_data="casino:play:dice:parity:even"), InlineKeyboardButton("فرد (1.5x)", callback_data="casino:play:dice:parity:odd")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_coin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦁 شیر", callback_data="casino:play:coin:heads"), InlineKeyboardButton("✖️ خط", callback_data="casino:play:coin:tails")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_card_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♥️ دل", callback_data="casino:play:card:hearts"), InlineKeyboardButton("♦️ خشت", callback_data="casino:play:card:diamonds")],
        [InlineKeyboardButton("♠️ پیک", callback_data="casino:play:card:spades"), InlineKeyboardButton("♣️ گشنیز", callback_data="casino:play:card:clubs")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

async def play_slots(update, user_id, amount):
    reels = [random.choice(config.SLOT_SYMBOLS) for _ in range(3)]
    reels_str = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        mult = 15 if reels[0] == "7️⃣" else (8 if reels[0] == "⭐" else 4)
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        mult = 1.7
    else: mult = 0

    if mult > 0:
        full = int(amount * mult)
        prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
        await db.add_balance(user_id, prize)
        text = f"🎰 <b>اسلات</b>\n━━━━━━━━━━━━━━━━━━\n<b>{reels_str}</b>\n\n🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
    else:
        text = f"🎰 <b>اسلات</b>\n━━━━━━━━━━━━━━━━━━\n<b>{reels_str}</b>\n\n😢 باختی! {utils.fmt(amount)} زرکوین از دست رفت."
    
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=casino_back_kb())
    utils.remember_owner(msg, user_id)

async def handle_callback(query, context, data, user_id):
    if data == "casino:cancel":
        pending = utils.casino_pending.pop(user_id, None)
        if pending:
            await db.add_balance(user_id, pending["entry"])
            await utils.safe_edit(query, f"❌ بازی لغو شد و {utils.fmt(pending['entry'])} زرکوین برگشت.", casino_menu_kb())
        else:
            await utils.safe_edit(query, "❌ بازی فعالی نداشتی.", casino_menu_kb())
        await utils.safe_answer(query)
        return

    if data.count(":") == 1:
        cg = data.split(":")[1]
        if cg in config.CASINO_GAMES:
            g = config.CASINO_GAMES[cg]
            utils.user_states[user_id] = {"action": "casino_entry", "game": cg}
            msg = await utils.safe_edit(query, f"{g['emoji']} <b>{g['name']}</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>{utils.fmt(g['min'])}</b> زرکوین\n💵 کارمزد: <b>10%</b> از جایزه\n\nمبلغ ورودی رو بفرست:", casino_back_kb())
            utils.remember_owner(msg, user_id)
        await utils.safe_answer(query)
        return

    if data.startswith("casino:play:"):
        parts = data.split(":")
        cg = parts[2]
        pending = utils.casino_pending.get(user_id)
        if not pending or pending["game"] != cg:
            await utils.safe_answer(query, "❌ بازی فعالی نداری", show_alert=True); return
        utils.casino_pending.pop(user_id, None)
        entry = pending["entry"]
        
        if cg == "dice":
            try:
                dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
            except Exception:
                await db.add_balance(user_id, entry)
                await utils.safe_edit(query, "❌ خطا در ارتباط با تلگرام. پول شما برگشت داده شد.", casino_back_kb())
                await utils.safe_answer(query)
                return
            await asyncio.sleep(4)
            res = dice_msg.dice.value
            
            header = f"🎲 <b>تاس</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه: <b>{res}</b>\nانتخاب تو: "
            is_win, mult = False, 0
            
            if parts[3] == "exact":
                header += f"دقیقاً {parts[4]}\n\n"
                if res == int(parts[4]): is_win, mult = True, 3.0
            else:
                if parts[4] == "even":
                    header += "زوج\n\n"
                    if res % 2 == 0: is_win, mult = True, 1.5
                else:
                    header += "فرد\n\n"
                    if res % 2 != 0: is_win, mult = True, 1.5
                    
            if is_win:
                full = int(entry * mult)
                prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
                await db.add_balance(user_id, prize)
                text = header + f"🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
            else:
                text = header + f"😢 باختی! {utils.fmt(entry)} زرکوین از دست رفت."
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)
            
        elif cg == "coin":
            res = random.choice(["heads", "tails"])
            header = f"🪙 <b>شیر یا خط</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه: <b>{'شیر 🦁' if res == 'heads' else 'خط ✖️'}</b>\nانتخاب تو: {'شیر 🦁' if parts[3] == 'heads' else 'خط ✖️'}\n\n"
            if res == parts[3]:
                full = entry * 2
                prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
                await db.add_balance(user_id, prize)
                text = header + f"🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
            else:
                text = header + f"😢 باختی! {utils.fmt(entry)} زرکوین از دست رفت."
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)
            
        elif cg == "card":
            res = random.choice(list(config.CARD_SUITS.keys()))
            header = f"🃏 <b>کارت شانس</b>\n━━━━━━━━━━━━━━━━━━\n🎯 کارت: <b>{config.CARD_SUITS[res]}</b> ({config.CARD_SUITS_FA[res]})\nانتخاب تو: {config.CARD_SUITS[parts[3]]} ({config.CARD_SUITS_FA[parts[3]]})\n\n"
            if res == parts[3]:
                full = entry * 4
                prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
                await db.add_balance(user_id, prize)
                text = header + f"🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
            else:
                text = header + f"😢 باختی! {utils.fmt(entry)} زرکوین از دست رفت."
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)
