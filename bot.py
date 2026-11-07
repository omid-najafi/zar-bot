# -*- coding: utf-8 -*-
"""ربات زرکوین (بات زر) - نسخه نهایی با کازینو و تاس اصلاح‌شده"""
import asyncio
import html
import logging
import os
import random
import re
import secrets
import string
from datetime import datetime, time
from zoneinfo import ZoneInfo

import aiomysql
from telegram import (
    ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

# ============================== تنظیمات ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
START_BALANCE = int(os.getenv("START_BALANCE", "0").strip() or "0")
TEHRAN = ZoneInfo("Asia/Tehran")

DB_HOST = os.getenv("MYSQLHOST", "localhost")
DB_PORT = int(os.getenv("MYSQLPORT", "3306") or "3306")
DB_USER = os.getenv("MYSQLUSER", "root")
DB_PASSWORD = os.getenv("MYSQLPASSWORD", "")
DB_NAME = os.getenv("MYSQLDATABASE", "railway")

db_pool: aiomysql.Pool | None = None

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("zarcoin")

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

BANK_RATE = 0.02
MAX_ASSETS = 5
TRANSFER_FEE_RATE = 0.01
TRANSFER_FEE_MIN = 1_000_000
COMMISSION_RATE = 0.10

PROPERTIES = {
    "supermarket": {"name": "سوپرمارکت", "price": 500_000, "income": 50_000, "emoji": "🛒"},
    "fruit":       {"name": "میوه‌فروشی", "price": 800_000, "income": 80_000, "emoji": "🍎"},
    "butcher":     {"name": "قصابی", "price": 1_000_000, "income": 100_000, "emoji": "🥩"},
    "pharmacy":    {"name": "داروخانه", "price": 1_800_000, "income": 180_000, "emoji": "💊"},
    "barber":      {"name": "آرایشگاه", "price": 2_200_000, "income": 220_000, "emoji": "💈"},
    "clothing":    {"name": "فروشگاه پوشاک", "price": 3_000_000, "income": 300_000, "emoji": "👕"},
    "bookstore":   {"name": "کتاب‌فروشی", "price": 3_500_000, "income": 350_000, "emoji": "📚"},
    "mobile":      {"name": "موبایل‌فروشی", "price": 4_000_000, "income": 400_000, "emoji": "📱"},
}

WORKERS = {
    "teacher":   {"name": "معلم", "price": 300_000, "income": 30_000, "emoji": "👨‍🏫"},
    "doctor":    {"name": "پزشک", "price": 500_000, "income": 50_000, "emoji": "👨‍⚕️"},
    "driver":    {"name": "راننده", "price": 800_000, "income": 80_000, "emoji": "🚕"},
    "developer": {"name": "برنامه‌نویس", "price": 1_200_000, "income": 120_000, "emoji": "👨‍💻"},
    "ai_expert": {"name": "متخصص هوش مصنوعی", "price": 2_000_000, "income": 200_000, "emoji": "🤖"},
}

GAMES = {
    "rps":     {"name": "سنگ کاغذ قیچی", "emoji": "✊", "min": 1000, "players": 2, "mult": 1.5},
    "ttt":     {"name": "دوز", "emoji": "❌", "min": 1000, "players": 2, "mult": 1.7},
    "quiz":    {"name": "کوییز", "emoji": "🧠", "min": 1000, "players": 2, "mult": 1.8},
    "penalty": {"name": "پنالتی", "emoji": "⚽", "min": 1000, "players": 1, "mult": 2.0},
}

CASINO_GAMES = {
    "slots": {"name": "اسلات", "emoji": "🎰", "min": 10_000},
    "dice":  {"name": "تاس", "emoji": "🎲", "min": 10_000},
    "coin":  {"name": "شیر یا خط", "emoji": "🪙", "min": 10_000},
    "card":  {"name": "کارت شانس", "emoji": "🃏", "min": 10_000},
}

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "7️⃣", "⭐"]
CARD_SUITS = {"hearts": "♥️", "diamonds": "♦️", "spades": "♠️", "clubs": "♣️"}
CARD_SUITS_FA = {"hearts": "دل", "diamonds": "خشت", "spades": "پیک", "clubs": "گشنیز"}
DICE_EMOJIS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}

# ============================== بانک سوالات کوییز ==============================
QUIZ_QUESTIONS = [
    {"q": "بنیان‌گذار سلسله هخامنشیان کیست؟", "opts": ["کوروش کبیر", "داریوش", "خشایارشا", "اردشیر"], "ans": 0},
    {"q": "تخت جمشید در کدام استان است؟", "opts": ["فارس", "خوزستان", "کرمان", "یزد"], "ans": 0},
    {"q": "آخرین پادشاه هخامنشی کیست؟", "opts": ["داریوش سوم", "خشایارشا", "اردشیر", "کوروش"], "ans": 0},
    {"q": "بنیان‌گذار سلسله ساسانیان کیست؟", "opts": ["اردشیر بابکان", "شاپور", "یزدگرد", "انوشیروان"], "ans": 0},
    {"q": "اولین پادشاه صفویه کیست؟", "opts": ["شاه اسماعیل اول", "شاه عباس اول", "شاه طهماسب", "شاه سلطان حسین"], "ans": 0},
    {"q": "پایتخت صفویان در اوج قدرت کجا بود؟", "opts": ["اصفهان", "تبریز", "قزوین", "شیراز"], "ans": 0},
    {"q": "بنیان‌گذار سلسله افشاریه کیست؟", "opts": ["نادرشاه", "کریم‌خان", "آغامحمدخان", "شاه سلطان حسین"], "ans": 0},
    {"q": "پایتخت کریم‌خان زند کجا بود؟", "opts": ["شیراز", "تهران", "اصفهان", "کرمان"], "ans": 0},
    {"q": "آخرین پادشاه قاجار کیست؟", "opts": ["احمدشاه", "مظفرالدین‌شاه", "محمدعلی‌شاه", "رضاشاه"], "ans": 0},
    {"q": "انقلاب مشروطه در چه سالی رخ داد؟", "opts": ["۱۲۸۵ شمسی", "۱۲۹۰ شمسی", "۱۲۷۵ شمسی", "۱۳۰۰ شمسی"], "ans": 0},
    {"q": "ملی شدن صنعت نفت ایران در چه سالی رخ داد؟", "opts": ["۱۳۲۹ شمسی", "۱۳۲۵ شمسی", "۱۳۳۵ شمسی", "۱۳۴۰ شمسی"], "ans": 0},
    {"q": "رهبر نهضت ملی شدن نفت ایران چه کسی بود؟", "opts": ["دکتر مصدق", "دکتر فاطمی", "آیت‌الله کاشانی", "رضاشاه"], "ans": 0},
    {"q": "جنگ ایران و عراق چند سال طول کشید؟", "opts": ["۸ سال", "۶ سال", "۱۰ سال", "۵ سال"], "ans": 0},
    {"q": "کتیبه بیستون متعلق به کدام پادشاه است؟", "opts": ["داریوش اول", "کوروش", "خشایارشا", "اردشیر"], "ans": 0},
    {"q": "جنگ جهانی اول در چه سالی آغاز شد؟", "opts": ["۱۹۱۴", "۱۹۱۸", "۱۹۳۹", "۱۹۲۰"], "ans": 0},
    {"q": "جنگ جهانی دوم در چه سالی پایان یافت؟", "opts": ["۱۹۴۵", "۱۹۴۴", "۱۹۴۶", "۱۹۴۳"], "ans": 0},
    {"q": "انقلاب کبیر فرانسه در چه سالی رخ داد؟", "opts": ["۱۷۸۹", "۱۷۷۶", "۱۸۰۰", "۱۸۱۵"], "ans": 0},
    {"q": "دیوار برلین در چه سالی فروپاشید؟", "opts": ["۱۹۸۹", "۱۹۹۱", "۱۹۸۵", "۱۹۹۳"], "ans": 0},
    {"q": "اولین انسان روی ماه چه کسی بود؟", "opts": ["نیل آرمسترانگ", "یوری گاگارین", "باز آلدرین", "مایکل کالینز"], "ans": 0},
    {"q": "اولین انسان در فضا چه کسی بود؟", "opts": ["یوری گاگارین", "نیل آرمسترانگ", "جان گلن", "آلن شپرد"], "ans": 0},
    {"q": "جنگ سرد بین کدام دو کشور بود؟", "opts": ["آمریکا و شوروی", "آمریکا و چین", "آلمان و فرانسه", "انگلیس و آلمان"], "ans": 0},
    {"q": "فروپاشی اتحاد جماهیر شوروی در چه سالی رخ داد؟", "opts": ["۱۹۹۱", "۱۹۸۹", "۱۹۹۳", "۱۹۸۵"], "ans": 0},
    {"q": "کشف آمریکا توسط کریستف کلمب در چه سالی بود؟", "opts": ["۱۴۹۲", "۱۴۵۰", "۱۵۰۰", "۱۴۸۰"], "ans": 0},
    {"q": "کدام تمدن باستانی اهرام ثلاثه را ساخت؟", "opts": ["مصر", "بابل", "یونان", "روم"], "ans": 0},
    {"q": "قانون حمورابی متعلق به کدام تمدن است؟", "opts": ["بابل", "مصر", "یونان", "ایران"], "ans": 0},
    {"q": "انقلاب صنعتی ابتدا در کدام کشور آغاز شد؟", "opts": ["انگلستان", "آمریکا", "آلمان", "فرانسه"], "ans": 0},
    {"q": "چه کسی اولین رئیس‌جمهور آمریکا بود؟", "opts": ["جورج واشنگتن", "آبراهام لینکلن", "توماس جفرسون", "جان آدامز"], "ans": 0},
    {"q": "پایتخت ایران کجاست؟", "opts": ["تهران", "اصفهان", "شیراز", "مشهد"], "ans": 0},
    {"q": "بزرگ‌ترین دریاچه ایران کدام است؟", "opts": ["دریاچه ارومیه", "دریاچه خزر", "دریاچه هامون", "دریاچه نمک"], "ans": 0},
    {"q": "بلندترین قله ایران کدام است؟", "opts": ["دماوند", "علم‌کوه", "زردکوه", "تفتان"], "ans": 0},
    {"q": "دماوند در کدام استان قرار دارد؟", "opts": ["مازندران", "تهران", "گیلان", "سمنان"], "ans": 0},
    {"q": "طولانی‌ترین رودخانه ایران کدام است؟", "opts": ["کارون", "سفیدرود", "ارس", "زاینده‌رود"], "ans": 0},
    {"q": "بزرگ‌ترین استان ایران از نظر مساحت کدام است؟", "opts": ["سیستان و بلوچستان", "کرمان", "فارس", "خراسان رضوی"], "ans": 0},
    {"q": "کوچک‌ترین استان ایران کدام است؟", "opts": ["البرز", "قم", "تهران", "گیلان"], "ans": 0},
    {"q": "شهر اصفهان در کنار کدام رود قرار دارد؟", "opts": ["زاینده‌رود", "کارون", "سفیدرود", "ارس"], "ans": 0},
    {"q": "بندرعباس مرکز کدام استان است؟", "opts": ["هرمزگان", "سیستان و بلوچستان", "بوشهر", "خوزستان"], "ans": 0},
    {"q": "کدام شهر به نصف جهان معروف است؟", "opts": ["اصفهان", "شیراز", "تبریز", "مشهد"], "ans": 0},
    {"q": "میدان نقش جهان در کدام شهر است؟", "opts": ["اصفهان", "شیراز", "تهران", "تبریز"], "ans": 0},
    {"q": "برج آزادی در کدام شهر است؟", "opts": ["تهران", "اصفهان", "شیراز", "مشهد"], "ans": 0},
    {"q": "حرم امام رضا در کدام شهر است؟", "opts": ["مشهد", "قم", "شیراز", "تهران"], "ans": 0},
    {"q": "حرم حضرت معصومه در کدام شهر است؟", "opts": ["قم", "مشهد", "شیراز", "تهران"], "ans": 0},
    {"q": "پایتخت فرانسه کجاست؟", "opts": ["پاریس", "لندن", "برلین", "مادرید"], "ans": 0},
    {"q": "پایتخت آلمان کجاست؟", "opts": ["برلین", "مونیخ", "هامبورگ", "فرانکفورت"], "ans": 0},
    {"q": "پایتخت انگلستان کجاست؟", "opts": ["لندن", "منچستر", "لیورپول", "بیرمنگام"], "ans": 0},
    {"q": "پایتخت ایتالیا کجاست؟", "opts": ["رم", "میلان", "ونیز", "ناپل"], "ans": 0},
    {"q": "پایتخت اسپانیا کجاست؟", "opts": ["مادرید", "بارسلونا", "سویا", "والنسیا"], "ans": 0},
    {"q": "پایتخت روسیه کجاست؟", "opts": ["مسکو", "سن‌پترزبورگ", "کی‌یف", "نووسیبیرسک"], "ans": 0},
    {"q": "پایتخت چین کجاست؟", "opts": ["پکن", "شانگهای", "هنگ‌کنگ", "گوانگژو"], "ans": 0},
    {"q": "پایتخت ژاپن کجاست؟", "opts": ["توکیو", "اوزاکا", "کیوتو", "هیروشیما"], "ans": 0},
    {"q": "پایتخت هند کجاست؟", "opts": ["دهلی نو", "بمبئی", "کلکته", "بنگلور"], "ans": 0},
    {"q": "پایتخت ترکیه کجاست؟", "opts": ["آنکارا", "استانبول", "ازمیر", "بورسا"], "ans": 0},
    {"q": "پایتخت عربستان سعودی کجاست؟", "opts": ["ریاض", "جده", "مکه", "مدینه"], "ans": 0},
    {"q": "پایتخت افغانستان کجاست؟", "opts": ["کابل", "هرات", "قندهار", "مزار شریف"], "ans": 0},
    {"q": "پایتخت پاکستان کجاست؟", "opts": ["اسلام‌آباد", "کراچی", "لاهور", "پیشاور"], "ans": 0},
    {"q": "پایتخت آذربایجان کجاست؟", "opts": ["باکو", "گنجه", "سومقاییت", "لنکران"], "ans": 0},
    {"q": "پایتخت ارمنستان کجاست؟", "opts": ["ایروان", "گیومری", "وانادزور", "آبویان"], "ans": 0},
    {"q": "پایتخت گرجستان کجاست؟", "opts": ["تفلیس", "باتومی", "کوتایسی", "سوخومی"], "ans": 0},
    {"q": "پایتخت آمریکا کجاست؟", "opts": ["واشنگتن", "نیویورک", "لس‌آنجلس", "شیکاگو"], "ans": 0},
    {"q": "پایتخت کانادا کجاست؟", "opts": ["اتاوا", "تورنتو", "مونترال", "ونکوور"], "ans": 0},
    {"q": "پایتخت استرالیا کجاست؟", "opts": ["کانبرا", "سیدنی", "ملبورن", "بریزبن"], "ans": 0},
    {"q": "پایتخت برزیل کجاست؟", "opts": ["برازیلیا", "ریودوژانیرو", "سائوپائولو", "سالوادور"], "ans": 0},
    {"q": "پایتخت مصر کجاست؟", "opts": ["قاهره", "اسکندریه", "جیزه", "اقصر"], "ans": 0},
    {"q": "بزرگ‌ترین اقیانوس جهان کدام است؟", "opts": ["آرام", "اطلس", "هند", "منجمد شمالی"], "ans": 0},
    {"q": "بزرگ‌ترین قاره جهان کدام است؟", "opts": ["آسیا", "آفریقا", "آمریکای شمالی", "اروپا"], "ans": 0},
    {"q": "بلندترین قله جهان کدام است؟", "opts": ["اورست", "K2", "کنچن‌جونگا", "دماوند"], "ans": 0},
    {"q": "طولانی‌ترین رود جهان کدام است؟", "opts": ["نیل", "آمازون", "می‌سی‌سی‌پی", "دانوب"], "ans": 0},
    {"q": "بزرگ‌ترین بیابان گرم جهان کدام است؟", "opts": ["صحرای آفریقا", "بیابان عربستان", "گبی", "کالاهاری"], "ans": 0},
    {"q": "بزرگ‌ترین کشور جهان از نظر مساحت کدام است؟", "opts": ["روسیه", "کانادا", "چین", "آمریکا"], "ans": 0},
    {"q": "کوچک‌ترین کشور جهان کدام است؟", "opts": ["واتیکان", "موناکو", "سان مارینو", "لیختن‌اشتاین"], "ans": 0},
    {"q": "واحد اندازه‌گیری نیرو چیست؟", "opts": ["نیوتن", "ژول", "وات", "پاسکال"], "ans": 0},
    {"q": "واحد اندازه‌گیری انرژی چیست؟", "opts": ["ژول", "نیوتن", "وات", "آمپر"], "ans": 0},
    {"q": "واحد اندازه‌گیری توان چیست؟", "opts": ["وات", "ژول", "نیوتن", "هرتز"], "ans": 0},
    {"q": "قانون جاذبه توسط چه کسی کشف شد؟", "opts": ["نیوتن", "انیشتین", "گالیله", "کپلر"], "ans": 0},
    {"q": "نسبیت توسط چه کسی مطرح شد؟", "opts": ["اینشتین", "نیوتن", "بور", "پلانک"], "ans": 0},
    {"q": "فرمول معروف E=mc² متعلق به کیست؟", "opts": ["اینشتین", "نیوتن", "گالیله", "کپلر"], "ans": 0},
    {"q": "نماد شیمیایی طلا چیست؟", "opts": ["Au", "Ag", "Pt", "Cu"], "ans": 0},
    {"q": "نماد شیمیایی نقره چیست؟", "opts": ["Ag", "Au", "Fe", "Zn"], "ans": 0},
    {"q": "نماد شیمیایی آهن چیست؟", "opts": ["Fe", "Ir", "In", "Fr"], "ans": 0},
    {"q": "نماد شیمیایی سدیم چیست؟", "opts": ["Na", "Sd", "So", "Sm"], "ans": 0},
    {"q": "نماد شیمیایی پتاسیم چیست؟", "opts": ["K", "P", "Pt", "Ka"], "ans": 0},
    {"q": "فرمول شیمیایی آب چیست؟", "opts": ["H₂O", "CO₂", "O₂", "H₂O₂"], "ans": 0},
    {"q": "فرمول شیمیایی نمک خوراکی چیست؟", "opts": ["NaCl", "KCl", "CaCO₃", "NaOH"], "ans": 0},
    {"q": "فراوان‌ترین گاز در جو زمین کدام است؟", "opts": ["نیتروژن", "اکسیژن", "دی‌اکسید کربن", "آرگون"], "ans": 0},
    {"q": "آب در چند درجه سانتی‌گراد می‌جوشد؟", "opts": ["۱۰۰", "۹۰", "۱۱۰", "۸۰"], "ans": 0},
    {"q": "آب در چند درجه سانتی‌گراد یخ می‌زند؟", "opts": ["۰", "-۱۰", "۱۰", "۵"], "ans": 0},
    {"q": "کدام فلز در دمای اتاق مایع است؟", "opts": ["جیوه", "آهن", "مس", "طلا"], "ans": 0},
    {"q": "کدام فلز از همه رساناتر است؟", "opts": ["نقره", "مس", "طلا", "آلومینیوم"], "ans": 0},
    {"q": "واحد سازنده بدن موجودات زنده چیست؟", "opts": ["سلول", "اتم", "مولکول", "بافت"], "ans": 0},
    {"q": "بزرگ‌ترین اندام بدن انسان کدام است؟", "opts": ["پوست", "کبد", "مغز", "ریه"], "ans": 0},
    {"q": "سنگین‌ترین اندام داخلی بدن انسان کدام است؟", "opts": ["کبد", "مغز", "قلب", "کلیه"], "ans": 0},
    {"q": "قلب انسان چند حفره دارد؟", "opts": ["۴", "۲", "۳", "۵"], "ans": 0},
    {"q": "خون توسط کدام اندام تصفیه می‌شود؟", "opts": ["کلیه", "کبد", "قلب", "طحال"], "ans": 0},
    {"q": "کدام اندام مسئول ترشح انسولین است؟", "opts": ["لوزالمعده", "کبد", "کلیه", "طحال"], "ans": 0},
    {"q": "کدام ویتامین از نور خورشید ساخته می‌شود؟", "opts": ["ویتامین D", "ویتامین C", "ویتامین A", "ویتامین B"], "ans": 0},
    {"q": "کمبود کدام ویتامین باعث اسکوربوت می‌شود؟", "opts": ["ویتامین C", "ویتامین D", "ویتامین A", "ویتامین B12"], "ans": 0},
    {"q": "DNA در کدام قسمت سلول قرار دارد؟", "opts": ["هسته", "سیتوپلاسم", "غشا", "میتوکندری"], "ans": 0},
    {"q": "بزرگ‌ترین جانور روی زمین کدام است؟", "opts": ["نهنگ آبی", "فیل", "زرافه", "کرگدن"], "ans": 0},
    {"q": "سریع‌ترین جانور خشکی کدام است؟", "opts": ["یوزپلنگ", "شیر", "اسب", "آهو"], "ans": 0},
    {"q": "بلندترین جانور جهان کدام است؟", "opts": ["زرافه", "فیل", "شتر", "کرگدن"], "ans": 0},
    {"q": "نویسنده شاهنامه کیست؟", "opts": ["فردوسی", "حافظ", "سعدی", "مولانا"], "ans": 0},
    {"q": "نویسنده گلستان و بوستان کیست؟", "opts": ["سعدی", "حافظ", "فردوسی", "مولانا"], "ans": 0},
    {"q": "غزل‌سرای بزرگ ایران چه کسی است؟", "opts": ["حافظ", "سعدی", "مولانا", "نظامی"], "ans": 0},
    {"q": "نویسنده مثنوی معنوی کیست؟", "opts": ["مولانا", "حافظ", "سعدی", "فردوسی"], "ans": 0},
    {"q": "نویسنده خمسه (پنج گنج) کیست؟", "opts": ["نظامی گنجوی", "فردوسی", "مولانا", "جامی"], "ans": 0},
    {"q": "پدر شعر فارسی چه کسی است؟", "opts": ["رودکی", "فردوسی", "عنصری", "ناصرخسرو"], "ans": 0},
    {"q": "شاعر معاصر «صدای پای آب» کیست؟", "opts": ["سهراب سپهری", "شاملو", "نیما", "فروغ"], "ans": 0},
    {"q": "نویسنده «بوف کور» کیست؟", "opts": ["صادق هدایت", "صادق چوبک", "جلال آل‌احمد", "هوشنگ گلشیری"], "ans": 0},
    {"q": "نویسنده «رومئو و ژولیت» کیست؟", "opts": ["شکسپیر", "دیکنز", "گوته", "تولستوی"], "ans": 0},
    {"q": "نویسنده «جنگ و صلح» کیست؟", "opts": ["تولستوی", "داستایوفسکی", "چخوف", "گوگول"], "ans": 0},
    {"q": "نویسنده «جنایت و مکافات» کیست؟", "opts": ["داستایوفسکی", "تولستوی", "چخوف", "پوشکین"], "ans": 0},
    {"q": "نویسنده «بینوایان» کیست؟", "opts": ["ویکتور هوگو", "بالزاک", "فلوبر", "زولا"], "ans": 0},
    {"q": "نویسنده «کمدی الهی» کیست؟", "opts": ["دانته", "پترارک", "بوکاچیو", "ماکیاولی"], "ans": 0},
    {"q": "نویسنده «دن کیشوت» کیست؟", "opts": ["سروانتس", "لورکا", "بورخس", "مارکز"], "ans": 0},
    {"q": "نویسنده «صد سال تنهایی» کیست؟", "opts": ["گابریل گارسیا مارکز", "بورخس", "پابلو نرودا", "وارگاس یوسا"], "ans": 0},
    {"q": "نویسنده «کیمیاگر» کیست؟", "opts": ["پائولو کوئیلو", "مارکز", "بورخس", "نرودا"], "ans": 0},
    {"q": "نویسنده «آنا کارنینا» کیست؟", "opts": ["تولستوی", "داستایوفسکی", "چخوف", "تورگنیف"], "ans": 0},
    {"q": "فوتبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["۱۱", "۱۰", "۱۲", "۹"], "ans": 0},
    {"q": "بازی فوتبال چند نیمه دارد؟", "opts": ["۲", "۳", "۴", "۱"], "ans": 0},
    {"q": "هر نیمه فوتبال چند دقیقه است؟", "opts": ["۴۵", "۴۰", "۵۰", "۳۰"], "ans": 0},
    {"q": "کدام کشور بیشترین قهرمانی جام جهانی فوتبال را دارد؟", "opts": ["برزیل", "آلمان", "ایتالیا", "آرژانتین"], "ans": 0},
    {"q": "بازی بسکتبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["۵", "۶", "۷", "۴"], "ans": 0},
    {"q": "بازی والیبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["۶", "۵", "۷", "۸"], "ans": 0},
    {"q": "المپیک هر چند سال یک بار برگزار می‌شود؟", "opts": ["۴", "۲", "۳", "۵"], "ans": 0},
    {"q": "کشتی فرنگی از کدام کشور ریشه گرفته است؟", "opts": ["فرانسه", "یونان", "ایران", "ترکیه"], "ans": 0},
    {"q": "کدام ورزش به «ورزش اول ایران» معروف است؟", "opts": ["کشتی", "فوتبال", "والیبال", "بسکتبال"], "ans": 0},
    {"q": "بازی شطرنج چند مهره برای هر بازیکن دارد؟", "opts": ["۱۶", "۱۵", "۱۸", "۲۰"], "ans": 0},
    {"q": "پله فوتبالیست معروف اهل کدام کشور بود؟", "opts": ["برزیل", "آرژانتین", "پرتغال", "اروگوئه"], "ans": 0},
    {"q": "مسی فوتبالیست معروف اهل کدام کشور است؟", "opts": ["آرژانتین", "برزیل", "پرتغال", "اروگوئه"], "ans": 0},
    {"q": "کریستیانو رونالدو اهل کدام کشور است؟", "opts": ["پرتغال", "برزیل", "آرژانتین", "اسپانیا"], "ans": 0},
    {"q": "جام جهانی فوتبال هر چند سال برگزار می‌شود؟", "opts": ["۴", "۲", "۳", "۵"], "ans": 0},
    {"q": "فوتبال در کدام کشور مدرن شد؟", "opts": ["انگلستان", "برزیل", "آرژانتین", "آلمان"], "ans": 0},
    {"q": "کارگردان معروف «پدرخوانده» کیست؟", "opts": ["فرانسیس فورد کوپولا", "اسپیلبرگ", "اسکورسیزی", "کوبریک"], "ans": 0},
    {"q": "کارگردان معروف «تایتانیک» کیست؟", "opts": ["جیمز کامرون", "اسپیلبرگ", "اسکورسیزی", "کوبریک"], "ans": 0},
    {"q": "نقاش معروف «مونالیزا» کیست؟", "opts": ["لئوناردو داوینچی", "میکل‌آنژ", "ونسان ون گوگ", "پیکاسو"], "ans": 0},
    {"q": "نقاش معروف «شب‌های پرستاره» کیست؟", "opts": ["ونسان ون گوگ", "داوینچی", "پیکاسو", "مونه"], "ans": 0},
    {"q": "نقاش تابلوی «گرنیکا» کیست؟", "opts": ["پابلو پیکاسو", "دالی", "مونه", "رنوآر"], "ans": 0},
    {"q": "مجسمه‌ساز معروف «دیوید» کیست؟", "opts": ["میکل‌آنژ", "داوینچی", "رافائل", "دوناتلو"], "ans": 0},
    {"q": "کارگردان «آواتار» کیست؟", "opts": ["جیمز کامرون", "اسپیلبرگ", "اسکورسیزی", "کوبریک"], "ans": 0},
    {"q": "کارگردان «ارباب حلقه‌ها» کیست؟", "opts": ["پیتر جکسون", "کامرون", "اسپیلبرگ", "کوبریک"], "ans": 0},
    {"q": "کارگردان ایرانی «طعم گیلاس» کیست؟", "opts": ["عباس کیارستمی", "مجید مجیدی", "اصغر فرهادی", "بهرام بیضایی"], "ans": 0},
    {"q": "کارگردان ایرانی «جدایی نادر از سیمین» کیست؟", "opts": ["اصغر فرهادی", "کیارستمی", "مجیدی", "بیضایی"], "ans": 0},
    {"q": "کارگردان ایرانی «بچه‌های آسمان» کیست؟", "opts": ["مجید مجیدی", "کیارستمی", "فرهادی", "بیضایی"], "ans": 0},
    {"q": "اسکار مربوط به صنعت سینمای کدام کشور است؟", "opts": ["آمریکا", "فرانسه", "انگلیس", "هند"], "ans": 0},
    {"q": "جشنواره فیلم کن در کدام کشور برگزار می‌شود؟", "opts": ["فرانسه", "ایتالیا", "آمریکا", "آلمان"], "ans": 0},
    {"q": "ساز معروف ایرانی که با آرشه نواخته می‌شود؟", "opts": ["کمانچه", "تار", "سنتور", "نی"], "ans": 0},
    {"q": "ساز معروف ایرانی که با مضراب نواخته می‌شود؟", "opts": ["تار", "کمانچه", "نی", "تنبک"], "ans": 0},
    {"q": "ساز بادی معروف ایرانی؟", "opts": ["نی", "تار", "سنتور", "تنبک"], "ans": 0},
    {"q": "ساز کوبه‌ای معروف ایرانی؟", "opts": ["تنبک", "تار", "نی", "کمانچه"], "ans": 0},
    {"q": "استاد آواز سنتی ایرانی معروف قرن اخیر؟", "opts": ["محمدرضا شجریان", "بهرام", "ابی", "داریوش"], "ans": 0},
    {"q": "آهنگساز معروف آلمانی «سمفونی نهم»؟", "opts": ["بتهوون", "موتزارت", "باخ", "شوپن"], "ans": 0},
    {"q": "آهنگساز معروف اتریشی «دون ژوان»؟", "opts": ["موتزارت", "بتهوون", "باخ", "شوپن"], "ans": 0},
    {"q": "پدر علم کامپیوتر چه کسی است؟", "opts": ["آلن تورینگ", "بیل گیتس", "استیو جابز", "لینوس توروالدز"], "ans": 0},
    {"q": "بنیان‌گذار مایکروسافت کیست؟", "opts": ["بیل گیتس", "استیو جابز", "مارک زاکربرگ", "جف بزوس"], "ans": 0},
    {"q": "بنیان‌گذار اپل کیست؟", "opts": ["استیو جابز", "بیل گیتس", "مارک زاکربرگ", "ایلان ماسک"], "ans": 0},
    {"q": "بنیان‌گذار فیسبوک کیست؟", "opts": ["مارک زاکربرگ", "بیل گیتس", "ایلان ماسک", "جف بزوس"], "ans": 0},
    {"q": "بنیان‌گذار تسلا و اسپیس‌ایکس کیست؟", "opts": ["ایلان ماسک", "جف بزوس", "بیل گیتس", "مارک زاکربرگ"], "ans": 0},
    {"q": "بنیان‌گذار آمازون کیست؟", "opts": ["جف بزوس", "ایلان ماسک", "بیل گیتس", "مارک زاکربرگ"], "ans": 0},
    {"q": "زبان برنامه‌نویسی که برای هوش مصنوعی معروف است؟", "opts": ["Python", "Java", "C", "PHP"], "ans": 0},
    {"q": "زبان برنامه‌نویسی وب سمت کلاینت؟", "opts": ["JavaScript", "Python", "C++", "Java"], "ans": 0},
    {"q": "پروتکل وب چه نام دارد؟", "opts": ["HTTP", "FTP", "SMTP", "TCP"], "ans": 0},
    {"q": "هر بایت چند بیت است؟", "opts": ["۸", "۴", "۱۶", "۳۲"], "ans": 0},
    {"q": "سیستم‌عامل معروف مایکروسافت؟", "opts": ["Windows", "macOS", "Linux", "Android"], "ans": 0},
    {"q": "سیستم‌عامل موبایل شرکت اپل؟", "opts": ["iOS", "Android", "Windows", "Linux"], "ans": 0},
    {"q": "سیستم‌عامل موبایل شرکت گوگل؟", "opts": ["Android", "iOS", "Windows", "macOS"], "ans": 0},
    {"q": "شرکت مادر گوگل چه نام دارد؟", "opts": ["Alphabet", "Meta", "Microsoft", "Apple"], "ans": 0},
    {"q": "شرکت مادر فیسبوک چه نام دارد؟", "opts": ["Meta", "Alphabet", "Microsoft", "Apple"], "ans": 0},
    {"q": "ChatGPT محصول کدام شرکت است؟", "opts": ["OpenAI", "Google", "Microsoft", "Meta"], "ans": 0},
    {"q": "کدام سیاره به سیاره سرخ معروف است؟", "opts": ["مریخ", "زهره", "مشتری", "زحل"], "ans": 0},
    {"q": "نزدیک‌ترین سیاره به خورشید کدام است؟", "opts": ["عطارد", "زهره", "زمین", "مریخ"], "ans": 0},
    {"q": "بزرگ‌ترین سیاره منظومه شمسی؟", "opts": ["مشتری", "زحل", "زمین", "نپتون"], "ans": 0},
    {"q": "سیاره‌ای که حلقه معروف دارد؟", "opts": ["زحل", "مشتری", "اورانوس", "نپتون"], "ans": 0},
    {"q": "زمین چندمین سیاره از خورشید است؟", "opts": ["سوم", "دوم", "چهارم", "پنجم"], "ans": 0},
    {"q": "خورشید یک ستاره است یا سیاره؟", "opts": ["ستاره", "سیاره", "قمر", "سیارک"], "ans": 0},
    {"q": "سال نوری واحد اندازه‌گیری چیست؟", "opts": ["فاصله", "زمان", "جرم", "سرعت"], "ans": 0},
    {"q": "کدام رنگ در پرچم ایران نیست؟", "opts": ["آبی", "سبز", "سفید", "سرخ"], "ans": 0},
    {"q": "پرچم ایران چند رنگ دارد؟", "opts": ["۳", "۲", "۴", "۵"], "ans": 0},
    {"q": "واحد پول ژاپن چیست؟", "opts": ["ین", "یوان", "وون", "دلار"], "ans": 0},
    {"q": "واحد پول چین چیست؟", "opts": ["یوان", "ین", "وون", "دلار"], "ans": 0},
    {"q": "واحد پول انگلیس چیست؟", "opts": ["پوند", "یورو", "دلار", "فرانک"], "ans": 0},
    {"q": "پول رسمی اتحادیه اروپا؟", "opts": ["یورو", "پوند", "دلار", "فرانک"], "ans": 0},
    {"q": "کدام کشور بیشترین جمعیت جهان را دارد؟", "opts": ["هند", "چین", "آمریکا", "اندونزی"], "ans": 0},
    {"q": "کدام قاره بیشترین کشورها را دارد؟", "opts": ["آفریقا", "آسیا", "اروپا", "آمریکای جنوبی"], "ans": 0},
    {"q": "کدام حیوان نماد ملی ایران باستان بود؟", "opts": ["شیر", "عقاب", "اسب", "پلنگ"], "ans": 0},
    {"q": "کدام کشور به سرزمین آفتاب تابان معروف است؟", "opts": ["ژاپن", "چین", "کره", "تایلند"], "ans": 0},
    {"q": "کدام شهر به شهر ابدی معروف است؟", "opts": ["رم", "آتن", "قاهره", "بغداد"], "ans": 0},
]

# ============================== ژنراتور سوال ریاضی ==============================
def generate_math_question() -> dict:
    kind = random.choice(["add", "sub", "mul", "div"])
    if kind == "add":
        a, b = random.randint(11, 999), random.randint(11, 999)
        answer = a + b
        q = f"{a} + {b} = ?"
    elif kind == "sub":
        a, b = random.randint(50, 999), random.randint(1, 49)
        answer = a - b
        q = f"{a} - {b} = ?"
    elif kind == "mul":
        a, b = random.randint(2, 20), random.randint(2, 20)
        answer = a * b
        q = f"{a} × {b} = ?"
    else:
        b = random.randint(2, 15)
        answer = random.randint(2, 30)
        a = b * answer
        q = f"{a} ÷ {b} = ?"

    wrongs = set()
    while len(wrongs) < 3:
        delta = random.choice([-3, -2, -1, 1, 2, 3, 4, 5])
        w = answer + delta
        if w > 0 and w != answer:
            wrongs.add(w)
    opts = [answer] + list(wrongs)
    random.shuffle(opts)
    return {"q": q, "opts": [str(x) for x in opts], "ans": opts.index(answer)}


def get_random_quiz_question() -> dict:
    if random.random() < 0.7:
        return random.choice(QUIZ_QUESTIONS)
    return generate_math_question()


# ============================== اسکیمای MySQL ==============================
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username VARCHAR(255),
        first_name VARCHAR(255),
        balance BIGINT NOT NULL DEFAULT 0,
        bank_balance BIGINT NOT NULL DEFAULT 0,
        card_number VARCHAR(16) UNIQUE,
        last_daily VARCHAR(10),
        created_at VARCHAR(32) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        asset_type VARCHAR(32) NOT NULL,
        asset_key VARCHAR(64) NOT NULL,
        purchase_price BIGINT NOT NULL,
        daily_income BIGINT NOT NULL,
        purchased_at VARCHAR(32) NOT NULL,
        INDEX idx_assets (user_id, asset_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

user_states: dict[int, dict] = {}
rooms: dict[str, dict] = {}
pending_transfers: dict[int, dict] = {}
penalty_games: dict[int, dict] = {}
casino_pending: dict[int, dict] = {}
daily_lock = asyncio.Lock()


# ============================== کمکی‌ها ==============================
def fa_to_en(text: str) -> str:
    return (text or "").translate(str.maketrans(PERSIAN_DIGITS, EN_DIGITS))

def to_fa(value) -> str:
    return str(value).translate(str.maketrans(EN_DIGITS, PERSIAN_DIGITS))

def fmt(amount: int) -> str:
    return to_fa(f"{int(amount):,}")

def parse_amount(text: str):
    cleaned = fa_to_en(text).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    v = int(cleaned)
    return v if v > 0 else None

def card_number_for(user_id: int) -> str:
    return f"6037{str(user_id).zfill(12)[-12:]}"

def format_card(card: str) -> str:
    if not card or len(card) != 16:
        return card or "-"
    return f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:16]}"

def now_iso() -> str:
    return datetime.now(TEHRAN).isoformat()

def escape(text) -> str:
    return html.escape(str(text or ""))

def new_room_id() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        rid = "".join(secrets.choice(alphabet) for _ in range(8))
        if rid not in rooms:
            return rid

def find_user_room(user_id: int):
    for rid, room in rooms.items():
        if user_id in room.get("players", []) and room.get("status") in ("waiting", "playing"):
            return rid
    return None

def ttt_check_win(board):
    lines = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None

def apply_commission(full_prize: int) -> tuple[int, int]:
    commission = int(full_prize * COMMISSION_RATE)
    return full_prize - commission, commission

async def safe_edit(query, text: str, reply_markup=None):
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                       reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        try:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML,
                                            reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception:
            logger.exception("safe_edit failed")


# ============================== اتصال DB ==============================
async def init_db_pool():
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        db=DB_NAME, autocommit=False, minsize=1, maxsize=10, charset="utf8mb4")
    logger.info("✅ Connection Pool به MySQL ساخته شد.")

async def close_db_pool():
    global db_pool
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()
        logger.info("🔌 Connection Pool بسته شد.")

async def init_db():
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            for stmt in SCHEMA_STATEMENTS:
                await cur.execute(stmt)
            await conn.commit()
    logger.info("✅ جداول MySQL آماده شدند.")


# ============================== توابع DB ==============================
async def ensure_user(user) -> dict:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "INSERT IGNORE INTO users "
                "(user_id, username, first_name, balance, bank_balance, card_number, created_at) "
                "VALUES (%s, %s, %s, %s, 0, %s, %s)",
                (user.id, user.username, user.first_name, START_BALANCE,
                 card_number_for(user.id), now_iso()))
            await cur.execute(
                "UPDATE users SET username=%s, first_name=%s WHERE user_id=%s",
                (user.username, user.first_name, user.id))
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user.id,))
            row = await cur.fetchone()
            await conn.commit()
            return dict(row)

async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

async def add_balance(user_id: int, amount: int):
    if amount <= 0:
        return
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s",
                              (amount, user_id))
            await conn.commit()

async def deduct_balance(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s",
                (amount, user_id, amount))
            await conn.commit()
            return cur.rowcount == 1

async def bank_deposit(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET balance = balance - %s, bank_balance = bank_balance + %s "
                    "WHERE user_id=%s AND balance >= %s",
                    (amount, amount, user_id, amount))
                if cur.rowcount != 1:
                    await conn.rollback()
                    return False
            await conn.commit()
            return True
        except Exception:
            await conn.rollback()
            logger.exception("bank_deposit failed")
            return False

async def bank_withdraw(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET bank_balance = bank_balance - %s, balance = balance + %s "
                    "WHERE user_id=%s AND bank_balance >= %s",
                    (amount, amount, user_id, amount))
                if cur.rowcount != 1:
                    await conn.rollback()
                    return False
            await conn.commit()
            return True
        except Exception:
            await conn.rollback()
            logger.exception("bank_withdraw failed")
            return False

async def transfer_coins(sender_id: int, recipient_id: int, amount: int, fee: int) -> bool:
    total = amount + fee
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s",
                    (total, sender_id, total))
                if cur.rowcount != 1:
                    await conn.rollback()
                    return False
                await cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s",
                                  (amount, recipient_id))
            await conn.commit()
            return True
        except Exception:
            await conn.rollback()
            logger.exception("transfer_coins failed")
            return False

async def count_assets(user_id: int, asset_type: str) -> int:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM assets WHERE user_id=%s AND asset_type=%s",
                              (user_id, asset_type))
            row = await cur.fetchone()
            return int(row[0]) if row else 0

async def get_assets(user_id: int, asset_type: str) -> list[dict]:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM assets WHERE user_id=%s AND asset_type=%s ORDER BY id ASC",
                (user_id, asset_type))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

async def buy_asset(user_id: int, asset_type: str, asset_key: str, price: int, income: int) -> str:
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM assets WHERE user_id=%s AND asset_type=%s",
                    (user_id, asset_type))
                if int((await cur.fetchone())[0]) >= MAX_ASSETS:
                    await conn.rollback()
                    return "limit"
                await cur.execute(
                    "UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s",
                    (price, user_id, price))
                if cur.rowcount != 1:
                    await conn.rollback()
                    return "balance"
                await cur.execute(
                    "INSERT INTO assets (user_id, asset_type, asset_key, purchase_price, daily_income, purchased_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, asset_type, asset_key, price, income, now_iso()))
            await conn.commit()
            return "ok"
        except Exception:
            await conn.rollback()
            logger.exception("buy_asset failed")
            return "error"

async def find_user_by_card(card: str):
    digits = "".join(ch for ch in (card or "") if ch.isdigit())
    if len(digits) != 16:
        return None
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE card_number=%s", (digits,))
            row = await cur.fetchone()
            return dict(row) if row else None


# ============================== سود روزانه ==============================
async def daily_payout(context: ContextTypes.DEFAULT_TYPE = None):
    async with daily_lock:
        today = datetime.now(TEHRAN).date()
        today_iso = today.isoformat()
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT user_id, bank_balance, last_daily FROM users")
                rows = await cur.fetchall()
                for row in rows:
                    user_id = row["user_id"]
                    bank_balance = int(row["bank_balance"] or 0)
                    last_daily = row["last_daily"]
                    if last_daily == today_iso:
                        continue
                    days = 1
                    if last_daily:
                        try:
                            last_date = datetime.fromisoformat(last_daily).date()
                            days = max(1, min((today - last_date).days, 7))
                        except Exception:
                            days = 1
                    interest = 0
                    current = bank_balance
                    for _ in range(days):
                        d = int(current * BANK_RATE)
                        interest += d
                        current += d
                    await cur.execute(
                        "SELECT COALESCE(SUM(daily_income), 0) FROM assets WHERE user_id=%s",
                        (user_id,))
                    asset_income = int((await cur.fetchone())[0] or 0) * days
                    await cur.execute(
                        "UPDATE users SET bank_balance = bank_balance + %s, "
                        "balance = balance + %s, last_daily = %s WHERE user_id=%s",
                        (interest, asset_income, today_iso, user_id))
                await conn.commit()
        logger.info("💰 سود روزانه %s پرداخت شد.", today_iso)


# ============================== کیبوردها ==============================
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 بانک", callback_data="bank:menu"),
         InlineKeyboardButton("🏠 ملک‌ها", callback_data="prop:menu")],
        [InlineKeyboardButton("👷 کارگرها", callback_data="worker:menu"),
         InlineKeyboardButton("🎮 بازی‌ها", callback_data="game:menu")],
        [InlineKeyboardButton("💸 انتقال زرکوین", callback_data="transfer:start")],
        [InlineKeyboardButton("📚 راهنما", callback_data="help:menu")],
    ])

def back_main_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")]])

def back_games_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")]])

def bank_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 واریز", callback_data="bank:deposit"),
         InlineKeyboardButton("🏧 برداشت", callback_data="bank:withdraw")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

def properties_menu_kb():
    rows, pair = [], []
    for key, prop in sorted(PROPERTIES.items(), key=lambda x: x[1]["price"]):
        pair.append(InlineKeyboardButton(
            f"{prop['emoji']} {prop['name']} | {fmt(prop['price'])}",
            callback_data=f"prop:buy:{key}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

def workers_menu_kb():
    rows, pair = [], []
    for key, w in sorted(WORKERS.items(), key=lambda x: x[1]["price"]):
        pair.append(InlineKeyboardButton(
            f"{w['emoji']} {w['name']} | {fmt(w['price'])}",
            callback_data=f"worker:buy:{key}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

def games_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی (۱۰۰۰+)", callback_data="game:rps"),
         InlineKeyboardButton("❌ دوز (۱۰۰۰+)", callback_data="game:ttt")],
        [InlineKeyboardButton("🧠 کوییز (۱۰۰۰+)", callback_data="game:quiz"),
         InlineKeyboardButton("⚽ پنالتی (۱۰۰۰+)", callback_data="game:penalty")],
        [InlineKeyboardButton("🎰 کازینو (۱۰,۰۰۰+)", callback_data="game:casino")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

def casino_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 اسلات (تا ۱۵x)", callback_data="casino:slots"),
         InlineKeyboardButton("🎲 تاس (تا ۶x)", callback_data="casino:dice")],
        [InlineKeyboardButton("🪙 شیر یا خط (۲x)", callback_data="casino:coin"),
         InlineKeyboardButton("🃏 کارت شانس (۴x)", callback_data="casino:card")],
        [InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")],
    ])

def casino_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎰 بازگشت به کازینو", callback_data="game:casino")]])

def casino_dice_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data="casino:play:dice:1"),
         InlineKeyboardButton("2️⃣", callback_data="casino:play:dice:2"),
         InlineKeyboardButton("3️⃣", callback_data="casino:play:dice:3")],
        [InlineKeyboardButton("4️⃣", callback_data="casino:play:dice:4"),
         InlineKeyboardButton("5️⃣", callback_data="casino:play:dice:5"),
         InlineKeyboardButton("6️⃣", callback_data="casino:play:dice:6")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_coin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦁 شیر", callback_data="casino:play:coin:heads"),
         InlineKeyboardButton("✖️ خط", callback_data="casino:play:coin:tails")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def casino_card_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♥️ دل", callback_data="casino:play:card:hearts"),
         InlineKeyboardButton("♦️ خشت", callback_data="casino:play:card:diamonds")],
        [InlineKeyboardButton("♠️ پیک", callback_data="casino:play:card:spades"),
         InlineKeyboardButton("♣️ گشنیز", callback_data="casino:play:card:clubs")],
        [InlineKeyboardButton("❌ لغو و بازگشت پول", callback_data="casino:cancel")],
    ])

def join_room_kb(room_id: str, game_key: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 ورود به بازی", callback_data=f"{game_key}:join:{room_id}")],
        [InlineKeyboardButton("❌ لغو", callback_data=f"room:cancel:{room_id}")],
    ])

def rps_choice_kb(room_id: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✊ سنگ", callback_data=f"rps:c:{room_id}:rock"),
        InlineKeyboardButton("✋ کاغذ", callback_data=f"rps:c:{room_id}:paper"),
        InlineKeyboardButton("✌️ قیچی", callback_data=f"rps:c:{room_id}:scissors"),
    ]])

def ttt_keyboard(room: dict):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            v = room["board"][i]
            if v == "X":
                row.append(InlineKeyboardButton("❌", callback_data="ttt:noop"))
            elif v == "O":
                row.append(InlineKeyboardButton("⭕", callback_data="ttt:noop"))
            else:
                row.append(InlineKeyboardButton("⬜", callback_data=f"ttt:m:{room['id']}:{i}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

def quiz_keyboard(room_id: str, opts):
    return InlineKeyboardMarkup([[InlineKeyboardButton(o, callback_data=f"quiz:a:{room_id}:{i}")]
                                 for i, o in enumerate(opts)])

def penalty_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚽ شوت!", callback_data="pen:shoot")]])

def transfer_confirm_kb(user_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"tr:c:{user_id}"),
        InlineKeyboardButton("❌ انصراف", callback_data=f"tr:x:{user_id}"),
    ]])


# ============================== متن‌ها ==============================
async def build_main_menu_text(user_id):
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    return (
        "✨ <b>به دنیای زرکوین خوش اومدی!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی کیف پول: <b>{fmt(balance)}</b> زرکوین\n\n"
        "از دکمه‌های زیر انتخاب کن 👇"
    )

async def build_bank_text(user_id):
    user = await get_user(user_id)
    balance = int(user["balance"]) if user else 0
    bank_balance = int(user["bank_balance"]) if user else 0
    card = format_card(user["card_number"]) if user else "-"
    interest = int(bank_balance * BANK_RATE)
    return (
        "🏦 <b>بانک زرکوین</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 شماره کارت شما:\n<code>{card}</code>\n\n"
        f"💰 کیف پول: <b>{fmt(balance)}</b>\n"
        f"🏦 بانک: <b>{fmt(bank_balance)}</b>\n"
        f"📈 سود روزانه (۲٪): <b>{fmt(interest)}</b>\n\n"
        "⏰ سود هر شب ساعت <b>۰۰:۰۰</b> به وقت تهران واریز میشه."
    )

async def build_assets_text(user_id, asset_type):
    if asset_type == "property":
        title, emoji, store = "املاک شما", "🏠", PROPERTIES
    else:
        title, emoji, store = "کارگرهای شما", "👷", WORKERS
    owned = await get_assets(user_id, asset_type)
    total_daily = sum(int(a["daily_income"]) for a in owned)
    lines = [
        f"{emoji} <b>{title}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 تعداد: <b>{to_fa(len(owned))}/{to_fa(MAX_ASSETS)}</b>",
        f"💵 درآمد روزانه کل: <b>{fmt(total_daily)}</b> زرکوین\n",
    ]
    if owned:
        for i, a in enumerate(owned, 1):
            info = store.get(a["asset_key"], {})
            lines.append(f"{to_fa(i)}. {info.get('emoji','•')} {info.get('name', a['asset_key'])} — {fmt(a['daily_income'])}/روز")
    else:
        lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)


# ============================== کامندها ==============================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        await build_main_menu_text(update.effective_user.id),
        parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def cmd_zarbat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        await build_main_menu_text(update.effective_user.id),
        parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def cmd_zarbazi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        "🎮 <b>بازی‌های زرکوین</b>\n\nیکی رو انتخاب کن:",
        parse_mode=ParseMode.HTML, reply_markup=games_menu_kb())


# ============================== لغو با ریپلای ==============================
async def handle_cancel(user_id: int, message):
    """لغو بازی فعلی کاربر با ریپلای «لغو» روی پیام بازی"""
    # ۱. کازینو
    sess = casino_pending.pop(user_id, None)
    if sess:
        await add_balance(user_id, sess["entry"])
        await message.reply_text(
            f"❌ بازی کازینو لغو شد.\n"
            f"💰 <b>{fmt(sess['entry'])}</b> زرکوین برگشت.",
            parse_mode=ParseMode.HTML)
        return

    # ۲. پنالتی
    pen = penalty_games.pop(user_id, None)
    if pen:
        await add_balance(user_id, pen["entry"])
        await message.reply_text(
            f"❌ پنالتی لغو شد.\n"
            f"💰 <b>{fmt(pen['entry'])}</b> زرکوین برگشت.",
            parse_mode=ParseMode.HTML)
        return

    # ۳. اتاق بازی دو نفره
    rid = find_user_room(user_id)
    if rid:
        room = rooms.get(rid)
        if room and room["status"] != "finished":
            for pid in room["players"]:
                await add_balance(pid, room["entry"])
            entry = room["entry"]
            room["status"] = "cancelled"
            rooms.pop(rid, None)
            await message.reply_text(
                f"❌ بازی لغو شد.\n"
                f"💰 <b>{fmt(entry)}</b> زرکوین به هر بازیکن برگشت.",
                parse_mode=ParseMode.HTML)
            return

    # ۴. حالت انتظار برای مبلغ/کارت
    if user_id in user_states:
        user_states.pop(user_id, None)
        await message.reply_text("❌ عملیات لغو شد.")
        return

    await message.reply_text("ℹ️ بازی فعالی برای لغو نداری.")


# ============================== Callback router ==============================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id

    # ✅ اگه بازی کازینو در جریانه و کاربر داره چیز دیگه‌ای می‌زنه، پولش رو برگردون
    pending = casino_pending.get(user_id)
    if pending:
        is_valid_choice = data.startswith(f"casino:play:{pending['game']}:")
        is_cancel = data == "casino:cancel"
        if not (is_valid_choice or is_cancel):
            casino_pending.pop(user_id, None)
            await add_balance(user_id, pending["entry"])
            try:
                await query.answer(f"⚠️ بازی قبلی لغو شد و {fmt(pending['entry'])} زرکوین برگشت.", show_alert=True)
            except Exception:
                pass

    user_states.pop(user_id, None)

    if data == "menu:main":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_main_menu_text(user_id), main_menu_kb())
        return

    if data == "bank:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_bank_text(user_id), bank_menu_kb())
        return
    if data == "bank:deposit":
        await query.answer()
        user_states[user_id] = {"action": "bank_deposit"}
        await safe_edit(query, "💰 <b>واریز به بانک</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return
    if data == "bank:withdraw":
        await query.answer()
        user_states[user_id] = {"action": "bank_withdraw"}
        await safe_edit(query, "🏧 <b>برداشت از بانک</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return

    if data == "prop:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(user_id, "property") +
                        "\n\n👇 از لیست زیر یکی بخر:", properties_menu_kb())
        return
    if data.startswith("prop:buy:"):
        key = data.split(":", 2)[2]
        prop = PROPERTIES.get(key)
        if not prop:
            await query.answer("❌ ملک نامعتبر", show_alert=True); return
        await ensure_user(query.from_user)
        if await count_assets(user_id, "property") >= MAX_ASSETS:
            await query.answer(f"❌ حداکثر {MAX_ASSETS} ملک مجاز!", show_alert=True); return
        user = await get_user(user_id)
        if int(user["balance"]) < prop["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        r = await buy_asset(user_id, "property", key, prop["price"], prop["income"])
        if r == "ok":
            await query.answer(f"✅ {prop['name']} خریداری شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_ASSETS} ملک مجاز!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
        await safe_edit(query, await build_assets_text(user_id, "property") +
                        "\n\n👇 از لیست زیر یکی بخر:", properties_menu_kb())
        return

    if data == "worker:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(user_id, "worker") +
                        "\n\n👇 از لیست زیر یکی استخدام کن:", workers_menu_kb())
        return
    if data.startswith("worker:buy:"):
        key = data.split(":", 2)[2]
        w = WORKERS.get(key)
        if not w:
            await query.answer("❌ نامعتبر", show_alert=True); return
        await ensure_user(query.from_user)
        if await count_assets(user_id, "worker") >= MAX_ASSETS:
            await query.answer(f"❌ حداکثر {MAX_ASSETS} کارگر مجاز!", show_alert=True); return
        user = await get_user(user_id)
        if int(user["balance"]) < w["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
        r = await buy_asset(user_id, "worker", key, w["price"], w["income"])
        if r == "ok":
            await query.answer(f"✅ {w['name']} استخدام شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_ASSETS} کارگر مجاز!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
        await safe_edit(query, await build_assets_text(user_id, "worker") +
                        "\n\n👇 از لیست زیر یکی استخدام کن:", workers_menu_kb())
        return

    if data == "game:menu":
        await query.answer()
        await safe_edit(query, "🎮 <b>بازی‌های زرکوین</b>\n\nیکی رو انتخاب کن:", games_menu_kb())
        return

    if data == "game:casino":
        await query.answer()
        await safe_edit(query,
            "🎰 <b>کازینو زر</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 حداقل ورودی: <b>۱۰,۰۰۰</b> زرکوین\n"
            "💵 کارمزد بات: ۱۰٪ از جایزه\n\n"
            "🎲 بازی‌ها:\n"
            "• 🎰 اسلات — تا ۱۵ برابر\n"
            "• 🎲 تاس — تا ۶ برابر\n"
            "• 🪙 شیر یا خط — ۲ برابر\n"
            "• 🃏 کارت شانس — ۴ برابر\n\n"
            "یکی رو انتخاب کن:",
            casino_menu_kb())
        return

    if data.startswith("casino:") and data.count(":") == 1:
        cg = data.split(":")[1]
        if cg in CASINO_GAMES:
            g = CASINO_GAMES[cg]
            user_states[user_id] = {"action": "casino_entry", "game": cg}
            await safe_edit(query,
                f"{g['emoji']} <b>{g['name']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 حداقل ورودی: <b>{fmt(g['min'])}</b> زرکوین\n"
                f"💵 کارمزد بات: ۱۰٪ از جایزه\n\n"
                f"مبلغ ورودی رو بفرست:",
                casino_back_kb())
        return

    if data == "casino:cancel":
        pending = casino_pending.pop(user_id, None)
        if pending:
            await add_balance(user_id, pending["entry"])
            await safe_edit(query, f"❌ بازی لغو شد و {fmt(pending['entry'])} زرکوین برگشت.", casino_menu_kb())
        else:
            await safe_edit(query, "❌ بازی فعالی نداشتی.", casino_menu_kb())
        return

    if data.startswith("casino:play:"):
        parts = data.split(":")
        cg, choice = parts[2], parts[3]
        pending = casino_pending.get(user_id)
        if not pending or pending["game"] != cg:
            await query.answer("❌ بازی فعالی نداری", show_alert=True); return
        casino_pending.pop(user_id, None)
        entry = pending["entry"]
        if cg == "dice":
            await resolve_dice(query, entry, choice)
        elif cg == "coin":
            await resolve_coin(query, entry, choice)
        elif cg == "card":
            await resolve_card(query, entry, choice)
        return

    if data.startswith("game:") and data.count(":") == 1:
        gk = data.split(":", 1)[1]
        if gk in GAMES:
            await start_game_entry(query, gk)
        return

    if data == "help:menu":
        await query.answer()
        await safe_edit(query, HELP_TEXT, back_main_kb())
        return

    if data == "transfer:start":
        await query.answer()
        user_states[user_id] = {"action": "transfer_amount"}
        await safe_edit(query, "💸 <b>انتقال زرکوین</b>\n\nمبلغ مورد نظر رو بفرست:", back_main_kb())
        return
    if data.startswith("tr:c:"):
        await query.answer()
        await confirm_transfer(query, int(data.split(":")[2]))
        return
    if data.startswith("tr:x:"):
        await query.answer()
        pending_transfers.pop(user_id, None)
        await safe_edit(query, "❌ انتقال لغو شد.", back_main_kb())
        return

    if data.startswith("room:cancel:"):
        await query.answer()
        await cancel_room(query, data.split(":")[2])
        return

    if data.startswith("rps:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data.startswith("rps:c:"):
        await query.answer()
        parts = data.split(":")
        await rps_choose(query, context, parts[2], parts[3])
        return

    if data.startswith("ttt:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data == "ttt:noop":
        await query.answer(); return
    if data.startswith("ttt:m:"):
        parts = data.split(":")
        await ttt_move(query, context, parts[2], int(parts[3]))
        return

    if data.startswith("quiz:join:"):
        await query.answer()
        await join_room(query, context, data.split(":")[2])
        return
    if data.startswith("quiz:a:"):
        parts = data.split(":")
        await quiz_answer(query, parts[2], int(parts[3]))
        return

    if data == "pen:shoot":
        await query.answer()
        await penalty_shoot(query, context)
        return

    await query.answer()


# ============================== بازی‌های دو نفره ==============================
async def start_game_entry(query, gk: str):
    user_id = query.from_user.id
    if find_user_room(user_id):
        await query.answer("⚠️ شما در یک بازی فعال هستید!", show_alert=True); return
    if user_id in penalty_games:
        await query.answer("⚠️ یک بازی دیگر در جریان است!", show_alert=True); return
    if user_id in casino_pending:
        await query.answer("⚠️ یک بازی کازینو در جریان است!", show_alert=True); return
    g = GAMES[gk]
    user_states[user_id] = {"action": "game_entry", "game": gk}
    await safe_edit(query,
        f"{g['emoji']} <b>{g['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 حداقل ورودی: <b>{fmt(g['min'])}</b> زرکوین\n"
        f"👥 بازیکنان: {to_fa(g['players'])}\n"
        f"💵 کارمزد بات: ۱۰٪ از جایزه\n\n"
        f"مبلغ ورودی رو بفرست:",
        back_games_kb())

async def join_room(query, context, room_id: str):
    room = rooms.get(room_id)
    if not room:
        await query.answer("❌ اتاق نیست", show_alert=True); return
    if room["status"] != "waiting":
        await query.answer("❌ بازی شروع شده", show_alert=True); return
    user_id = query.from_user.id
    if user_id == room["creator"]:
        await query.answer("❌ خودت سازنده‌ای", show_alert=True); return
    if user_id in room["players"]:
        await query.answer("✅ قبلاً وارد شدی", show_alert=True); return
    if find_user_room(user_id):
        await query.answer("⚠️ در بازی دیگر فعالی", show_alert=True); return
    await ensure_user(query.from_user)
    if not await deduct_balance(user_id, room["entry"]):
        await query.answer("❌ موجودی کافی نیست", show_alert=True); return
    room["players"].append(user_id)
    room["user_names"][user_id] = query.from_user.first_name or str(user_id)
    room["status"] = "playing"

    gk = room["game"]
    if gk == "rps":
        room["choices"] = {}
        text = (f"✊ <b>سنگ کاغذ قیچی</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"👤 بازیکن ۱: {escape(room['user_names'][room['players'][0]])}\n"
                f"👤 بازیکن ۲: {escape(room['user_names'][room['players'][1]])}\n\n"
                f"هر دو یک گزینه بزنید:")
        await safe_edit(query, text, rps_choice_kb(room_id))
    elif gk == "ttt":
        room["board"] = [""] * 9
        room["turn"] = room["players"][0]
        room["symbols"] = {room["players"][0]: "X", room["players"][1]: "O"}
        await render_ttt(query, room)
    elif gk == "quiz":
        q = get_random_quiz_question()
        room["question"] = q
        room["answered"] = False
        text = (f"🧠 <b>کوییز</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"❓ <b>{escape(q['q'])}</b>\n\n"
                f"اولین کسی که درست جواب بده برنده‌ست:")
        await safe_edit(query, text, quiz_keyboard(room_id, q["opts"]))

async def cancel_room(query, room_id: str):
    room = rooms.get(room_id)
    if not room:
        await query.answer("❌ اتاق نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"] and user_id != room["creator"]:
        await query.answer("❌ اجازه نداری", show_alert=True); return
    if room["status"] == "finished":
        return
    for pid in room["players"]:
        await add_balance(pid, room["entry"])
    room["status"] = "cancelled"
    rooms.pop(room_id, None)
    await safe_edit(query, "❌ بازی لغو شد و پول‌ها برگشت داده شد.", back_games_kb())

async def rps_choose(query, context, room_id, choice):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing":
        await query.answer("❌ بازی فعال نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"]:
        await query.answer("❌ تو بازیکن نیستی", show_alert=True); return
    if user_id in room["choices"]:
        await query.answer("✅ قبلاً انتخاب کردی", show_alert=True); return
    room["choices"][user_id] = choice
    if len(room["choices"]) < 2:
        await query.answer("✅ ثبت شد، منتظر حریف...", show_alert=True)
        text = (f"✊ <b>سنگ کاغذ قیچی</b>\n"
                f"💰 ورودی: {fmt(room['entry'])}\n\n"
                f"👤 {escape(room['user_names'][room['players'][0]])}: "
                f"{'✅' if room['players'][0] in room['choices'] else '⏳'}\n"
                f"👤 {escape(room['user_names'][room['players'][1]])}: "
                f"{'✅' if room['players'][1] in room['choices'] else '⏳'}")
        await safe_edit(query, text, None)
        return
    names = {"rock": "سنگ ✊", "paper": "کاغذ ✋", "scissors": "قیچی ✌️"}
    p1, p2 = room["players"]
    c1, c2 = room["choices"][p1], room["choices"][p2]
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if c1 == c2:
        await add_balance(p1, room["entry"])
        await add_balance(p2, room["entry"])
        result = "🤝 مساوی! پول‌ها برگشت."
    else:
        winner = p1 if beats[c1] == c2 else p2
        full_prize = int(room["entry"] * GAMES["rps"]["mult"])
        prize, comm = apply_commission(full_prize)
        await add_balance(winner, prize)
        result = (f"🏆 <b>{escape(room['user_names'][winner])}</b> برنده شد!\n"
                  f"💰 جایزه: {fmt(full_prize)}\n"
                  f"💵 کارمزد ۱۰٪: {fmt(comm)}\n"
                  f"✅ دریافتی: <b>{fmt(prize)}</b>")
    text = (
        f"✊ <b>نتیجه سنگ کاغذ قیچی</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 {escape(room['user_names'][p1])}: {names[c1]}\n"
        f"👤 {escape(room['user_names'][p2])}: {names[c2]}\n\n"
        f"{result}")
    room["status"] = "finished"
    rooms.pop(room_id, None)
    await safe_edit(query, text, back_games_kb())

async def render_ttt(query, room):
    p1, p2 = room["players"]
    turn = room["turn"]
    text = (f"❌ <b>دوز</b>\n"
            f"💰 ورودی: {fmt(room['entry'])}\n\n"
            f"👤 {escape(room['user_names'][p1])} ❌\n"
            f"👤 {escape(room['user_names'][p2])} ⭕\n\n"
            f"🎯 نوبت: <b>{escape(room['user_names'][turn])}</b>")
    await safe_edit(query, text, ttt_keyboard(room))

async def ttt_move(query, context, room_id, idx):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing":
        await query.answer("❌ بازی فعال نیست", show_alert=True); return
    user_id = query.from_user.id
    if user_id != room["turn"]:
        await query.answer("⏳ نوبت تو نیست", show_alert=True); return
    if room["board"][idx]:
        await query.answer("❌ خانه پر است", show_alert=True); return
    p1, p2 = room["players"]
    room["board"][idx] = room["symbols"][user_id]
    winner_symbol = ttt_check_win(room["board"])
    if winner_symbol:
        if winner_symbol == "draw":
            await add_balance(p1, room["entry"])
            await add_balance(p2, room["entry"])
            text = "🤝 <b>مساوی!</b> پول‌ها برگشت."
        else:
            winner = p1 if winner_symbol == "X" else p2
            full_prize = int(room["entry"] * GAMES["ttt"]["mult"])
            prize, comm = apply_commission(full_prize)
            await add_balance(winner, prize)
            text = (f"🏆 <b>{escape(room['user_names'][winner])}</b> برنده شد!\n"
                    f"💰 جایزه: {fmt(full_prize)}\n"
                    f"💵 کارمزد ۱۰٪: {fmt(comm)}\n"
                    f"✅ دریافتی: <b>{fmt(prize)}</b>")
        room["status"] = "finished"
        rooms.pop(room_id, None)
        await safe_edit(query
