import logging
import re
from datetime import time
from telegram import (
    ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

import config
import utils
import db
from games import rps, ttt, quiz, penalty, casino

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("zarcoin")

async def properties_menu_kb(user_id: int):
    summary = await db.get_assets_summary(user_id)
    rows = []
    for key, prop in sorted(config.PROPERTIES.items(), key=lambda x: x[1]["price"]):
        data = summary.get(key, {"count": 0, "total_income": 0})
        count = data["count"]
        inc_text = f"سود کل: {utils.fmt(count * prop['income'])}" if count > 0 else f"سود: {utils.fmt(prop['income'])}"
        label = f"{prop['emoji']} {prop['name']} | {utils.fmt(prop['price'])} | {inc_text} ({count}/{config.MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"prop:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

async def workers_menu_kb(user_id: int):
    summary = await db.get_assets_summary(user_id)
    rows = []
    for key, w in sorted(config.WORKERS.items(), key=lambda x: x[1]["price"]):
        data = summary.get(key, {"count": 0, "total_income": 0})
        count = data["count"]
        inc_text = f"سود کل: {utils.fmt(count * w['income'])}" if count > 0 else f"سود: {utils.fmt(w['income'])}"
        label = f"{w['emoji']} {w['name']} | {utils.fmt(w['price'])} | {inc_text} ({count}/{config.MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"worker:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

async def build_main_menu_text(user_id):
    user = await db.get_user(user_id)
    return (
        "✨ <b>به دنیای زرکوین خوش اومدی!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی کیف پول: <b>{utils.fmt(int(user['balance']) if user else 0)}</b> زرکوین\n\n"
        "از دکمه‌های زیر انتخاب کن 👇"
    )

async def build_bank_text(user_id):
    user = await db.get_user(user_id)
    bal, bank, card = (int(user["balance"]), int(user["bank_balance"]), utils.format_card(user["card_number"])) if user else (0, 0, "-")
    interest = int(bank * config.BANK_RATE)
    return (
        "🏦 <b>بانک زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"💳 شماره کارت شما:\n<code>{card}</code>\n\n"
        f"💰 کیف پول: <b>{utils.fmt(bal)}</b>\n"
        f"🏦 بانک: <b>{utils.fmt(bank)}</b>\n"
        f"📈 سود روزانه (2%): <b>{utils.fmt(interest)}</b>\n\n"
        "⏰ سود هر شب ساعت <b>00:00</b> به وقت تهران واریز میشه."
    )

async def build_assets_text(user_id, asset_type):
    if asset_type == "property":
        title, emoji, store = "املاک شما", "🏠", config.PROPERTIES
    else:
        title, emoji, store = "کارگرهای شما", "👷", config.WORKERS
    owned = await db.get_assets(user_id, asset_type)
    total_daily = sum(int(a["daily_income"]) for a in owned)
    grouped = {}
    for a in owned:
        grouped.setdefault(a["asset_key"], {"count": 0, "daily": 0})
        grouped[a["asset_key"]]["count"] += 1
        grouped[a["asset_key"]]["daily"] += int(a["daily_income"])
        
    lines = [f"{emoji} <b>{title}</b>", "━━━━━━━━━━━━━━━━━━", f"📊 تعداد کل: <b>{len(owned)}</b>", f"💵 درآمد روزانه کل: <b>{utils.fmt(total_daily)}</b> زرکوین\n"]
    if grouped:
        for key, data in grouped.items():
            info = store.get(key, {})
            lines.append(f"{info.get('emoji','•')} {info.get('name', key)}: {data['count']} عدد (سود کل: {utils.fmt(data['daily'])}/روز)")
    else:
        lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
    await db.ensure_user(update.effective_user)
    msg = await update.message.reply_text(await build_main_menu_text(user_id), parse_mode=ParseMode.HTML, reply_markup=utils.MAIN_MENU_KB)
    utils.remember_owner(msg, user_id)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_start(update, context)
async def cmd_zarbat(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_start(update, context)

async def cmd_zarbazi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
    await db.ensure_user(update.effective_user)
    msg = await update.message.reply_text("🎮 <b>بازی‌های زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>1,000</b> زرکوین\n💵 کارمزد: <b>10%</b> از جایزه\n\n✊ سنگ کاغذ قیچی — 1.5x\n❌ دوز — 1.7x\n🧠 کوییز — 1.8x\n⚽ پنالتی — 2x\n🎰 کازینو — تا 15x\n\nیکی رو انتخاب کن:", parse_mode=ParseMode.HTML, reply_markup=utils.GAMES_MENU_KB)
    utils.remember_owner(msg, user_id)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id
    
    await query.answer()
    prefix = data.split(":")[0]

    if prefix == "rps": await rps.handle_callback(query, context, data, user_id); return
    if prefix == "ttt": await ttt.handle_callback(query, context, data, user_id); return
    if prefix == "quiz": await quiz.handle_callback(query, context, data, user_id); return
    if prefix == "pen": await penalty.handle_callback(query, context, data, user_id); return
    if prefix == "casino": await casino.handle_callback(query, context, data, user_id); return

    PERSONAL_PREFIXES = ("menu", "bank", "prop", "worker", "transfer", "help", "game")
    if prefix in PERSONAL_PREFIXES:
        owner = utils.menu_owners.get((query.message.chat_id, query.message.message_id))
        if owner is not None and owner != user_id:
            await query.answer("❌ این منو برای شما نیست! لطفاً /start بزنید.", show_alert=True); return

    pending = utils.casino_pending.get(user_id)
    if pending and prefix != "casino":
        utils.casino_pending.pop(user_id, None)
        await db.add_balance(user_id, pending["entry"])
        await query.answer(f"⚠️ بازی قبلی لغو شد و {utils.fmt(pending['entry'])} زرکوین برگشت.", show_alert=True)

    utils.user_states.pop(user_id, None)

    if data == "menu:main":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_main_menu_text(user_id), utils.MAIN_MENU_KB); utils.remember_owner(msg, user_id); return

    if data == "bank:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_bank_text(user_id), utils.BANK_MENU_KB); utils.remember_owner(msg, user_id); return
    if data == "bank:deposit":
        utils.user_states[user_id] = {"action": "bank_deposit"}
        msg = await utils.safe_edit(query, "💰 <b>واریز به بانک</b>\n\nمبلغ مورد نظر رو بفرست:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return
    if data == "bank:withdraw":
        utils.user_states[user_id] = {"action": "bank_withdraw"}
        msg = await utils.safe_edit(query, "🏧 <b>برداشت از بانک</b>\n\nمبلغ مورد نظر رو بفرست:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data == "prop:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):", await properties_menu_kb(user_id)); utils.remember_owner(msg, user_id); return
    if data.startswith("prop:select:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        summary = await db.get_assets_summary(user_id)
        count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await query.answer(f"❌ حداکثر {config.MAX_PER_KEY} عدد از این ملک مجاز است!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < prop["price"]: await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        
        new_total_inc = (count + 1) * prop['income']
        text = (
            f"🏠 <b>تایید خرید ملک</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🏷 نام: {prop['emoji']} <b>{prop['name']}</b>\n"
            f"💰 قیمت هر عدد: <b>{utils.fmt(prop['price'])}</b> زرکوین\n"
            f"📈 سود روزانه هر عدد: <b>{utils.fmt(prop['income'])}</b>\n"
            f"📊 تعداد فعلی شما: {count}/{config.MAX_PER_KEY}\n"
            f"💰 سود کل این ملک (بعد از خرید): <b>{utils.fmt(new_total_inc)}</b> زرکوین\n\n"
            f"آیا از خرید مطمئنی؟"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ بله، بخر", callback_data=f"prop:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="prop:menu")]])
        msg = await utils.safe_edit(query, text, kb); utils.remember_owner(msg, user_id); return
    if data.startswith("prop:confirm:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        r = await db.buy_asset(user_id, "property", key, prop["price"], prop["income"])
        if r == "ok": await query.answer(f"✅ {prop['name']} خریداری شد!", show_alert=True)
        elif r == "limit": await query.answer(f"❌ حداکثر {config.MAX_PER_KEY} عدد مجاز است!", show_alert=True)
        elif r == "balance": await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else: await query.answer("❌ خطا", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇 از لیست زیر انتخاب کن:", await properties_menu_kb(user_id)); utils.remember_owner(msg, user_id); return

    if data == "worker:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):", await workers_menu_kb(user_id)); utils.remember_owner(msg, user_id); return
    if data.startswith("worker:select:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        summary = await db.get_assets_summary(user_id)
        count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await query.answer(f"❌ حداکثر {config.MAX_PER_KEY} عدد از این کارگر مجاز است!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < w["price"]: await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        
        new_total_inc = (count + 1) * w['income']
        text = (
            f"👷 <b>تایید استخدام کارگر</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🏷 نام: {w['emoji']} <b>{w['name']}</b>\n"
            f"💰 قیمت هر عدد: <b>{utils.fmt(w['price'])}</b> زرکوین\n"
            f"📈 سود روزانه هر عدد: <b>{utils.fmt(w['income'])}</b>\n"
            f"📊 تعداد فعلی شما: {count}/{config.MAX_PER_KEY}\n"
            f"💰 سود کل این کارگر (بعد از خرید): <b>{utils.fmt(new_total_inc)}</b> زرکوین\n\n"
            f"آیا از استخدام مطمئنی؟"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ بله، استخدام کن", callback_data=f"worker:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="worker:menu")]])
        msg = await utils.safe_edit(query, text, kb); utils.remember_owner(msg, user_id); return
    if data.startswith("worker:confirm:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        r = await db.buy_asset(user_id, "worker", key, w["price"], w["income"])
        if r == "ok": await query.answer(f"✅ {w['name']} استخدام شد!", show_alert=True)
        elif r == "limit": await query.answer(f"❌ حداکثر {config.MAX_PER_KEY} عدد مجاز است!", show_alert=True)
        elif r == "balance": await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else: await query.answer("❌ خطا", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇 از لیست زیر انتخاب کن:", await workers_menu_kb(user_id)); utils.remember_owner(msg, user_id); return

    if data == "game:menu":
        msg = await utils.safe_edit(query, "🎮 <b>بازی‌های زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>1,000</b> زرکوین\n💵 کارمزد: <b>10%</b> از جایزه\n\n✊ سنگ کاغذ قیچی — 1.5x\n❌ دوز — 1.7x\n🧠 کوییز — 1.8x\n⚽ پنالتی — 2x\n🎰 کازینو — تا 15x\n\nیکی رو انتخاب کن:", utils.GAMES_MENU_KB)
        utils.remember_owner(msg, user_id); return

    if data == "game:casino":
        msg = await utils.safe_edit(query, "🎰 <b>کازینو زر</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>10,000</b> زرکوین\n💵 کارمزد: <b>10%</b> از جایزه\n\n🎲 بازی‌ها:\n• 🎰 اسلات — تا 15 برابر\n• 🎲 تاس — تا 3 برابر\n• 🪙 شیر یا خط — 2 برابر\n• 🃏 کارت شانس — 4 برابر\n\nیکی رو انتخاب کن:", casino.casino_menu_kb())
        utils.remember_owner(msg, user_id); return

    if data.startswith("game:") and data.count(":") == 1:
        gk = data.split(":", 1)[1]
        if gk in config.GAMES:
            g = config.GAMES[gk]
            utils.user_states[user_id] = {"action": "game_entry", "game": gk}
            msg = await utils.safe_edit(query, f"{g['emoji']} <b>{g['name']}</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>{utils.fmt(g['min'])}</b> زرکوین\n👥 بازیکنان: {g['players']}\n💵 کارمزد: <b>10%</b> از جایزه\n\nمبلغ ورودی رو بفرست:", utils.BACK_GAMES_KB)
            utils.remember_owner(msg, user_id)
        return

    if data == "help:menu":
        msg = await utils.safe_edit(query, config.HELP_TEXT, utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data == "transfer:start":
        utils.user_states[user_id] = {"action": "transfer_amount"}
        msg = await utils.safe_edit(query, "💸 <b>انتقال زرکوین</b>\n\nمبلغ مورد نظر رو بفرست:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return
    if data.startswith("tr:c:"):
        await confirm_transfer(query, int(data.split(":")[2])); return
    if data.startswith("tr:x:"):
        utils.pending_transfers.pop(user_id, None)
        msg = await utils.safe_edit(query, "❌ انتقال لغو شد.", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data.startswith("room:cancel:"):
        await cancel_room(query, data.split(":")[2]); return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user, user_id, text = update.effective_user, update.effective_user.id, update.message.text.strip()

    if text == "لغو" and update.message.reply_to_message:
        await handle_cancel(user_id, update.message); return

    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
        await update.message.reply_text(f"⚠️ بازی قبلی کازینو لغو شد و {utils.fmt(pending['entry'])} زرکوین برگشت."); return

    state = utils.user_states.get(user_id)
    if not state: return
    action = state["action"]

    if action in ("bank_deposit", "bank_withdraw"):
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        await db.ensure_user(user)
        ok = await db.bank_deposit(user_id, amount) if action == "bank_deposit" else await db.bank_withdraw(user_id, amount)
        utils.user_states.pop(user_id, None)
        if ok:
            await update.message.reply_text(f"✅ <b>{utils.fmt(amount)}</b> زرکوین {'به بانک واریز شد' if action == 'bank_deposit' else 'از بانک برداشت شد'}.", parse_mode=ParseMode.HTML, reply_markup=utils.MAIN_MENU_KB)
        else: await update.message.reply_text("❌ موجودی کافی نیست", reply_markup=utils.MAIN_MENU_KB)
        return

    if action == "game_entry":
        gk = state["game"]
        g = config.GAMES.get(gk)
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]: await update.message.reply_text(f"❌ حداقل ورودی {utils.fmt(g['min'])} است"); return
        await db.ensure_user(user)
        if not await db.deduct_balance(user_id, amount): await update.message.reply_text("❌ موجودی کافی نیست"); return
        utils.user_states.pop(user_id, None)

        if gk == "penalty": await penalty.start_game(update, amount)
        elif gk == "rps": await rps.create_room(update, user, amount)
        elif gk == "ttt": await ttt.create_room(update, user, amount)
        elif gk == "quiz": await quiz.create_room(update, user, amount)
        return

    if action == "casino_entry":
        cg = state["game"]
        g = config.CASINO_GAMES.get(cg)
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]: await update.message.reply_text(f"❌ حداقل ورودی {utils.fmt(g['min'])} است"); return
        await db.ensure_user(user)
        if not await db.deduct_balance(user_id, amount): await update.message.reply_text("❌ موجودی کافی نیست"); return
        utils.user_states.pop(user_id, None)

        if cg == "slots": await casino.play_slots(update, user_id, amount)
        else:
            utils.casino_pending[user_id] = {"entry": amount, "game": cg, "chat_id": update.effective_chat.id}
            if cg == "dice":
                msg = await update.message.reply_text(f"🎲 <b>تاس</b>\n💰 ورودی: {utils.fmt(amount)}\n\n⚠️ <b>دقت کن! اگر اشتباه حدس بزنی پولت برنمی‌گرده.</b>\n\nانتخاب کن:", parse_mode=ParseMode.HTML, reply_markup=casino.casino_dice_kb())
                utils.remember_owner(msg, user_id)
            elif cg == "coin":
                msg = await update.message.reply_text(f"🪙 <b>شیر یا خط</b>\n💰 ورودی: {utils.fmt(amount)}\n\nانتخاب کن:", parse_mode=ParseMode.HTML, reply_markup=casino.casino_coin_kb())
                utils.remember_owner(msg, user_id)
            elif cg == "card":
                msg = await update.message.reply_text(f"🃏 <b>کارت شانس</b>\n💰 ورودی: {utils.fmt(amount)}\n\nکدام خال؟", parse_mode=ParseMode.HTML, reply_markup=casino.casino_card_kb())
                utils.remember_owner(msg, user_id)
        return

    if action == "transfer_amount":
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        fee = int(amount * config.TRANSFER_FEE_RATE) if amount > config.TRANSFER_FEE_MIN else 0
        total = amount + fee
        u = await db.get_user(user_id)
        if int(u["balance"]) < total: await update.message.reply_text(f"❌ موجودی کافی نیست (نیاز: {utils.fmt(total)})"); return
        utils.user_states[user_id] = {"action": "transfer_card", "amount": amount, "fee": fee}
        msg = await update.message.reply_text(f"💸 مبلغ: <b>{utils.fmt(amount)}</b>\n💵 کارمزد: <b>{utils.fmt(fee)}</b>\n📊 مجموع کسر: <b>{utils.fmt(total)}</b>\n\nشماره کارت مقصد رو بفرست:", parse_mode=ParseMode.HTML, reply_markup=utils.BACK_MAIN_KB)
        utils.remember_owner(msg, user_id); return

    if action == "transfer_card":
        recipient = await db.find_user_by_card(text)
        if not recipient: await update.message.reply_text("❌ کاربری با این شماره کارت پیدا نشد"); return
        if recipient["user_id"] == user_id: await update.message.reply_text("❌ به خودت نمی‌تونی انتقال بدی"); return
        amount, fee = state["amount"], state["fee"]
        utils.pending_transfers[user_id] = {"recipient_id": recipient["user_id"], "recipient_name": recipient["first_name"] or str(recipient["user_id"]), "amount": amount, "fee": fee, "total": amount+fee}
        utils.user_states.pop(user_id, None)
        msg = await update.message.reply_text(f"💸 <b>تأیید انتقال</b>\n━━━━━━━━━━━━━━━━━━\n👤 گیرنده: {utils.escape(recipient['first_name'])}\n💳 کارت: <code>{utils.format_card(recipient['card_number'])}</code>\n💰 مبلغ: <b>{utils.fmt(amount)}</b>\n💵 کارمزد: <b>{utils.fmt(fee)}</b>\n📊 مجموع کسر: <b>{utils.fmt(amount+fee)}</b>\n\nآیا تأیید می‌کنی؟", parse_mode=ParseMode.HTML, reply_markup=utils.transfer_confirm_kb(user_id))
        utils.remember_owner(msg, user_id); return

async def handle_cancel(user_id: int, message):
    sess = utils.casino_pending.pop(user_id, None)
    if sess: await db.add_balance(user_id, sess["entry"]); await message.reply_text(f"❌ بازی کازینو لغو شد.\n💰 <b>{utils.fmt(sess['entry'])}</b> زرکوین برگشت.", parse_mode=ParseMode.HTML); return
    pen = utils.penalty_games.pop(user_id, None)
    if pen: await db.add_balance(user_id, pen["entry"]); await message.reply_text(f"❌ پنالتی لغو شد.\n💰 <b>{utils.fmt(pen['entry'])}</b> زرکوین برگشت.", parse_mode=ParseMode.HTML); return
    rid = utils.find_user_room(user_id)
    if rid:
        room = utils.rooms.get(rid)
        if room and room["status"] != "finished":
            for pid in room["players"]: await db.add_balance(pid, room["entry"])
            entry = room["entry"]; room["status"] = "cancelled"; utils.rooms.pop(rid, None)
            await message.reply_text(f"❌ بازی لغو شد.\n💰 <b>{utils.fmt(entry)}</b> زرکوین به هر بازیکن برگشت.", parse_mode=ParseMode.HTML); return
    if user_id in utils.user_states: utils.user_states.pop(user_id, None); await message.reply_text("❌ عملیات لغو شد."); return
    await message.reply_text("ℹ️ بازی فعالی برای لغو نداری.")

async def cancel_room(query, room_id: str):
    room = utils.rooms.get(room_id)
    if not room: await query.answer("❌ اتاق نیست", show_alert=True); return
    if query.from_user.id not in room["players"] and query.from_user.id != room["creator"]: await query.answer("❌ اجازه نداری", show_alert=True); return
    if room["status"] == "finished": return
    for pid in room["players"]: await db.add_balance(pid, room["entry"])
    room["status"] = "cancelled"; utils.rooms.pop(room_id, None)
    await utils.safe_edit(query, "❌ بازی لغو شد و پول‌ها برگشت داده شد.", utils.BACK_GAMES_KB)

async def confirm_transfer(query, owner_id: int):
    if query.from_user.id != owner_id: await query.answer("❌ این دکمه برای تو نیست", show_alert=True); return
    pending = utils.pending_transfers.pop(owner_id, None)
    if not pending: await query.answer("❌ انتقال منقضی شده", show_alert=True); return
    if not await db.transfer_coins(owner_id, pending["recipient_id"], pending["amount"], pending["fee"]):
        await query.answer("❌ موجودی کافی نیست", show_alert=True); await utils.safe_edit(query, "❌ انتقال انجام نشد.", utils.BACK_MAIN_KB); return
    await utils.safe_edit(query, f"✅ <b>انتقال انجام شد!</b>\n\n👤 گیرنده: {utils.escape(pending['recipient_name'])}\n💰 مبلغ: <b>{utils.fmt(pending['amount'])}</b>\n💵 کارمزد: <b>{utils.fmt(pending['fee'])}</b>", utils.BACK_MAIN_KB)
    try: await query.bot.send_message(pending["recipient_id"], f"🎁 <b>زرکوین دریافت کردی!</b>\n\n💰 مبلغ: <b>{utils.fmt(pending['amount'])}</b> زرکوین\n👤 از طرف: {utils.escape(query.from_user.first_name)}", parse_mode=ParseMode.HTML)
    except Exception: pass

async def owner_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID: return
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.from_user: return
    m = re.match(r"^انتقال زرکوین\s+([\d۰-۹,،]+)\s*$", msg.text or "")
    if not m: return
    amount = utils.parse_amount(m.group(1))
    if not amount: await msg.reply_text("❌ مبلغ نامعتبر"); return
    target = msg.reply_to_message.from_user
    if target.is_bot: await msg.reply_text("❌ به بات نمی‌شه انتقال داد"); return
    await db.ensure_user(target); await db.add_balance(target.id, amount)
    await msg.reply_text(f"✅ <b>{utils.fmt(amount)}</b> زرکوین به {utils.escape(target.first_name)} واریز شد.", parse_mode=ParseMode.HTML)

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if not cm or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"): return
    if cm.new_chat_member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and cm.old_chat_member.status in (ChatMember.LEFT, ChatMember.KICKED):
        try: await context.bot.send_message(update.effective_chat.id, "✨ <b>زرکوین بات در این گروه فعال شد!</b> ✨\n\n💡 برای شروع بنویس: <code>زربات</code>\n🎮 برای بازی‌ها بنویس: <code>زر بازی</code>", parse_mode=ParseMode.HTML)
        except Exception: pass

async def post_init(app: Application):
    await db.init_db_pool(); await db.init_db()
    try: await db.daily_payout()
    except Exception: pass
    app.job_queue.run_daily(db.daily_payout, time=time(hour=0, minute=0, tzinfo=utils.TEHRAN), name="daily_payout")

async def post_shutdown(app: Application):
    await db.close_db_pool()

def main():
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    
    app.add_handler(MessageHandler(filters.Regex(r"^زربات$"), cmd_zarbat))
    app.add_handler(MessageHandler(filters.Regex(r"^زر\s*بازی$"), cmd_zarbazi))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.Regex(r"^انتقال زرکوین\s+[\d۰-۹,،]+"), owner_give))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("🚀 Bot starting with polling (Optimized)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
