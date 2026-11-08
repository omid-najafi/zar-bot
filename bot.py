import logging
import re
import random
from datetime import datetime, time
from telegram import ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

import config
import utils
import db
import kabareh
from games import rps, ttt, quiz, penalty, casino

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("zarcoin")


# ═══════════ کیبوردهای پویا ═══════════
async def properties_menu_kb(user_id: int):
    summary = await db.get_assets_summary(user_id)
    rows = []
    for key, prop in sorted(config.PROPERTIES.items(), key=lambda x: x[1]["price"]):
        data = summary.get(key, {"count": 0})
        count = data["count"]
        inc = f"سود کل: {utils.fmt(count * prop['income'])}" if count > 0 else f"سود: {utils.fmt(prop['income'])}"
        label = f"{prop['emoji']} {prop['name']} | {utils.fmt(prop['price'])} | {inc} ({count}/{config.MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"prop:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


async def workers_menu_kb(user_id: int):
    summary = await db.get_assets_summary(user_id)
    rows = []
    for key, w in sorted(config.WORKERS.items(), key=lambda x: x[1]["price"]):
        data = summary.get(key, {"count": 0})
        count = data["count"]
        inc = f"سود کل: {utils.fmt(count * w['income'])}" if count > 0 else f"سود: {utils.fmt(w['income'])}"
        label = f"{w['emoji']} {w['name']} | {utils.fmt(w['price'])} | {inc} ({count}/{config.MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"worker:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


# ═══════════ متن‌ها ═══════════
async def build_main_menu_text(user_id):
    user = await db.get_user(user_id)
    total_xp = int(user.get("total_xp", 0)) if user else 0
    level, xp_in, xp_next = utils.calc_level(total_xp)
    bar = utils.format_progress_bar(xp_in, xp_next, 12)
    return (
        "✨ <b>به دنیای زرکوین!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⭐ لول: <b>{level}</b>\n"
        f"✨ {bar} <b>{utils.fmt(xp_in)}/{utils.fmt(xp_next)}</b>\n"
        f"💰 موجودی: <b>{utils.fmt(int(user['balance']) if user else 0)}</b>\n\n"
        "از دکمه‌ها انتخاب کن 👇"
    )


async def build_bank_text(user_id):
    user = await db.get_user(user_id)
    bal, bank, card = (int(user["balance"]), int(user["bank_balance"]), utils.format_card(user["card_number"])) if user else (0, 0, "-")
    interest = int(bank * config.BANK_RATE)
    return (
        "🏦 <b>بانک زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"💳 <code>{card}</code>\n\n"
        f"💰 کیف پول: <b>{utils.fmt(bal)}</b>\n"
        f"🏦 بانک: <b>{utils.fmt(bank)}</b>\n"
        f"📈 سود روزانه: <b>{utils.fmt(interest)}</b>"
    )


async def build_assets_text(user_id, asset_type):
    if asset_type == "property":
        title, emoji, store = "املاک", "🏠", config.PROPERTIES
    else:
        title, emoji, store = "کارگرها", "👷", config.WORKERS
    owned = await db.get_assets(user_id, asset_type)
    total_daily = sum(int(a["daily_income"]) for a in owned)
    grouped = {}
    for a in owned:
        grouped.setdefault(a["asset_key"], {"count": 0, "daily": 0})
        grouped[a["asset_key"]]["count"] += 1
        grouped[a["asset_key"]]["daily"] += int(a["daily_income"])
    lines = [f"{emoji} <b>{title}</b>", "━━━━━━━━━━━━━━━━━━", f"📊 کل: <b>{len(owned)}</b>", f"💵 درآمد روزانه: <b>{utils.fmt(total_daily)}</b>\n"]
    for key, data in grouped.items():
        info = store.get(key, {})
        lines.append(f"{info.get('emoji','•')} {info.get('name', key)}: {data['count']} ({utils.fmt(data['daily'])}/روز)")
    if not grouped: lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)


async def build_missions_text(user_id):
    await db.ensure_daily_missions(user_id)
    missions = await db.get_user_missions(user_id)
    user = await db.get_user(user_id)
    total_xp = int(user.get("total_xp", 0)) if user else 0
    level, xp_in, xp_next = utils.calc_level(total_xp)
    lines = ["🎯 <b>ماموریت‌های امروز</b>", "━━━━━━━━━━━━━━━━━━"]
    completed = 0
    for i, m in enumerate(missions, 1):
        t = config.MISSION_TEMPLATES.get(m["mission_key"], {})
        desc = t.get("desc", m["mission_key"])
        xp = int(m["xp_reward"]); p = int(m["progress"]); tg = int(m["target"])
        if m["completed"]:
            completed += 1
            lines.append(f"✅ {i}. {desc} (+{xp} XP)")
        else:
            lines.append(f"🔄 {i}. {desc} ({p}/{tg}) +{xp} XP")
    lines.append(f"\n📊 {completed}/{config.DAILY_MISSION_COUNT} انجام شد")
    lines.append(f"⭐ لول: {level} | ✨ {xp_in}/{xp_next}")
    return "\n".join(lines)


# ═══════════ Command Handlers ═══════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ بررسی جوین اجباری
    if not await utils.verify_membership(update, context):
        return
    user_id = update.effective_user.id
    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
    await db.ensure_user(update.effective_user)
    msg = await update.message.reply_text(await build_main_menu_text(user_id), parse_mode=ParseMode.HTML, reply_markup=utils.MAIN_MENU_KB)
    utils.remember_owner(msg, user_id)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await utils.verify_membership(update, context):
        return
    await cmd_start_no_check(update, context)


async def cmd_start_no_check(update, context):
    user_id = update.effective_user.id
    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
    await db.ensure_user(update.effective_user)
    msg = await update.message.reply_text(await build_main_menu_text(user_id), parse_mode=ParseMode.HTML, reply_markup=utils.MAIN_MENU_KB)
    utils.remember_owner(msg, user_id)


async def cmd_zarbat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await utils.verify_membership(update, context):
        return
    await cmd_start_no_check(update, context)


async def cmd_zarbazi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await utils.verify_membership(update, context):
        return
    user_id = update.effective_user.id
    await db.ensure_user(update.effective_user)
    msg = await update.message.reply_text("🎮 <b>بازی‌ها</b>\n💰 حداقل 1,000\n💵 کارمزد 10%", parse_mode=ParseMode.HTML, reply_markup=utils.GAMES_MENU_KB)
    utils.remember_owner(msg, user_id)


async def cmd_zar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await utils.verify_membership(update, context):
        return
    user = update.effective_user
    user_id = user.id
    user_data = await db.ensure_user(user)
    last_zar = user_data.get("last_zar")
    now = datetime.now(utils.TEHRAN)
    if last_zar:
        try:
            last_dt = datetime.fromisoformat(last_zar)
            elapsed = (now - last_dt).total_seconds()
            if elapsed < config.ZAR_COOLDOWN_SECONDS:
                remaining = int(config.ZAR_COOLDOWN_SECONDS - elapsed)
                await update.message.reply_text(f"⏳ صبر کن! {remaining // 60}:{remaining % 60:02d}", parse_mode=ParseMode.HTML)
                return
        except Exception: pass
    total_xp = int(user_data.get("total_xp", 0))
    level, _, _ = utils.calc_level(total_xp)
    min_c = level * 100; max_c = level * 100 + 100
    reward = random.randint(min_c, max_c)
    await db.add_balance(user_id, reward)
    await db.set_last_zar(user_id, now.isoformat())
    result = await db.progress_mission(user_id, "zar_collect", 1, base_xp=config.BASE_XP_ZAR)
    await update.message.reply_text(f"🌾 <b>زر!</b>\n💰 +{utils.fmt(reward)}\n⭐ لول {level}\n⏰ بعدی: 5 دقیقه", parse_mode=ParseMode.HTML)
    await utils.notify_mission(context, update.message.chat_id, result)


# ═══════════ Group Watcher (لاگ آیدی گروه) ═══════════
async def group_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utils.log_group_chat_id(update)


# ═══════════ Callback Router ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    data = query.data or ""
    user_id = query.from_user.id
    prefix = data.split(":")[0]

    # ✅ اولویت ویژه: بررسی عضویت
    if data == "check_membership":
        is_joined, missing = await utils.check_membership_force(context.bot, user_id)
        if is_joined:
            await query.answer("✅ عضویت تأیید شد!", show_alert=True)
            await db.ensure_user(query.from_user)
            text = await build_main_menu_text(user_id)
            msg = await utils.safe_edit(query, text, utils.MAIN_MENU_KB)
            if msg: utils.remember_owner(msg, user_id)
        else:
            missing_txt = "\n".join(f"• {m}" for m in missing) if missing else "نامشخص"
            await query.answer(f"❌ هنوز عضو این‌ها نشدی:\n{missing_txt}", show_alert=True)
        return

    # ✅ بررسی عضویت برای کال‌بک‌های حساس
    if data in ("menu:main", "kabareh:menu", "game:menu", "mission:menu"):
        if not await utils.verify_membership(update, context):
            return

    # کاباره
    if prefix == "kabareh":
        await kabareh.handle_callback(query, context, data, user_id); return

    # بازی‌ها
    if prefix == "rps": await rps.handle_callback(query, context, data, user_id); return
    if prefix == "ttt": await ttt.handle_callback(query, context, data, user_id); return
    if prefix == "quiz": await quiz.handle_callback(query, context, data, user_id); return
    if prefix == "pen": await penalty.handle_callback(query, context, data, user_id); return
    if prefix == "casino": await casino.handle_callback(query, context, data, user_id); return

    # چک مالکیت منو
    PERSONAL = ("menu", "bank", "prop", "worker", "transfer", "help", "game", "mission")
    if prefix in PERSONAL and query.message:
        owner = utils.menu_owners.get((query.message.chat_id, query.message.message_id))
        if owner is not None and owner != user_id:
            await utils.safe_answer(query, "❌ این منو برای شما نیست!", show_alert=True); return

    await utils.safe_answer(query)

    pending = utils.casino_pending.get(user_id)
    if pending and prefix != "casino":
        utils.casino_pending.pop(user_id, None)
        await db.add_balance(user_id, pending["entry"])

    utils.user_states.pop(user_id, None)

    if data == "menu:main":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_main_menu_text(user_id), utils.MAIN_MENU_KB)
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "mission:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_missions_text(user_id), utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "bank:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_bank_text(user_id), utils.BANK_MENU_KB)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data == "bank:deposit":
        utils.user_states[user_id] = {"action": "bank_deposit"}
        msg = await utils.safe_edit(query, "💰 مبلغ واریز:", utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data == "bank:withdraw":
        utils.user_states[user_id] = {"action": "bank_withdraw"}
        msg = await utils.safe_edit(query, "🏧 مبلغ برداشت:", utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "prop:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇:", await properties_menu_kb(user_id))
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("prop:select:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        summary = await db.get_assets_summary(user_id); count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await utils.safe_answer(query, "❌ محدودیت!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < prop["price"]: await utils.safe_answer(query, "❌ موجودی!", show_alert=True); return
        new_total = (count + 1) * prop['income']
        text = f"🏠 <b>{prop['name']}</b>\n💰 {utils.fmt(prop['price'])}\n📈 سود بعد: {utils.fmt(new_total)}\n\nمطمئنی؟"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ بخر", callback_data=f"prop:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="prop:menu")]])
        msg = await utils.safe_edit(query, text, kb)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("prop:confirm:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        r = await db.buy_asset(user_id, "property", key, prop["price"], prop["income"])
        if r == "ok":
            await utils.safe_answer(query, "✅ خریداری شد!", show_alert=True)
            result = await db.progress_mission(user_id, "buy_property", 1, base_xp=config.BASE_XP_BUY_ASSET)
            await utils.notify_mission(context, query.message.chat_id, result)
        elif r == "limit": await utils.safe_answer(query, "❌ محدودیت!", show_alert=True)
        elif r == "balance": await utils.safe_answer(query, "❌ موجودی!", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇:", await properties_menu_kb(user_id))
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "worker:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇:", await workers_menu_kb(user_id))
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("worker:select:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        summary = await db.get_assets_summary(user_id); count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await utils.safe_answer(query, "❌ محدودیت!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < w["price"]: await utils.safe_answer(query, "❌ موجودی!", show_alert=True); return
        new_total = (count + 1) * w['income']
        text = f"👷 <b>{w['name']}</b>\n💰 {utils.fmt(w['price'])}\n📈 سود بعد: {utils.fmt(new_total)}\n\nمطمئنی؟"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ استخدام", callback_data=f"worker:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="worker:menu")]])
        msg = await utils.safe_edit(query, text, kb)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("worker:confirm:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        r = await db.buy_asset(user_id, "worker", key, w["price"], w["income"])
        if r == "ok":
            await utils.safe_answer(query, "✅ استخدام شد!", show_alert=True)
            result = await db.progress_mission(user_id, "buy_worker", 1, base_xp=config.BASE_XP_BUY_ASSET)
            await utils.notify_mission(context, query.message.chat_id, result)
        elif r == "limit": await utils.safe_answer(query, "❌ محدودیت!", show_alert=True)
        elif r == "balance": await utils.safe_answer(query, "❌ موجودی!", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇:", await workers_menu_kb(user_id))
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "game:menu":
        msg = await utils.safe_edit(query, "🎮 <b>بازی‌ها</b>\n💰 حداقل 1,000\n💵 کارمزد 10%", utils.GAMES_MENU_KB)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data == "game:casino":
        msg = await utils.safe_edit(query, "🎰 <b>کازینو</b>\n💰 حداقل 10,000", casino.casino_menu_kb())
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("game:") and data.count(":") == 1:
        gk = data.split(":", 1)[1]
        if gk in config.GAMES:
            g = config.GAMES[gk]
            utils.user_states[user_id] = {"action": "game_entry", "game": gk}
            msg = await utils.safe_edit(query, f"{g['emoji']} <b>{g['name']}</b>\n💰 حداقل {utils.fmt(g['min'])}\n\nمبلغ:", utils.BACK_GAMES_KB)
            if msg: utils.remember_owner(msg, user_id)
        return

    if data == "help:menu":
        msg = await utils.safe_edit(query, config.HELP_TEXT, utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return

    if data == "transfer:start":
        utils.user_states[user_id] = {"action": "transfer_amount"}
        msg = await utils.safe_edit(query, "💸 مبلغ انتقال:", utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("tr:c:"):
        await confirm_transfer(query, int(data.split(":")[2])); return
    if data.startswith("tr:x:"):
        utils.pending_transfers.pop(user_id, None)
        msg = await utils.safe_edit(query, "❌ لغو شد.", utils.BACK_MAIN_KB)
        if msg: utils.remember_owner(msg, user_id)
        return
    if data.startswith("room:cancel:"):
        await cancel_room(query, data.split(":")[2]); return


# ═══════════ Text Handler ═══════════
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user, user_id, text = update.effective_user, update.effective_user.id, update.message.text.strip()
    
    if text == "لغو" and update.message.reply_to_message:
        await handle_cancel(user_id, update.message); return
    
    if user_id in utils.casino_pending:
        pending = utils.casino_pending.pop(user_id)
        await db.add_balance(user_id, pending["entry"])
        await update.message.reply_text(f"⚠️ بازی لغو شد. {utils.fmt(pending['entry'])} برگشت."); return
    
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
            await update.message.reply_text(f"✅ {utils.fmt(amount)} {'واریز' if action == 'bank_deposit' else 'برداشت'} شد.", reply_markup=utils.MAIN_MENU_KB)
            if action == "bank_deposit":
                base = (amount // 10000) * config.BASE_XP_DEPOSIT_10K
                result = await db.progress_mission(user_id, "deposit_bank", amount, base_xp=min(base, 500))
                await utils.notify_mission(context, update.message.chat_id, result)
        else: await update.message.reply_text("❌ موجودی کافی نیست", reply_markup=utils.MAIN_MENU_KB)
        return

    if action == "game_entry":
        gk = state["game"]; g = config.GAMES.get(gk)
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]: await update.message.reply_text(f"❌ حداقل {utils.fmt(g['min'])}"); return
        await db.ensure_user(user)
        if not await db.deduct_balance(user_id, amount): await update.message.reply_text("❌ موجودی!"); return
        utils.user_states.pop(user_id, None)
        if gk == "penalty": await penalty.start_game(update, amount, context)
        elif gk == "rps": await rps.create_room(update, user, amount)
        elif gk == "ttt": await ttt.create_room(update, user, amount)
        elif gk == "quiz": await quiz.create_room(update, user, amount)
        return

    if action == "casino_entry":
        cg = state["game"]; g = config.CASINO_GAMES.get(cg)
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]: await update.message.reply_text(f"❌ حداقل {utils.fmt(g['min'])}"); return
        await db.ensure_user(user)
        if not await db.deduct_balance(user_id, amount): await update.message.reply_text("❌ موجودی!"); return
        utils.user_states.pop(user_id, None)
        if cg == "slots": await casino.play_slots(update, user_id, amount, context)
        else:
            utils.casino_pending[user_id] = {"entry": amount, "game": cg, "chat_id": update.effective_chat.id}
            if cg == "dice":
                msg = await update.message.reply_text(f"🎲 تاس\n💰 {utils.fmt(amount)}\n\nانتخاب:", reply_markup=casino.casino_dice_kb()); utils.remember_owner(msg, user_id)
            elif cg == "coin":
                msg = await update.message.reply_text(f"🪙 شیر یا خط\n💰 {utils.fmt(amount)}", reply_markup=casino.casino_coin_kb()); utils.remember_owner(msg, user_id)
            elif cg == "card":
                msg = await update.message.reply_text(f"🃏 کارت\n💰 {utils.fmt(amount)}", reply_markup=casino.casino_card_kb()); utils.remember_owner(msg, user_id)
        return

    if action == "transfer_amount":
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        fee = int(amount * config.TRANSFER_FEE_RATE) if amount > config.TRANSFER_FEE_MIN else 0
        u = await db.get_user(user_id)
        if int(u["balance"]) < amount + fee: await update.message.reply_text(f"❌ نیاز: {utils.fmt(amount + fee)}"); return
        utils.user_states[user_id] = {"action": "transfer_card", "amount": amount, "fee": fee}
        msg = await update.message.reply_text(f"💸 {utils.fmt(amount)}\n💵 کارمزد: {utils.fmt(fee)}\n\nکارت مقصد:", reply_markup=utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id)
        return

    if action == "transfer_card":
        recipient = await db.find_user_by_card(text)
        if not recipient: await update.message.reply_text("❌ پیدا نشد"); return
        if recipient["user_id"] == user_id: await update.message.reply_text("❌ به خودت!"); return
        amount, fee = state["amount"], state["fee"]
        utils.pending_transfers[user_id] = {"recipient_id": recipient["user_id"], "recipient_name": recipient["first_name"] or "", "amount": amount, "fee": fee}
        utils.user_states.pop(user_id, None)
        msg = await update.message.reply_text(f"💸 تایید:\n👤 {utils.escape(recipient['first_name'])}\n💰 {utils.fmt(amount)}", reply_markup=utils.transfer_confirm_kb(user_id)); utils.remember_owner(msg, user_id)
        return


# ═══════════ Helpers ═══════════
async def handle_cancel(user_id: int, message):
    sess = utils.casino_pending.pop(user_id, None)
    if sess: await db.add_balance(user_id, sess["entry"]); await message.reply_text(f"❌ لغو. {utils.fmt(sess['entry'])} برگشت."); return
    pen = utils.penalty_games.pop(user_id, None)
    if pen: await db.add_balance(user_id, pen["entry"]); await message.reply_text(f"❌ لغو."); return
    rid = utils.find_user_room(user_id)
    if rid:
        room = utils.rooms.get(rid)
        if room and room["status"] != "finished":
            for pid in room["players"]: await db.add_balance(pid, room["entry"])
            room["status"] = "cancelled"; utils.rooms.pop(rid, None)
            await message.reply_text(f"❌ لغو."); return
    if user_id in utils.user_states: utils.user_states.pop(user_id, None); await message.reply_text("❌ لغو شد."); return
    await message.reply_text("ℹ️ بازی فعالی نداری.")


async def cancel_room(query, room_id: str):
    room = utils.rooms.get(room_id)
    if not room: await utils.safe_answer(query, "❌ اتاق نیست", show_alert=True); return
    if query.from_user.id not in room["players"] and query.from_user.id != room["creator"]: await utils.safe_answer(query, "❌ اجازه!", show_alert=True); return
    if room["status"] == "finished": return
    for pid in room["players"]: await db.add_balance(pid, room["entry"])
    room["status"] = "cancelled"; utils.rooms.pop(room_id, None)
    await utils.safe_edit(query, "❌ بازی لغو شد.", utils.BACK_GAMES_KB); await utils.safe_answer(query)


async def confirm_transfer(query, owner_id: int):
    if query.from_user.id != owner_id: await utils.safe_answer(query, "❌ دکمه برای تو نیست", show_alert=True); return
    pending = utils.pending_transfers.pop(owner_id, None)
    if not pending: await utils.safe_answer(query, "❌ منقضی", show_alert=True); return
    if not await db.transfer_coins(owner_id, pending["recipient_id"], pending["amount"], pending["fee"]):
        await utils.safe_answer(query, "❌ موجودی!", show_alert=True); await utils.safe_edit(query, "❌ انجام نشد.", utils.BACK_MAIN_KB); return
    await utils.safe_edit(query, f"✅ انتقال شد!\n👤 {utils.escape(pending['recipient_name'])}\n💰 {utils.fmt(pending['amount'])}", utils.BACK_MAIN_KB)
    await utils.safe_answer(query)
    try: await query.bot.send_message(pending["recipient_id"], f"🎁 {utils.fmt(pending['amount'])} زرکوین از {utils.escape(query.from_user.first_name)}", parse_mode=ParseMode.HTML)
    except Exception: pass
    result = await db.progress_mission(owner_id, "transfer", 1, base_xp=config.BASE_XP_TRANSFER)
    await utils.notify_mission(query.bot, query.message.chat_id, result)


async def owner_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID: return
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.from_user: return
    m = re.match(r"^انتقال زرکوین\s+([\d۰-۹,،]+)\s*$", msg.text or "")
    if not m: return
    amount = utils.parse_amount(m.group(1))
    if not amount: await msg.reply_text("❌ نامعتبر"); return
    target = msg.reply_to_message.from_user
    if target.is_bot: await msg.reply_text("❌ بات!"); return
    await db.ensure_user(target); await db.add_balance(target.id, amount)
    await msg.reply_text(f"✅ {utils.fmt(amount)} به {utils.escape(target.first_name)}", parse_mode=ParseMode.HTML)


async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if not cm or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"): return
    if cm.new_chat_member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and cm.old_chat_member.status in (ChatMember.LEFT, ChatMember.KICKED):
        try: await context.bot.send_message(update.effective_chat.id, "✨ زرکوین بات فعال شد!\n💡 زربات | زر بازی | زر", parse_mode=ParseMode.HTML)
        except Exception: pass


async def post_init(app: Application):
    logger.info("🚀 Starting...")
    await db.init_db_pool()
    await db.init_db()
    logger.info("✅ DB ready")
    try: await db.daily_payout()
    except Exception as e: logger.exception(f"payout: {e}")
    app.job_queue.run_daily(db.daily_payout, time=time(hour=0, minute=0, tzinfo=utils.TEHRAN), name="daily_payout")
    
    # لاگ کردن وضعیت جوین اجباری
    if config.REQUIRED_GROUP and config.REQUIRED_GROUP.get("id"):
        logger.info(f"✅ جوین گروه فعال: {config.REQUIRED_GROUP['name']}")
    else:
        logger.warning("⚠️ REQUIRED_GROUP.id تنظیم نشده - بررسی جوین گروه غیرفعال است")


async def post_shutdown(app: Application):
    await db.close_db_pool()


def main():
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    
    # 👇 گروه‌وانچر (اول از همه برای لاگ آیدی گروه)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, group_watcher), group=-1)
    
    # دستورات
    app.add_handler(MessageHandler(filters.Regex(r"^زربات$"), cmd_zarbat))
    app.add_handler(MessageHandler(filters.Regex(r"^زر\s*بازی$"), cmd_zarbazi))
    app.add_handler(MessageHandler(filters.Regex(r"^زر$"), cmd_zar))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    
    # سایر
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.Regex(r"^انتقال زرکوین\s+[\d۰-۹,،]+"), owner_give))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("🚀 Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
