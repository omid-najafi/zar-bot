from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

def kb(room_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✊ سنگ", callback_data=f"rps:c:{room_id}:rock"),
        InlineKeyboardButton("✋ کاغذ", callback_data=f"rps:c:{room_id}:paper"),
        InlineKeyboardButton("✌️ قیچی", callback_data=f"rps:c:{room_id}:scissors"),
    ]])

async def create_room(update, user, amount):
    rid = utils.new_room_id()
    utils.rooms[rid] = {
        "id": rid, "game": "rps", "entry": amount, "creator": user.id,
        "players": [user.id], "status": "waiting",
        "user_names": {user.id: user.first_name or str(user.id)},
        "chat_id": update.effective_chat.id, "created_at": utils.now_iso(),
    }
    text = f"✊ <b>سنگ کاغذ قیچی</b>\n━━━━━━━━━━━━━━━━━━\n💰 ورودی: <b>{utils.fmt(amount)}</b>\n\n👤 بازیکن ۱: {utils.escape(user.first_name)}\n\n⏳ منتظر بازیکن دوم..."
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=utils.join_room_kb(rid, "rps"))
    utils.remember_owner(msg, user.id)

async def handle_callback(query, context, data, user_id):
    parts = data.split(":")
    action = parts[1]
    room_id = parts[2]
    
    if action == "join":
        room = utils.rooms.get(room_id)
        if not room or room["status"] != "waiting" or user_id in room["players"]:
            await utils.safe_answer(query, "❌ نمی‌تونی وارد بشی", show_alert=True); return
        if utils.find_user_room(user_id):
            await utils.safe_answer(query, "⚠️ در بازی دیگر فعالی", show_alert=True); return
            
        await db.ensure_user(query.from_user)
        if not await db.deduct_balance(user_id, room["entry"]):
            await utils.safe_answer(query, "❌ موجودی کافی نیست", show_alert=True); return
            
        room["players"].append(user_id)
        room["user_names"][user_id] = query.from_user.first_name or str(user_id)
        room["status"] = "playing"
        room["choices"] = {}
        
        text = (f"✊ <b>سنگ کاغذ قیچی</b>\n💰 ورودی: {utils.fmt(room['entry'])}\n\n"
                f"👤 بازیکن ۱: {utils.escape(room['user_names'][room['players'][0]])}\n"
                f"👤 بازیکن ۲: {utils.escape(room['user_names'][room['players'][1]])}\n\nهر دو یک گزینه بزنید:")
        msg = await utils.safe_edit(query, text, kb(room_id))
        utils.remember_owner(msg, room["players"][0])
        await utils.safe_answer(query)
        
    elif action == "c":
        choice = parts[3]
        room = utils.rooms.get(room_id)
        if not room or room["status"] != "playing" or user_id not in room["players"]:
            await utils.safe_answer(query, "❌ بازی فعال نیست", show_alert=True); return
        if user_id in room["choices"]:
            await utils.safe_answer(query, "✅ قبلاً انتخاب کردی", show_alert=True); return
            
        room["choices"][user_id] = choice
        if len(room["choices"]) < 2:
            await utils.safe_answer(query, "✅ ثبت شد، منتظر حریف...", show_alert=True)
            return
            
        names = {"rock": "سنگ ✊", "paper": "کاغذ ✋", "scissors": "قیچی ✌️"}
        p1, p2 = room["players"]
        c1, c2 = room["choices"][p1], room["choices"][p2]
        beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        winner_id = None
        
        if c1 == c2:
            await db.add_balance(p1, room["entry"]); await db.add_balance(p2, room["entry"])
            result = "🤝 مساوی! پول‌ها برگشت."
        else:
            winner_id = p1 if beats[c1] == c2 else p2
            full = int(room["entry"] * config.GAMES["rps"]["mult"])
            prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
            await db.add_balance(winner_id, prize)
            result = f"🏆 <b>{utils.escape(room['user_names'][winner_id])}</b> برنده شد!\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b>"
            
        text = (f"✊ <b>نتیجه سنگ کاغذ قیچی</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"👤 {utils.escape(room['user_names'][p1])}: {names[c1]}\n"
                f"👤 {utils.escape(room['user_names'][p2])}: {names[c2]}\n\n{result}")
        room["status"] = "finished"; utils.rooms.pop(room_id, None)
        await utils.safe_edit(query, text, utils.BACK_GAMES_KB)
        await utils.safe_answer(query)
        
        # ✅ ثبت ماموریت‌ها
        r_p1 = await db.progress_mission(p1, "play_rps", 1, base_xp=config.BASE_XP_PLAY_GAME)
        r_p2 = await db.progress_mission(p2, "play_rps", 1, base_xp=config.BASE_XP_PLAY_GAME)
        await utils.notify_mission(context, room["chat_id"], r_p1)
        await utils.notify_mission(context, room["chat_id"], r_p2)
        
        r_any_p1 = await db.progress_mission(p1, "play_any_game", 1, base_xp=0)
        r_any_p2 = await db.progress_mission(p2, "play_any_game", 1, base_xp=0)
        await utils.notify_mission(context, room["chat_id"], r_any_p1)
        await utils.notify_mission(context, room["chat_id"], r_any_p2)
        
        if winner_id:
            r_win = await db.progress_mission(winner_id, "win_rps", 1, base_xp=config.BASE_XP_WIN_GAME)
            await utils.notify_mission(context, room["chat_id"], r_win)
