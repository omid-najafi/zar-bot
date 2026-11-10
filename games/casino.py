import asyncio
import random
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

logger = logging.getLogger("zarcoin")
DICE_FACES = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}

def casino_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 اسلات", callback_data="casino:slots"), InlineKeyboardButton("🎲 تاس", callback_data="casino:dice")],
        [InlineKeyboardButton("🪙 شیر یا خط", callback_data="casino:coin"), InlineKeyboardButton("🃏 کارت شانس", callback_data="casino:card")],
        [InlineKeyboardButton("🎡 رولت", callback_data="casino:roulette"), InlineKeyboardButton("💣 مین‌یاب", callback_data="casino:mines")],
        [InlineKeyboardButton("🎯 چرخ شانس", callback_data="casino:wheel")],
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

def casino_roulette_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("قرمز (2x)", callback_data="casino:play:roulette:red"), InlineKeyboardButton("مشکی (2x)", callback_data="casino:play:roulette:black")],
        [InlineKeyboardButton("صفر (36x)", callback_data="casino:play:roulette:green")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_mines_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚪 در ۱", callback_data="casino:play:mines:1"), InlineKeyboardButton("🚪 در ۲", callback_data="casino:play:mines:2"), InlineKeyboardButton("🚪 در ۳", callback_data="casino:play:mines:3")],
        [InlineKeyboardButton("🚪 در ۴", callback_data="casino:play:mines:4"), InlineKeyboardButton("🚪 در ۵", callback_data="casino:play:mines:5")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_wheel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data="casino:play:wheel:1"), InlineKeyboardButton("2️⃣", callback_data="casino:play:wheel:2"), InlineKeyboardButton("3️⃣", callback_data="casino:play:wheel:3")],
        [InlineKeyboardButton("4️⃣", callback_data="casino:play:wheel:4"), InlineKeyboardButton("5️⃣", callback_data="casino:play:wheel:5"), InlineKeyboardButton("6️⃣", callback_data="casino:play:wheel:6")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

async def _record_casino_missions(context, chat_id, user_id, is_win: bool):
    """ثبت ماموریت‌های کازینو"""
    r_p = await db.progress_mission(user_id, "play_casino", 1, base_xp=config.BASE_XP_PLAY_GAME)
    await utils.notify_mission(context, chat_id, r_p)
    r_any = await db.progress_mission(user_id, "play_any_game", 1, base_xp=0)
    await utils.notify_mission(context, chat_id, r_any)
    if is_win:
        r_win = await db.progress_mission(user_id, "win_casino", 1, base_xp=config.BASE_XP_WIN_GAME)
        await utils.notify_mission(context, chat_id, r_win)
        r_any_win = await db.progress_mission(user_id, "win_any_game", 1, base_xp=0)
        await utils.notify_mission(context, chat_id, r_any_win)

async def play_slots(update, user_id, amount, context):
    reels = [random.choice(config.SLOT_SYMBOLS) for _ in range(3)]
    reels_str = " | ".join(reels)
    is_win = False
    if reels[0] == reels[1] == reels[2]:
        mult = 15 if reels[0] == "7️⃣" else (8 if reels[0] == "⭐" else 4)
        is_win = True
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        mult = 1.7
        is_win = True
    else:
        mult = 0

    if is_win:
        full = int(amount * mult)
        prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
        await db.add_balance(user_id, prize)
        text = f"🎰 <b>اسلات</b>\n━━━━━━━━━━━━━━━━━━\n<b>{reels_str}</b>\n\n🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
    else:
        text = f"🎰 <b>اسلات</b>\n━━━━━━━━━━━━━━━━━━\n<b>{reels_str}</b>\n\n😢 باختی! {utils.fmt(amount)} زرکوین از دست رفت."

    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=casino_back_kb())
    utils.remember_owner(msg, user_id)

    # ✅ ثبت ماموریت‌ها
    await _record_casino_missions(context, update.message.chat_id, user_id, is_win)


def _win_text(game_name: str, header: str, entry: int, mult: float) -> tuple[str, str, bool]:
    """تولید متن برد — خروجی: (text, is_win)"""
    full = int(entry * mult)
    prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
    text = header + f"🎉 <b>بردی!</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b> زرکوین"
    return text, prize, True


def _lose_text(header: str, entry: int) -> str:
    return header + f"😢 باختی! {utils.fmt(entry)} زرکوین از دست رفت."


async def handle_callback(query, context, data, user_id):
    if data == "casino:cancel":
        pending = utils.casino_pending.pop(user_id, None)
        if pending:
            await db.add_balance(user_id, pending["entry"])
            await utils.safe_edit(query, f"❌ بازی لغو شد و {utils.fmt(pending['entry'])} زرکوین برگشت.", casino_menu_kb())
        else:
            await utils.safe_answer(query, "❌ بازی فعالی نداری", show_alert=True)
            return
        await utils.safe_answer(query)
        return

    if data.count(":") == 1:
        cg = data.split(":")[1]
        if cg in config.CASINO_GAMES:
            g = config.CASINO_GAMES[cg]
            utils.user_states[user_id] = {"action": "casino_entry", "game": cg}
            msg = await utils.safe_edit(query, f"{g['emoji']} <b>{g['name']}</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>{utils.fmt(g['min'])}</b> زرکوین\n💵 کارمزد: <b>10%</b> از جایزه\n\nمبلغ ورودی رو بفرست:", casino_back_kb())
            if msg:
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
        chat_id = query.message.chat_id
        is_win = False

        if cg == "dice":
            try:
                dice_msg = await context.bot.send_dice(
                    chat_id=chat_id, emoji="🎲",
                    reply_to_message_id=query.message.message_id,
                    allow_sending_without_reply=True)
            except Exception as e:
                logger.error(f"Dice send error: {e}")
                await db.add_balance(user_id, entry)
                await utils.safe_edit(query, "❌ خطا در ارتباط با تلگرام. پول شما برگشت داده شد.", casino_back_kb())
                await utils.safe_answer(query)
                return

            await asyncio.sleep(4.5)
            res = dice_msg.dice.value
            face = DICE_FACES.get(res, "🎲")

            if parts[3] == "exact":
                choice_text = f"دقیقاً {parts[4]}"
                is_win = (res == int(parts[4]))
                mult = 3.0
            else:
                if parts[4] == "even":
                    choice_text = "زوج"
                    is_win = (res % 2 == 0)
                else:
                    choice_text = "فرد"
                    is_win = (res % 2 != 0)
                mult = 1.5

            header = f"🎲 <b>تاس</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه: {face} <b>{res}</b>\nانتخاب تو: {choice_text}\n\n"

            if is_win:
                text, prize, _ = _win_text("تاس", header, entry, mult)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        elif cg == "coin":
            res = random.choice(["heads", "tails"])
            header = f"🪙 <b>شیر یا خط</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه: <b>{'شیر 🦁' if res == 'heads' else 'خط ✖️'}</b>\nانتخاب تو: {'شیر 🦁' if parts[3] == 'heads' else 'خط ✖️'}\n\n"
            is_win = (res == parts[3])
            if is_win:
                text, prize, _ = _win_text("شیر یا خط", header, entry, 2)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        elif cg == "card":
            res = random.choice(list(config.CARD_SUITS.keys()))
            header = f"🃏 <b>کارت شانس</b>\n━━━━━━━━━━━━━━━━━━\n🎯 کارت: <b>{config.CARD_SUITS[res]}</b> ({config.CARD_SUITS_FA[res]})\nانتخاب تو: {config.CARD_SUITS[parts[3]]} ({config.CARD_SUITS_FA[parts[3]]})\n\n"
            is_win = (res == parts[3])
            if is_win:
                text, prize, _ = _win_text("کارت شانس", header, entry, 4)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        elif cg == "roulette":
            # رولت اروپایی: 0-36
            # 0 = سبز، اعداد فرد = قرمز، اعداد زوج = مشکی
            res = random.randint(0, 36)
            if res == 0:
                color = "green"
                face = "🟢"
            elif res in config.ROULETTE_RED:
                color = "red"
                face = "🔴"
            else:
                color = "black"
                face = "⚫"

            color_fa = {"red": "قرمز 🔴", "black": "مشکی ⚫", "green": "سبز 🟢"}
            choice = parts[3]
            header = f"🎡 <b>رولت</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه: {face} <b>{res}</b> ({color_fa[color]})\nانتخاب تو: {color_fa.get(choice, choice)}\n\n"
            is_win = (color == choice)
            if is_win:
                mult = 36 if choice == "green" else 2
                text, prize, _ = _win_text("رولت", header, entry, mult)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        elif cg == "mines":
            # مین‌یاب: ۵ در، ۳ جواهر، ۲ مین
            gems = set(random.sample(range(1, 6), config.MINES_GEMS))
            choice = int(parts[3])
            is_win = choice in gems
            # نمایش همه درها
            doors_display = ""
            for i in range(1, 6):
                if i in gems:
                    doors_display += f"در {i}: 💎 جواهر"
                else:
                    doors_display += f"در {i}: 💣 مین"
                if i == choice:
                    doors_display += " ← انتخاب تو"
                doors_display += "\n"
            header = f"💣 <b>مین‌یاب</b>\n━━━━━━━━━━━━━━━━━━\n🎯 نتیجه:\n{doors_display}\n"
            if is_win:
                text, prize, _ = _win_text("مین‌یاب", header, entry, 1.7)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        elif cg == "wheel":
            # چرخ شانس: ۶ قسمت، کاربر عدد ۱-۶ انتخاب می‌کند
            res = random.randint(1, config.WHEEL_SEGMENTS)
            choice = int(parts[3])
            header = f"🎯 <b>چرخ شانس</b>\n━━━━━━━━━━━━━━━━━━\n🎯 چرخ روی عدد <b>{res}</b> متوقف شد!\nانتخاب تو: <b>{choice}</b>\n\n"
            is_win = (res == choice)
            if is_win:
                text, prize, _ = _win_text("چرخ شانس", header, entry, 6)
                await db.add_balance(user_id, prize)
            else:
                text = _lose_text(header, entry)
            await utils.safe_edit(query, text, casino_back_kb())
            await utils.safe_answer(query)

        # ✅ ثبت ماموریت‌ها (برای همه بازی‌های کازینو)
        await _record_casino_missions(context, chat_id, user_id, is_win)
