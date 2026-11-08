from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

def ttt_check_win(board):
    lines = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]: return board[a]
    if all(board): return "draw"
    return None

def kb(room):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            v = room["board"][i]
            if v == "X": row.append(InlineKeyboardButton("❌", callback_data="ttt:noop"))
            elif v == "O": row.append(InlineKeyboardButton("⭕", callback_data="ttt:noop"))
            else: row.append(InlineKeyboardButton("⬜", callback_data=f"ttt:m:{room['id']}:{i}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def render(query, room):
    p1, p2 = room["players"]
    turn = room["turn"]
    text = (f"❌ <b>دوز</b>\n💰 ورودی: {utils.fmt(room['entry'])}\n\n"
            f"👤 {utils.escape(room['user_names'][p1])} ❌\n"
            f"👤 {utils.escape(room['user_names'][p2])} ⭕\n\n"
            f"🎯 نوبت: <b>{utils.escape(room['user_names'][turn])}</b>")
    msg = await utils.safe_edit(query, text, kb(room))
    utils.remember_owner(msg, p1)

async def create_room(update, user, amount):
    rid = utils.new_room_id()
    utils.rooms[rid] = {
        "id": rid, "game": "ttt", "entry": amount, "creator": user.id,
        "players": [user.id], "status": "waiting",
        "user_names": {user.id: user.first_name or str(user.id)},
        "chat_id": update.effective_chat.id, "created_at": utils.now_iso(),
    }
    text = f"❌ <b>دوز</b>\n━━━━━━━━━━━━━━━━━━\n💰 ورودی: <b>{utils.fmt(amount)}</b>\n\n👤 بازیکن ۱: {utils.escape(user.first_name)}\n\n⏳ منتظر بازیکن دوم..."
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=utils.join_room_kb(rid, "ttt"))
    utils.remember_owner(msg, user.id)

async def handle_callback(query, context, data, user_id):
    parts = data.split(":")
    action = parts[1]
    
    if action == "noop":
        await utils.safe_answer(query); return
        
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
        room["board"] = [""] * 9
        room["turn"] = room["players"][0]
        room["symbols"] = {room["players"][0]: "X", room["players"][1]: "O"}
        await render(query, room)
        await utils.safe_answer(query)
        
    elif action == "m":
        idx = int(parts[3])
        room = utils.rooms.get(room_id)
        if not room or room["status"] != "playing":
            await utils.safe_answer(query, "❌ بازی فعال نیست", show_alert=True); return
        if user_id != room["turn"]:
            await utils.safe_answer(query, "⏳ نوبت تو نیست", show_alert=True); return
        if room["board"][idx]:
            await utils.safe_answer(query, "❌ خانه پر است", show_alert=True); return
            
        p1, p2 = room["players"]
        room["board"][idx] = room["symbols"][user_id]
        winner = ttt_check_win(room["board"])
        
        if winner:
            if winner == "draw":
                await db.add_balance(p1, room["entry"]); await db.add_balance(p2, room["entry"])
                text = "🤝 <b>مساوی!</b> پول‌ها برگشت."
            else:
                w_id = p1 if winner == "X" else p2
                full = int(room["entry"] * config.GAMES["ttt"]["mult"])
                prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
                await db.add_balance(w_id, prize)
                text = f"🏆 <b>{utils.escape(room['user_names'][w_id])}</b> برنده شد!\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b>"
            room["status"] = "finished"; utils.rooms.pop(room_id, None)
            await utils.safe_edit(query, text, utils.BACK_GAMES_KB)
            await utils.safe_answer(query)
            return
            
        room["turn"] = p2 if room["turn"] == p1 else p1
        await render(query, room)
        await utils.safe_answer(query)
