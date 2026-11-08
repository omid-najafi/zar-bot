import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

QUIZ_QUESTIONS = [
    {"q": "بنیان‌گذار سلسله هخامنشیان کیست؟", "opts": ["کوروش کبیر", "داریوش", "خشایارشا", "اردشیر"], "ans": 0},
    {"q": "تخت جمشید در کدام استان است؟", "opts": ["فارس", "خوزستان", "کرمان", "یزد"], "ans": 0},
    {"q": "پایتخت ایران کجاست؟", "opts": ["تهران", "اصفهان", "شیراز", "مشهد"], "ans": 0},
    {"q": "بزرگ‌ترین سیاره منظومه شمسی؟", "opts": ["مشتری", "زحل", "زمین", "نپتون"], "ans": 0},
    {"q": "نماد شیمیایی طلا چیست؟", "opts": ["Au", "Ag", "Pt", "Cu"], "ans": 0},
    # ... می‌تونی بقیه 300 سوال رو همینجا به لیست اضافه کنی ...
]

def get_random_q():
    if random.random() < 0.8:
        return random.choice(QUIZ_QUESTIONS)
    
    kind = random.choice(["add", "sub", "mul"])
    if kind == "add":
        a, b = random.randint(10, 999), random.randint(10, 999)
        ans = a + b; q = f"{a} + {b} = ?"
    elif kind == "sub":
        a, b = random.randint(50, 999), random.randint(1, 49)
        ans = a - b; q = f"{a} - {b} = ?"
    else:
        a, b = random.randint(2, 20), random.randint(2, 20)
        ans = a * b; q = f"{a} × {b} = ?"
    wrongs = set()
    while len(wrongs) < 3:
        w = ans + random.choice([-3,-2,-1,1,2,3,4])
        if w > 0 and w != ans: wrongs.add(w)
    opts = [ans] + list(wrongs)
    random.shuffle(opts)
    return {"q": q, "opts": [str(x) for x in opts], "ans": opts.index(ans)}

def kb(room_id, opts):
    return InlineKeyboardMarkup([[InlineKeyboardButton(o, callback_data=f"quiz:a:{room_id}:{i}")] for i, o in enumerate(opts)])

async def create_room(update, user, amount):
    rid = utils.new_room_id()
    utils.rooms[rid] = {
        "id": rid, "game": "quiz", "entry": amount, "creator": user.id,
        "players": [user.id], "status": "waiting",
        "user_names": {user.id: user.first_name or str(user.id)},
        "chat_id": update.effective_chat.id, "created_at": utils.now_iso(),
    }
    text = f"🧠 <b>کوییز</b>\n━━━━━━━━━━━━━━━━━━\n💰 ورودی: <b>{utils.fmt(amount)}</b>\n\n👤 بازیکن ۱: {utils.escape(user.first_name)}\n\n⏳ منتظر بازیکن دوم..."
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=utils.join_room_kb(rid, "quiz"))
    utils.remember_owner(msg, user.id)

async def handle_callback(query, context, data, user_id):
    parts = data.split(":")
    action = parts[1]
    room_id = parts[2]
    
    if action == "join":
        room = utils.rooms.get(room_id)
        if not room or room["status"] != "waiting" or user_id in room["players"]:
            await query.answer("❌ نمی‌تونی وارد بشی", show_alert=True); return
        if utils.find_user_room(user_id):
            await query.answer("⚠️ در بازی دیگر فعالی", show_alert=True); return
            
        await db.ensure_user(query.from_user)
        if not await db.deduct_balance(user_id, room["entry"]):
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
            
        room["players"].append(user_id)
        room["user_names"][user_id] = query.from_user.first_name or str(user_id)
        room["status"] = "playing"
        q = get_random_q()
        room["question"] = q
        room["answered"] = False
        
        text = f"🧠 <b>کوییز</b>\n💰 ورودی: {utils.fmt(room['entry'])}\n\n❓ <b>{utils.escape(q['q'])}</b>\n\nاولین کسی که درست جواب بده برنده‌ست:"
        msg = await utils.safe_edit(query, text, kb(room_id, q["opts"]))
        utils.remember_owner(msg, room["players"][0])
        await query.answer()
        
    elif action == "a":
        idx = int(parts[3])
        room = utils.rooms.get(room_id)
        if not room or room["status"] != "playing" or room.get("answered"): 
            await query.answer("❌ تمام شده", show_alert=True); return
            
        q = room["question"]
        if idx == q["ans"]:
            room["answered"] = True
            full = int(room["entry"] * config.GAMES["quiz"]["mult"])
            prize, comm = utils.apply_commission(full, config.COMMISSION_RATE)
            await db.add_balance(user_id, prize)
            room["status"] = "finished"; utils.rooms.pop(room_id, None)
            
            text = f"🧠 <b>نتیجه کوییز</b>\n❓ {utils.escape(q['q'])}\n\n🏆 برنده: <b>{utils.escape(query.from_user.first_name)}</b>\n💰 جایزه: {utils.fmt(full)}\n💵 کارمزد 10%: {utils.fmt(comm)}\n✅ دریافتی: <b>{utils.fmt(prize)}</b>"
            await utils.safe_edit(query, text, utils.back_games_kb())
        else:
            await query.answer("❌ اشتباه! دوباره تلاش کن", show_alert=True)
