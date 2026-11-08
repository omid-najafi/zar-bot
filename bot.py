import logging
import re
import random
from datetime import datetime, time
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
import kabareh  # ✅ ماژول کاباره
from games import rps, ttt, quiz, penalty, casino

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("zarcoin")

# ═══════════ کیبوردهای ملک و کارگر ═══════════
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

# ═══════════ متن‌ها ═══════════
async def build_main_menu_text(user_id):
    user = await db.get_user(user_id)
    total_xp = int(user.get("total_xp", 0)) if user else 0
    level, xp_in, xp_next = utils.calc_level(total_xp)
    bar = utils.format_progress_bar(xp_in, xp_next, 12)
    return (
        "✨ <b>به دنیای زرکوین خوش اومدی!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⭐ لول: <b>{level}</b>\n"
        f"✨ XP: {bar} <b>{utils.fmt(xp_in)}/{utils.fmt(xp_next)}</b>\n"
        f"💰 موجودی: <b>{utils.fmt(int(user['balance']) if user else 0)}</b> زرکوین\n\n"
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
        "⏰ سود هر شب ساعت <b>00:00</b> واریز میشه."
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
    lines = [f"{emoji} <b>{title}</b>", "━━━━━━━━━━━━━━━━━━", f"📊 تعداد کل: <b>{len(owned)}</b>", f"💵 درآمد روزانه: <b>{utils.fmt(total_daily)}</b>\n"]
    if grouped:
        for key, data in grouped.items():
            info = store.get(key, {})
            lines.append(f"{info.get('emoji','•')} {info.get('name', key)}: {data['count']} عدد (سود: {utils.fmt(data['daily'])}/روز)")
    else:
        lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)

async def build_missions_text(user_id):
    await db.ensure_daily_missions(user_id)
    missions = await db.get_user_missions(user_id)
    user = await db.get_user(user_id)
    total_xp = int(user.get("total_xp", 0)) if user else 0
    level, xp_in, xp_next = utils.calc_level(total_xp)
    lines = ["🎯 <b>ماموریت‌های امروز</b>", "━━━━━━━━━━━━━━━━━━", "هر روز 6 ماموریت جدید!\n"]
    completed = 0
    for i, m in enumerate(missions, 1):
        template = config.MISSION_TEMPLATES.get(m["mission_key"], {})
        desc = template.get("desc", m["mission_key"])
        xp = int(m["xp_reward"]); progress = int(m["progress"]); target = int(m["target"]); is_done = m["completed"]
        if is_done:
            completed += 1
            lines.append(f"✅ {i}. {desc}")
            lines.append(f"   <i>+{xp} XP دریافت شد</i>\n")
        else:
            pct = int(progress * 100 / target) if target else 0
            bar = utils.format_progress_bar(progress, target, 8)
            lines.append(f"🔄 {i}. {desc}")
            lines.append(f"   {bar} {progress}/{target} ({pct}%) | +{xp} XP\n")
    lines.append(f"📊 <b>{completed}/{config.DAILY_MISSION_COUNT}</b> انجام شده")
    lines.append(f"\n⭐ لول: <b>{level}</b> | ✨ XP: {xp_in}/{xp_next}")
    return "\n".join(lines)

# ═══════════ Commands ═══════════
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
    msg = await update.message.reply_text("🎮 <b>بازی‌های زرکوین</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل ورودی: <b>1,000</b>\n💵 کارمزد: <b>10%</b>\n\nیکی رو انتخاب کن:", parse_mode=ParseMode.HTML, reply_markup=utils.GAMES_MENU_KB)
    utils.remember_owner(msg, user_id)

async def cmd_zar(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                mins = remaining // 60; secs = remaining % 60
                await update.message.reply_text(f"⏳ <b>صبر کن!</b>\n\nتا دریافت بعدی: <b>{mins}:{secs:02d}</b>", parse_mode=ParseMode.HTML)
                return
        except Exception: pass
    total_xp = int(user_data.get("total_xp", 0))
    level, _, _ = utils.calc_level(total_xp)
    min_coin = level * 100; max_coin = level * 100 + 100
    reward = random.randint(min_coin, max_coin)
    await db.add_balance(user_id, reward)
    await db.set_last_zar(user_id, now.isoformat())
    result = await db.progress_mission(user_id, "zar_collect", 1, base_xp=config.BASE_XP_ZAR)
    text = f"🌾 <b>زر دریافت شد!</b>\n━━━━━━━━━━━━━━━━━━\n💰 <b>+{utils.fmt(reward)}</b> زرکوین\n⭐ لول: <b>{level}</b>\n🎁 بازه: {utils.fmt(min_coin)} - {utils.fmt(max_coin)}\n⏰ بعدی: <b>5 دقیقه دیگه</b>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    await utils.notify_mission(context, update.message.chat_id, result)

# ═══════════ Callback Router ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id
    prefix = data.split(":")[0]

    # ✅ بازی‌ها (خودشون safe_answer می‌کنن)
    if prefix == "rps": await rps.handle_callback(query, context, data, user_id); return
    if prefix == "ttt": await ttt.handle_callback(query, context, data, user_id); return
    if prefix == "quiz": await quiz.handle_callback(query, context, data, user_id); return
    if prefix == "pen": await penalty.handle_callback(query, context, data, user_id); return
    if prefix == "casino": await casino.handle_callback(query, context, data, user_id); return

    # ✅ چک مالکیت منو برای همه منوهای شخصی (شامل کاباره)
    PERSONAL_PREFIXES = ("menu", "bank", "prop", "worker", "transfer", "help", "game", "mission", "kabareh")
    if prefix in PERSONAL_PREFIXES:
        owner = utils.menu_owners.get((query.message.chat_id, query.message.message_id))
        if owner is not None and owner != user_id:
            await utils.safe_answer(query, "❌ این منو برای شما نیست! لطفاً /start بزنید.", show_alert=True)
            return

    # ✅ روت به کاباره (خودش safe_answer می‌کنه)
    if prefix == "kabareh":
        await kabareh.handle_callback(query, context, data, user_id)
        return

    # بقیه منوها
    await utils.safe_answer(query)

    pending = utils.casino_pending.get(user_id)
    if pending and prefix != "casino":
        utils.casino_pending.pop(user_id, None)
        await db.add_balance(user_id, pending["entry"])
        await utils.safe_answer(query, f"⚠️ بازی قبلی لغو شد و {utils.fmt(pending['entry'])} برگشت.", show_alert=True)

    utils.user_states.pop(user_id, None)

    if data == "menu:main":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_main_menu_text(user_id), utils.MAIN_MENU_KB); utils.remember_owner(msg, user_id); return

    if data == "mission:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_missions_text(user_id), utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data == "bank:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_bank_text(user_id), utils.BANK_MENU_KB); utils.remember_owner(msg, user_id); return
    if data == "bank:deposit":
        utils.user_states[user_id] = {"action": "bank_deposit"}
        msg = await utils.safe_edit(query, "💰 <b>واریز</b>\n\nمبلغ:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return
    if data == "bank:withdraw":
        utils.user_states[user_id] = {"action": "bank_withdraw"}
        msg = await utils.safe_edit(query, "🏧 <b>برداشت</b>\n\nمبلغ:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data == "prop:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇 انتخاب کن:", await properties_menu_kb(user_id)); utils.remember_owner(msg, user_id); return
    if data.startswith("prop:select:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        summary = await db.get_assets_summary(user_id); count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await utils.safe_answer(query, "❌ محدودیت!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < prop["price"]: await utils.safe_answer(query, "❌ موجودی!", show_alert=True); return
        new_total = (count + 1) * prop['income']
        text = f"🏠 <b>تایید خرید</b>\n━━━━━━━━━━━━━━━━━━\n{prop['emoji']} <b>{prop['name']}</b>\n💰 {utils.fmt(prop['price'])}\n📈 سود هر عدد: {utils.fmt(prop['income'])}\n📊 تعداد: {count}/{config.MAX_PER_KEY}\n💰 سود کل بعد: {utils.fmt(new_total)}\n\nمطمئنی؟"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ بخر", callback_data=f"prop:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="prop:menu")]])
        msg = await utils.safe_edit(query, text, kb); utils.remember_owner(msg, user_id); return
    if data.startswith("prop:confirm:"):
        key = data.split(":")[2]; prop = config.PROPERTIES.get(key)
        if not prop: return
        r = await db.buy_asset(user_id, "property", key, prop["price"], prop["income"])
        if r == "ok":
            await utils.safe_answer(query, f"✅ خریداری شد!", show_alert=True)
            result = await db.progress_mission(user_id, "buy_property", 1, base_xp=config.BASE_XP_BUY_ASSET)
            await utils.notify_mission(context, query.message.chat_id, result)
        elif r == "limit": await utils.safe_answer(query, "❌ محدودیت!", show_alert=True)
        elif r == "balance": await utils.safe_answer(query, "❌ موجودی!", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "property") + "\n\n👇 انتخاب کن:", await properties_menu_kb(user_id)); utils.remember_owner(msg, user_id); return

    if data == "worker:menu":
        await db.ensure_user(query.from_user)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇 انتخاب کن:", await workers_menu_kb(user_id)); utils.remember_owner(msg, user_id); return
    if data.startswith("worker:select:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        summary = await db.get_assets_summary(user_id); count = summary.get(key, {}).get("count", 0)
        if count >= config.MAX_PER_KEY: await utils.safe_answer(query, "❌ محدودیت!", show_alert=True); return
        user = await db.get_user(user_id)
        if int(user["balance"]) < w["price"]: await utils.safe_answer(query, "❌ موجودی!", show_alert=True); return
        new_total = (count + 1) * w['income']
        text = f"👷 <b>تایید استخدام</b>\n━━━━━━━━━━━━━━━━━━\n{w['emoji']} <b>{w['name']}</b>\n💰 {utils.fmt(w['price'])}\n📈 سود هر عدد: {utils.fmt(w['income'])}\n📊 تعداد: {count}/{config.MAX_PER_KEY}\n💰 سود کل بعد: {utils.fmt(new_total)}\n\nمطمئنی؟"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ استخدام", callback_data=f"worker:confirm:{key}")], [InlineKeyboardButton("❌ انصراف", callback_data="worker:menu")]])
        msg = await utils.safe_edit(query, text, kb); utils.remember_owner(msg, user_id); return
    if data.startswith("worker:confirm:"):
        key = data.split(":")[2]; w = config.WORKERS.get(key)
        if not w: return
        r = await db.buy_asset(user_id, "worker", key, w["price"], w["income"])
        if r == "ok":
            await utils.safe_answer(query, f"✅ استخدام شد!", show_alert=True)
            result = await db.progress_mission(user_id, "buy_worker", 1, base_xp=config.BASE_XP_BUY_ASSET)
            await utils.notify_mission(context, query.message.chat_id, result)
        elif r == "limit": await utils.safe_answer(query, "❌ محدودیت!", show_alert=True)
        elif r == "balance": await utils.safe_answer(query, "❌ موجودی!", show_alert=True)
        msg = await utils.safe_edit(query, await build_assets_text(user_id, "worker") + "\n\n👇 انتخاب کن:", await workers_menu_kb(user_id)); utils.remember_owner(msg, user_id); return

    if data == "game:menu":
        msg = await utils.safe_edit(query, "🎮 <b>بازی‌ها</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل: <b>1,000</b>\n💵 کارمزد: <b>10%</b>\n\nیکی رو انتخاب کن:", utils.GAMES_MENU_KB); utils.remember_owner(msg, user_id); return
    if data == "game:casino":
        msg = await utils.safe_edit(query, "🎰 <b>کازینو</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل: <b>10,000</b>\n💵 کارمزد: <b>10%</b>\n\nیکی رو انتخاب کن:", casino.casino_menu_kb()); utils.remember_owner(msg, user_id); return
    if data.startswith("game:") and data.count(":") == 1:
        gk = data.split(":", 1)[1]
        if gk in config.GAMES:
            g = config.GAMES[gk]
            utils.user_states[user_id] = {"action": "game_entry", "game": gk}
            msg = await utils.safe_edit(query, f"{g['emoji']} <b>{g['name']}</b>\n━━━━━━━━━━━━━━━━━━\n💰 حداقل: <b>{utils.fmt(g['min'])}</b>\n👥 بازیکنان: {g['players']}\n💵 کارمزد: <b>10%</b>\n\nمبلغ ورودی:", utils.BACK_GAMES_KB); utils.remember_owner(msg, user_id)
        return

    if data == "help:menu":
        msg = await utils.safe_edit(query, config.HELP_TEXT, utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if data == "transfer:start":
        utils.user_states[user_id] = {"action": "transfer_amount"}
        msg = await utils.safe_edit(query, "💸 <b>انتقال</b>\n\nمبلغ:", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return
    if data.startswith("tr:c:"):
        await confirm_transfer(query, int(data.split(":")[2])); return
    if data.startswith("tr:x:"):
        utils.pending_transfers.pop(user_id, None)
        msg = await utils.safe_edit(query, "❌ لغو شد.", utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

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
        await update.message.reply_text(f"⚠️ بازی لغو شد و {utils.fmt(pending['entry'])} برگشت."); return

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
            await update.message.reply_text(f"✅ <b>{utils.fmt(amount)}</b> {'واریز' if action == 'bank_deposit' else 'برداشت'} شد.", parse_mode=ParseMode.HTML, reply_markup=utils.MAIN_MENU_KB)
            if action == "bank_deposit":
                base = (amount // 10000) * config.BASE_XP_DEPOSIT_10K
                result = await db.progress_mission(user_id, "deposit_bank", amount, base_xp=min(base, 500))
                await utils.notify_mission(context, update.message.chat_id, result)
        else: await update.message.reply_text("❌ موجودی کافی نیست", reply_markup=utils.MAIN_MENU_KB)
        return

    if action == "game_entry":
        gk = state["game"]
        g = config.GAMES.get(gk)
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
        cg = state["game"]
        g = config.CASINO_GAMES.get(cg)
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
                msg = await update.message.reply_text(f"🎲 <b>تاس</b>\n💰 {utils.fmt(amount)}\n\n⚠️ اگر ببازی پولت برنمی‌گرده.\n\nانتخاب:", parse_mode=ParseMode.HTML, reply_markup=casino.casino_dice_kb()); utils.remember_owner(msg, user_id)
            elif cg == "coin":
                msg = await update.message.reply_text(f"🪙 <b>شیر یا خط</b>\n💰 {utils.fmt(amount)}\n\nانتخاب:", parse_mode=ParseMode.HTML, reply_markup=casino.casino_coin_kb()); utils.remember_owner(msg, user_id)
            elif cg == "card":
                msg = await update.message.reply_text(f"🃏 <b>کارت</b>\n💰 {utils.fmt(amount)}\n\nکدام خال؟", parse_mode=ParseMode.HTML, reply_markup=casino.casino_card_kb()); utils.remember_owner(msg, user_id)
        return

    if action == "transfer_amount":
        amount = utils.parse_amount(text)
        if not amount: await update.message.reply_text("❌ مبلغ نامعتبر"); return
        fee = int(amount * config.TRANSFER_FEE_RATE) if amount > config.TRANSFER_FEE_MIN else 0
        total = amount + fee
        u = await db.get_user(user_id)
        if int(u["balance"]) < total: await update.message.reply_text(f"❌ نیاز: {utils.fmt(total)}"); return
        utils.user_states[user_id] = {"action": "transfer_card", "amount": amount, "fee": fee}
        msg = await update.message.reply_text(f"💸 مبلغ: <b>{utils.fmt(amount)}</b>\n💵 کارمزد: {utils.fmt(fee)}\n\nکارت مقصد:", parse_mode=ParseMode.HTML, reply_markup=utils.BACK_MAIN_KB); utils.remember_owner(msg, user_id); return

    if action == "transfer_card":
        recipient = await db.find_user_by_card(text)
        if not recipient: await update.message.reply_text("❌ کاربر پیدا نشد"); return
        if recipient["user_id"] == user_id: await update.message.reply_text("❌ به خودت نمی‌تونی"); return
        amount, fee = state["amount"], state["fee"]
        utils.pending_transfers[user_id] = {"recipient_id": recipient["user_id"], "recipient_name": recipient["first_name"] or str(recipient["user_id"]), "amount": amount, "fee": fee}
        utils.user_states.pop(user_id, None)
        msg = await update.message.reply_text(f"💸 <b>تایید انتقال</b>\n━━━━━━━━━━━━━━━━━━\n👤 {utils.escape(recipient['first_name'])}\n💰 {utils.fmt(amount)}\n💵 کارمزد: {utils.fmt(fee)}\n\nتایید؟", parse_mode=ParseMode.HTML, reply_markup=utils.transfer_confirm_kb(user_id)); utils.remember_owner(msg, user_id); return

async def handle_cancel(user_id: int, message):
    sess = utils.casino_pending.pop(user_id, None)
    if sess: await db.add_balance(user_id, sess["entry"]); await message.reply_text(f"❌ لغو شد. {utils.fmt(sess['entry'])} برگشت."); return
    pen = utils.penalty_games.pop(user_id, None)
    if pen: await db.add_balance(user_id, pen["entry"]); await message.reply_text(f"❌ لغو شد. {utils.fmt(pen['entry'])} برگشت."); return
    rid = utils.find_user_room(user_id)
    if rid:
        room = utils.rooms.get(rid)
        if room and room["status"] != "finished":
            for pid in room["players"]: await db.add_balance(pid, room["entry"])
            entry = room["entry"]; room["status"] = "cancelled"; utils.rooms.pop(rid, None)
            await message.reply_text(f"❌ لغو شد. {utils.fmt(entry)} به هر بازیکن برگشت."); return
    if user_id in utils.user_states: utils.user_states.pop(user_id, None); await message.reply_text("❌ عملیات لغو شد."); return
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
    if not pending: await utils.safe_answer(query, "❌ منقضی شد", show_alert=True); return
    if not await db.transfer_coins(owner_id, pending["recipient_id"], pending["amount"], pending["fee"]):
        await utils.safe_answer(query, "❌ موجودی کافی نیست", show_alert=True); await utils.safe_edit(query, "❌ انجام نشد.", utils.BACK_MAIN_KB); return
    await utils.safe_edit(query, f"✅ <b>انتقال انجام شد!</b>\n\n👤 {utils.escape(pending['recipient_name'])}\n💰 {utils.fmt(pending['amount'])}\n💵 کارمزد: {utils.fmt(pending['fee'])}", utils.BACK_MAIN_KB)
    await utils.safe_answer(query)
    try: await query.bot.send_message(pending["recipient_id"], f"🎁 <b>زرکوین!</b>\n\n💰 {utils.fmt(pending['amount'])}\n👤 از طرف: {utils.escape(query.from_user.first_name)}", parse_mode=ParseMode.HTML)
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
    if not amount: await msg.reply_text("❌ مبلغ نامعتبر"); return
    target = msg.reply_to_message.from_user
    if target.is_bot: await msg.reply_text("❌ به بات نمی‌شه"); return
    await db.ensure_user(target); await db.add_balance(target.id, amount)
    await msg.reply_text(f"✅ {utils.fmt(amount)} به {utils.escape(target.first_name)} واریز شد.", parse_mode=ParseMode.HTML)

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if not cm or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"): return
    if cm.new_chat_member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and cm.old_chat_member.status in (ChatMember.LEFT, ChatMember.KICKED):
        try: await context.bot.send_message(update.effective_chat.id, "✨ <b>زرکوین بات فعال شد!</b> ✨\n\n💡 <code>زربات</code> | <code>زر بازی</code> | <code>زر</code>", parse_mode=ParseMode.HTML)
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
    app.add_handler(MessageHandler(filters.Regex(r"^زر$"), cmd_zar))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.Regex(r"^انتقال زرکوین\s+[\d۰-۹,،]+"), owner_give))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("🚀 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
