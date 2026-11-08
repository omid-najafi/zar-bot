# -*- coding: utf-8 -*-
"""ربات زرکوین (بات زر) - نسخه نهایی با تاییدیه خرید و تاس تلگرام"""
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
MAX_PER_KEY = 5
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
    {"q": "انقلاب مشروطه در چه سالی رخ داد؟", "opts": ["1285 شمسی", "1290 شمسی", "1275 شمسی", "1300 شمسی"], "ans": 0},
    {"q": "ملی شدن صنعت نفت ایران در چه سالی رخ داد؟", "opts": ["1329 شمسی", "1325 شمسی", "1335 شمسی", "1340 شمسی"], "ans": 0},
    {"q": "رهبر نهضت ملی شدن نفت ایران چه کسی بود؟", "opts": ["دکتر مصدق", "دکتر فاطمی", "آیت‌الله کاشانی", "رضاشاه"], "ans": 0},
    {"q": "جنگ ایران و عراق چند سال طول کشید؟", "opts": ["8 سال", "6 سال", "10 سال", "5 سال"], "ans": 0},
    {"q": "کتیبه بیستون متعلق به کدام پادشاه است؟", "opts": ["داریوش اول", "کوروش", "خشایارشا", "اردشیر"], "ans": 0},
    {"q": "جنگ جهانی اول در چه سالی آغاز شد؟", "opts": ["1914", "1918", "1939", "1920"], "ans": 0},
    {"q": "جنگ جهانی دوم در چه سالی پایان یافت؟", "opts": ["1945", "1944", "1946", "1943"], "ans": 0},
    {"q": "انقلاب کبیر فرانسه در چه سالی رخ داد؟", "opts": ["1789", "1776", "1800", "1815"], "ans": 0},
    {"q": "دیوار برلین در چه سالی فروپاشید؟", "opts": ["1989", "1991", "1985", "1993"], "ans": 0},
    {"q": "اولین انسان روی ماه چه کسی بود؟", "opts": ["نیل آرمسترانگ", "یوری گاگارین", "باز آلدرین", "مایکل کالینز"], "ans": 0},
    {"q": "اولین انسان در فضا چه کسی بود؟", "opts": ["یوری گاگارین", "نیل آرمسترانگ", "جان گلن", "آلن شپرد"], "ans": 0},
    {"q": "جنگ سرد بین کدام دو کشور بود؟", "opts": ["آمریکا و شوروی", "آمریکا و چین", "آلمان و فرانسه", "انگلیس و آلمان"], "ans": 0},
    {"q": "فروپاشی اتحاد جماهیر شوروی در چه سالی رخ داد؟", "opts": ["1991", "1989", "1993", "1985"], "ans": 0},
    {"q": "کشف آمریکا توسط کریستف کلمب در چه سالی بود؟", "opts": ["1492", "1450", "1500", "1480"], "ans": 0},
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
    {"q": "آب در چند درجه سانتی‌گراد می‌جوشد؟", "opts": ["100", "90", "110", "80"], "ans": 0},
    {"q": "آب در چند درجه سانتی‌گراد یخ می‌زند؟", "opts": ["0", "-10", "10", "5"], "ans": 0},
    {"q": "کدام فلز در دمای اتاق مایع است؟", "opts": ["جیوه", "آهن", "مس", "طلا"], "ans": 0},
    {"q": "کدام فلز از همه رساناتر است؟", "opts": ["نقره", "مس", "طلا", "آلومینیوم"], "ans": 0},
    {"q": "واحد سازنده بدن موجودات زنده چیست؟", "opts": ["سلول", "اتم", "مولکول", "بافت"], "ans": 0},
    {"q": "بزرگ‌ترین اندام بدن انسان کدام است؟", "opts": ["پوست", "کبد", "مغز", "ریه"], "ans": 0},
    {"q": "سنگین‌ترین اندام داخلی بدن انسان کدام است؟", "opts": ["کبد", "مغز", "قلب", "کلیه"], "ans": 0},
    {"q": "قلب انسان چند حفره دارد؟", "opts": ["4", "2", "3", "5"], "ans": 0},
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
    {"q": "فوتبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["11", "10", "12", "9"], "ans": 0},
    {"q": "بازی فوتبال چند نیمه دارد؟", "opts": ["2", "3", "4", "1"], "ans": 0},
    {"q": "هر نیمه فوتبال چند دقیقه است؟", "opts": ["45", "40", "50", "30"], "ans": 0},
    {"q": "کدام کشور بیشترین قهرمانی جام جهانی فوتبال را دارد؟", "opts": ["برزیل", "آلمان", "ایتالیا", "آرژانتین"], "ans": 0},
    {"q": "بازی بسکتبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["5", "6", "7", "4"], "ans": 0},
    {"q": "بازی والیبال هر تیم چند بازیکن در زمین دارد؟", "opts": ["6", "5", "7", "8"], "ans": 0},
    {"q": "المپیک هر چند سال یک بار برگزار می‌شود؟", "opts": ["4", "2", "3", "5"], "ans": 0},
    {"q": "کشتی فرنگی از کدام کشور ریشه گرفته است؟", "opts": ["فرانسه", "یونان", "ایران", "ترکیه"], "ans": 0},
    {"q": "کدام ورزش به «ورزش اول ایران» معروف است؟", "opts": ["کشتی", "فوتبال", "والیبال", "بسکتبال"], "ans": 0},
    {"q": "بازی شطرنج چند مهره برای هر بازیکن دارد؟", "opts": ["16", "15", "18", "20"], "ans": 0},
    {"q": "پله فوتبالیست معروف اهل کدام کشور بود؟", "opts": ["برزیل", "آرژانتین", "پرتغال", "اروگوئه"], "ans": 0},
    {"q": "مسی فوتبالیست معروف اهل کدام کشور است؟", "opts": ["آرژانتین", "برزیل", "پرتغال", "اروگوئه"], "ans": 0},
    {"q": "کریستیانو رونالدو اهل کدام کشور است؟", "opts": ["پرتغال", "برزیل", "آرژانتین", "اسپانیا"], "ans": 0},
    {"q": "جام جهانی فوتبال هر چند سال برگزار می‌شود؟", "opts": ["4", "2", "3", "5"], "ans": 0},
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
    {"q": "هر بایت چند بیت است؟", "opts": ["8", "4", "16", "32"], "ans": 0},
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
    {"q": "پرچم ایران چند رنگ دارد؟", "opts": ["3", "2", "4", "5"], "ans": 0},
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
        INDEX idx_assets (user_id, asset_type, asset_key)
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

def fmt(amount: int) -> str:
    return f"{int(amount):,}"

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

async def count_assets_by_key(user_id: int, asset_key: str) -> int:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM assets WHERE user_id=%s AND asset_key=%s",
                (user_id, asset_key))
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
                    "SELECT COUNT(*) FROM assets WHERE user_id=%s AND asset_key=%s",
                    (user_id, asset_key))
                if int((await cur.fetchone())[0]) >= MAX_PER_KEY:
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

# ✅ منوی عمودی برای ملک‌ها
async def properties_menu_kb(user_id: int):
    rows = []
    for key, prop in sorted(PROPERTIES.items(), key=lambda x: x[1]["price"]):
        count = await count_assets_by_key(user_id, key)
        label = f"{prop['emoji']} {prop['name']} | قیمت: {fmt(prop['price'])} | سود: {fmt(prop['income'])}/روز"
        if count >= MAX_PER_KEY:
            label += " (تکمیل)"
        else:
            label += f" ({count}/{MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"prop:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

# ✅ منوی عمودی برای کارگرها
async def workers_menu_kb(user_id: int):
    rows = []
    for key, w in sorted(WORKERS.items(), key=lambda x: x[1]["price"]):
        count = await count_assets_by_key(user_id, key)
        label = f"{w['emoji']} {w['name']} | قیمت: {fmt(w['price'])} | سود: {fmt(w['income'])}/روز"
        if count >= MAX_PER_KEY:
            label += " (تکمیل)"
        else:
            label += f" ({count}/{MAX_PER_KEY})"
        rows.append([InlineKeyboardButton(label, callback_data=f"worker:select:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)

def games_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game:rps"),
         InlineKeyboardButton("❌ دوز", callback_data="game:ttt")],
        [InlineKeyboardButton("🧠 کوییز", callback_data="game:quiz"),
         InlineKeyboardButton("⚽ پنالتی", callback_data="game:penalty")],
        [InlineKeyboardButton("🎰 کازینو", callback_data="game:casino")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")],
    ])

def casino_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 اسلات", callback_data="casino:slots"),
         InlineKeyboardButton("🎲 تاس", callback_data="casino:dice")],
        [InlineKeyboardButton("🪙 شیر یا خط", callback_data="casino:coin"),
         InlineKeyboardButton("🃏 کارت شانس", callback_data="casino:card")],
        [InlineKeyboardButton("🔙 بازگشت به بازی‌ها", callback_data="game:menu")],
    ])

def casino_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎰 بازگشت به کازینو", callback_data="game:casino")]])

# ✅ کیبورد جدید تاس با گزینه‌های زوج/فرد و دقیق
def casino_dice_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("دقیقاً 1 (3x)", callback_data="casino:play:dice:exact:1"),
         InlineKeyboardButton("دقیقاً 2 (3x)", callback_data="casino:play:dice:exact:2"),
         InlineKeyboardButton("دقیقاً 3 (3x)", callback_data="casino:play:dice:exact:3")],
        [InlineKeyboardButton("دقیقاً 4 (3x)", callback_data="casino:play:dice:exact:4"),
         InlineKeyboardButton("دقیقاً 5 (3x)", callback_data="casino:play:dice:exact:5"),
         InlineKeyboardButton("دقیقاً 6 (3x)", callback_data="casino:play:dice:exact:6")],
        [InlineKeyboardButton("زوج (1.5x)", callback_data="casino:play:dice:parity:even"),
         InlineKeyboardButton("فرد (1.5x)", callback_data="casino:play:dice:parity:odd")],
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
        f"📈 سود روزانه (2%): <b>{fmt(interest)}</b>\n\n"
        "⏰ سود هر شب ساعت <b>00:00</b> به وقت تهران واریز میشه."
    )

async def build_assets_text(user_id, asset_type):
    if asset_type == "property":
        title, emoji, store = "املاک شما", "🏠", PROPERTIES
    else:
        title, emoji, store = "کارگرهای شما", "👷", WORKERS
    owned = await get_assets(user_id, asset_type)
    total_daily = sum(int(a["daily_income"]) for a in owned)

    grouped = {}
    for a in owned:
        k = a["asset_key"]
        if k not in grouped:
            grouped[k] = {"count": 0, "daily": 0}
        grouped[k]["count"] += 1
        grouped[k]["daily"] += int(a["daily_income"])

    lines = [
        f"{emoji} <b>{title}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 تعداد کل: <b>{len(owned)}</b>",
        f"💵 درآمد روزانه کل: <b>{fmt(total_daily)}</b> زرکوین\n",
    ]
    if grouped:
        for key, data in grouped.items():
            info = store.get(key, {})
            lines.append(
                f"{info.get('emoji','•')} {info.get('name', key)}: "
                f"{data['count']} عدد ({fmt(data['daily'])}/روز)"
            )
    else:
        lines.append("📭 هنوز چیزی نخریدی.")
    return "\n".join(lines)


# ============================== کامندها ==============================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        await build_main_menu_text(update.effective_user.id),
        parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "🎮 <b>بازی‌های زرکوین</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 حداقل ورودی: <b>1,000</b> زرکوین\n"
        "💵 کارمزد: <b>10%</b> از جایزه\n\n"
        "✊ سنگ کاغذ قیچی — 1.5x\n"
        "❌ دوز — 1.7x\n"
        "🧠 کوییز — 1.8x\n"
        "⚽ پنالتی — 2x\n"
        "🎰 کازینو — تا 15x\n\n"
        "یکی رو انتخاب کن:",
        parse_mode=ParseMode.HTML, reply_markup=games_menu_kb())


# ============================== لغو با ریپلای ==============================
async def handle_cancel(user_id: int, message):
    sess = casino_pending.pop(user_id, None)
    if sess:
        await add_balance(user_id, sess["entry"])
        await message.reply_text(
            f"❌ بازی کازینو لغو شد.\n💰 <b>{fmt(sess['entry'])}</b> زرکوین برگشت.",
            parse_mode=ParseMode.HTML)
        return

    pen = penalty_games.pop(user_id, None)
    if pen:
        await add_balance(user_id, pen["entry"])
        await message.reply_text(
            f"❌ پنالتی لغو شد.\n💰 <b>{fmt(pen['entry'])}</b> زرکوین برگشت.",
            parse_mode=ParseMode.HTML)
        return

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
                f"❌ بازی لغو شد.\n💰 <b>{fmt(entry)}</b> زرکوین به هر بازیکن برگشت.",
                parse_mode=ParseMode.HTML)
            return

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

    # اگه بازی کازینو در جریانه و کاربر داره چیز دیگه‌ای می‌زنه، پولش رو برگردون
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

    # ------------------ ملک‌ها ------------------
    if data == "prop:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(user_id, "property") +
                        "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):",
                        await properties_menu_kb(user_id))
        return
        
    if data.startswith("prop:select:"):
        await query.answer()
        key = data.split(":")[2]
        prop = PROPERTIES.get(key)
        if not prop:
            await query.answer("❌ ملک نامعتبر", show_alert=True); return
        
        count = await count_assets_by_key(user_id, key)
        if count >= MAX_PER_KEY:
            await query.answer(f"❌ حداکثر {MAX_PER_KEY} عدد از این ملک مجاز است!", show_alert=True); return
            
        user = await get_user(user_id)
        if int(user["balance"]) < prop["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
            
        text = (
            f"🏠 <b>تایید خرید ملک</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷 نام: {prop['emoji']} <b>{prop['name']}</b>\n"
            f"💰 قیمت: <b>{fmt(prop['price'])}</b> زرکوین\n"
            f"📈 سود روزانه: <b>{fmt(prop['income'])}</b> زرکوین\n"
            f"📊 تعداد فعلی شما: {count}/{MAX_PER_KEY}\n\n"
            f"آیا از خرید مطمئنی؟"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، بخر", callback_data=f"prop:confirm:{key}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="prop:menu")]
        ])
        await safe_edit(query, text, kb)
        return

    if data.startswith("prop:confirm:"):
        await query.answer()
        key = data.split(":")[2]
        prop = PROPERTIES.get(key)
        if not prop:
            await query.answer("❌ ملک نامعتبر", show_alert=True); return
            
        r = await buy_asset(user_id, "property", key, prop["price"], prop["income"])
        if r == "ok":
            await query.answer(f"✅ {prop['name']} خریداری شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_PER_KEY} عدد از این ملک مجاز است!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
            
        await safe_edit(query, await build_assets_text(user_id, "property") +
                        "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):",
                        await properties_menu_kb(user_id))
        return

    # ------------------ کارگرها ------------------
    if data == "worker:menu":
        await query.answer()
        await ensure_user(query.from_user)
        await safe_edit(query, await build_assets_text(user_id, "worker") +
                        "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):",
                        await workers_menu_kb(user_id))
        return
        
    if data.startswith("worker:select:"):
        await query.answer()
        key = data.split(":")[2]
        w = WORKERS.get(key)
        if not w:
            await query.answer("❌ کارگر نامعتبر", show_alert=True); return
            
        count = await count_assets_by_key(user_id, key)
        if count >= MAX_PER_KEY:
            await query.answer(f"❌ حداکثر {MAX_PER_KEY} عدد از این کارگر مجاز است!", show_alert=True); return
            
        user = await get_user(user_id)
        if int(user["balance"]) < w["price"]:
            await query.answer("❌ موجودی کافی نیست", show_alert=True); return
            
        text = (
            f"👷 <b>تایید استخدام کارگر</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷 نام: {w['emoji']} <b>{w['name']}</b>\n"
            f"💰 قیمت: <b>{fmt(w['price'])}</b> زرکوین\n"
            f"📈 سود روزانه: <b>{fmt(w['income'])}</b> زرکوین\n"
            f"📊 تعداد فعلی شما: {count}/{MAX_PER_KEY}\n\n"
            f"آیا از استخدام مطمئنی؟"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله، استخدام کن", callback_data=f"worker:confirm:{key}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="worker:menu")]
        ])
        await safe_edit(query, text, kb)
        return

    if data.startswith("worker:confirm:"):
        await query.answer()
        key = data.split(":")[2]
        w = WORKERS.get(key)
        if not w:
            await query.answer("❌ کارگر نامعتبر", show_alert=True); return
            
        r = await buy_asset(user_id, "worker", key, w["price"], w["income"])
        if r == "ok":
            await query.answer(f"✅ {w['name']} استخدام شد!", show_alert=True)
        elif r == "limit":
            await query.answer(f"❌ حداکثر {MAX_PER_KEY} عدد از این کارگر مجاز است!", show_alert=True)
        elif r == "balance":
            await query.answer("❌ موجودی کافی نیست", show_alert=True)
        else:
            await query.answer("❌ خطا", show_alert=True)
            
        await safe_edit(query, await build_assets_text(user_id, "worker") +
                        "\n\n👇 از لیست زیر انتخاب کن (حداکثر 5 از هر نوع):",
                        await workers_menu_kb(user_id))
        return

    # ------------------ بازی‌ها ------------------
    if data == "game:menu":
        await query.answer()
        await safe_edit(query,
            "🎮 <b>بازی‌های زرکوین</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 حداقل ورودی: <b>1,000</b> زرکوین\n"
            "💵 کارمزد: <b>10%</b> از جایزه\n\n"
            "✊ سنگ کاغذ قیچی — 1.5x\n"
            "❌ دوز — 1.7x\n"
            "🧠 کوییز — 1.8x\n"
            "⚽ پنالتی — 2x\n"
            "🎰 کازینو — تا 15x\n\n"
            "یکی رو انتخاب کن:",
            games_menu_kb())
        return

    if data == "game:casino":
        await query.answer()
        await safe_edit(query,
            "🎰 <b>کازینو زر</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 حداقل ورودی: <b>10,000</b> زرکوین\n"
            "💵 کارمزد: <b>10%</b> از جایزه\n\n"
            "🎲 بازی‌ها:\n"
            "• 🎰 اسلات — تا 15 برابر\n"
            "• 🎲 تاس — تا 3 برابر\n"
            "• 🪙 شیر یا خط — 2 برابر\n"
            "• 🃏 کارت شانس — 4 برابر\n\n"
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
                f"💵 کارمزد: <b>10%</b> از جایزه\n\n"
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
        cg = parts[2]
        pending = casino_pending.get(user_id)
        if not pending or pending["game"] != cg:
            await query.answer("❌ بازی فعالی نداری", show_alert=True); return
        casino_pending.pop(user_id, None)
        entry = pending["entry"]
        
        if cg == "dice":
            # ✅ در بازی تاس، نوع انتخاب (exact/parity) و مقدار فرستاده میشه
            choice_type = parts[3]
            choice_val = parts[4]
            await resolve_dice(query, entry, choice_type, choice_val)
        elif cg == "coin":
            await resolve_coin(query, entry, parts[3])
        elif cg == "card":
            await resolve_card(query, entry, parts[3])
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
        f"👥 بازیکنان: {g['players']}\n"
        f"💵 کارمزد: <b>10%</b> از جایزه\n\n"
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
                  f"💵 کارمزد 10%: {fmt(comm)}\n"
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
                    f"💵 کارمزد 10%: {fmt(comm)}\n"
                    f"✅ دریافتی: <b>{fmt(prize)}</b>")
        room["status"] = "finished"
        rooms.pop(room_id, None)
        await safe_edit(query, text, back_games_kb())
        return
    room["turn"] = p2 if room["turn"] == p1 else p1
    await render_ttt(query, room)

async def quiz_answer(query, room_id, idx):
    room = rooms.get(room_id)
    if not room or room["status"] != "playing" or room.get("answered"):
        await query.answer("❌ بازی تمام شد", show_alert=True); return
    user_id = query.from_user.id
    if user_id not in room["players"]:
        await query.answer("❌ تو بازیکن نیستی", show_alert=True); return
    q = room["question"]
    if idx == q["ans"]:
        room["answered"] = True
        full_prize = int(room["entry"] * GAMES["quiz"]["mult"])
        prize, comm = apply_commission(full_prize)
        await add_balance(user_id, prize)
        room["status"] = "finished"
        rooms.pop(room_id, None)
        await query.answer("✅ درست بود!", show_alert=True)
        text = (f"🧠 <b>نتیجه کوییز</b>\n"
                f"❓ {escape(q['q'])}\n\n"
                f"🏆 برنده: <b>{escape(query.from_user.first_name)}</b>\n"
                f"💰 جایزه: {fmt(full_prize)}\n"
                f"💵 کارمزد 10%: {fmt(comm)}\n"
                f"✅ دریافتی: <b>{fmt(prize)}</b>")
        await safe_edit(query, text, back_games_kb())
    else:
        await query.answer("❌ اشتباه! دوباره تلاش کن", show_alert=True)

async def penalty_entry_done(update, entry: int):
    user_id = update.effective_user.id
    penalty_games[user_id] = {"entry": entry, "chat_id": update.effective_chat.id}
    await update.message.reply_text(
        f"⚽ <b>پنالتی</b>\n"
        f"💰 ورودی: {fmt(entry)}\n\n"
        f"آماده‌ای؟ شوت کن!",
        parse_mode=ParseMode.HTML, reply_markup=penalty_kb())

async def penalty_shoot(query, context):
    user_id = query.from_user.id
    game = penalty_games.get(user_id)
    if not game:
        await query.answer("❌ بازی فعالی نداری", show_alert=True); return
    penalty_games.pop(user_id, None)
    if random.random() < 0.5:
        full_prize = game["entry"] * 2
        prize, comm = apply_commission(full_prize)
        await add_balance(user_id, prize)
        await safe_edit(query,
            f"⚽ <b>گل!!!</b> 🎉\n\n"
            f"💰 جایزه: {fmt(full_prize)}\n"
            f"💵 کارمزد 10%: {fmt(comm)}\n"
            f"✅ دریافتی: <b>{fmt(prize)}</b> زرکوین",
            back_games_kb())
    else:
        await safe_edit(query,
            f"⚽ <b>دروازه‌بان گرفت!</b> 😢\n\n"
            f"💸 متأسفانه {fmt(game['entry'])} زرکوین از دست رفت.",
            back_games_kb())


# ============================== بازی کازینو ==============================
async def play_slots_message(update, user_id: int, entry: int):
    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    reels_str = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        if reels[0] == "7️⃣":
            mult = 15
        elif reels[0] == "⭐":
            mult = 8
        else:
            mult = 4
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        mult = 1.7
    else:
        mult = 0

    if mult > 0:
        full_prize = int(entry * mult)
        prize, comm = apply_commission(full_prize)
        await add_balance(user_id, prize)
        text = (
            f"🎰 <b>اسلات</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{reels_str}</b>\n\n"
            f"🎉 <b>بردی!</b>\n"
            f"💰 جایزه: {fmt(full_prize)}\n"
            f"💵 کارمزد 10%: {fmt(comm)}\n"
            f"✅ دریافتی: <b>{fmt(prize)}</b> زرکوین"
        )
    else:
        text = (
            f"🎰 <b>اسلات</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{reels_str}</b>\n\n"
            f"😢 باختی! {fmt(entry)} زرکوین از دست رفت."
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=casino_back_kb())

# ✅ تابع جدید تاس با ایموجی تلگرام
async def resolve_dice(query, entry: int, choice_type: str, choice_val: str):
    # ارسال ایموجی تاس
    try:
        dice_msg = await query.message.reply_dice(emoji="🎲")
    except Exception:
        dice_msg = await query.message.chat.send_dice(emoji="🎲")
    
    # صبر برای انیمیشن
    await asyncio.sleep(4)
    
    result_num = dice_msg.dice.value
    
    header = (
        f"🎲 <b>تاس</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 نتیجه: <b>{result_num}</b>\n"
        f"انتخاب تو: "
    )
    
    is_win = False
    multiplier = 0
    
    if choice_type == "exact":
        header += f"دقیقاً {choice_val}\n\n"
        if result_num == int(choice_val):
            is_win = True
            multiplier = 3.0
    else: # parity
        if choice_val == "even":
            header += "زوج\n\n"
            if result_num % 2 == 0:
                is_win = True
                multiplier = 1.5
        else:
            header += "فرد\n\n"
            if result_num % 2 != 0:
                is_win = True
                multiplier = 1.5

    if is_win:
        full_prize = int(entry * multiplier)
        prize, comm = apply_commission(full_prize)
        await add_balance(query.from_user.id, prize)
        text = header + (
            f"🎉 <b>بردی!</b>\n"
            f"💰 جایزه: {fmt(full_prize)}\n"
            f"💵 کارمزد 10%: {fmt(comm)}\n"
            f"✅ دریافتی: <b>{fmt(prize)}</b> زرکوین"
        )
    else:
        text = header + f"😢 باختی! {fmt(entry)} زرکوین از دست رفت."
        
    await safe_edit(query, text, casino_back_kb())


async def resolve_coin(query, entry: int, choice: str):
    result = random.choice(["heads", "tails"])
    result_name = "شیر 🦁" if result == "heads" else "خط ✖️"
    choice_name = "شیر 🦁" if choice == "heads" else "خط ✖️"
    header = (
        f"🪙 <b>شیر یا خط</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 نتیجه: <b>{result_name}</b>\n"
        f"انتخاب تو: {choice_name}\n\n"
    )
    if result == choice:
        full_prize = entry * 2
        prize, comm = apply_commission(full_prize)
        await add_balance(query.from_user.id, prize)
        text = header + (
            f"🎉 <b>بردی!</b>\n"
            f"💰 جایزه: {fmt(full_prize)}\n"
            f"💵 کارمزد 10%: {fmt(comm)}\n"
            f"✅ دریافتی: <b>{fmt(prize)}</b> زرکوین"
        )
    else:
        text = header + f"😢 باختی! {fmt(entry)} زرکوین از دست رفت."
    await safe_edit(query, text, casino_back_kb())

async def resolve_card(query, entry: int, choice: str):
    result = random.choice(list(CARD_SUITS.keys()))
    header = (
        f"🃏 <b>کارت شانس</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 کارت: <b>{CARD_SUITS[result]}</b> ({CARD_SUITS_FA[result]})\n"
        f"انتخاب تو: {CARD_SUITS[choice]} ({CARD_SUITS_FA[choice]})\n\n"
    )
    if result == choice:
        full_prize = entry * 4
        prize, comm = apply_commission(full_prize)
        await add_balance(query.from_user.id, prize)
        text = header + (
            f"🎉 <b>بردی!</b>\n"
            f"💰 جایزه: {fmt(full_prize)}\n"
            f"💵 کارمزد 10%: {fmt(comm)}\n"
            f"✅ دریافتی: <b>{fmt(prize)}</b> زرکوین"
        )
    else:
        text = header + f"😢 باختی! {fmt(entry)} زرکوین از دست رفت."
    await safe_edit(query, text, casino_back_kb())


# ============================== انتقال ==============================
async def confirm_transfer(query, owner_id: int):
    if query.from_user.id != owner_id:
        await query.answer("❌ این دکمه برای تو نیست", show_alert=True); return
    pending = pending_transfers.pop(owner_id, None)
    if not pending:
        await query.answer("❌ انتقال منقضی شده", show_alert=True); return
    if not await transfer_coins(owner_id, pending["recipient_id"], pending["amount"], pending["fee"]):
        await query.answer("❌ موجودی کافی نیست", show_alert=True)
        await safe_edit(query, "❌ انتقال انجام نشد.", back_main_kb())
        return
    await safe_edit(query,
        f"✅ <b>انتقال انجام شد!</b>\n\n"
        f"👤 گیرنده: {escape(pending['recipient_name'])}\n"
        f"💰 مبلغ: <b>{fmt(pending['amount'])}</b>\n"
        f"💵 کارمزد: <b>{fmt(pending['fee'])}</b>",
        back_main_kb())
    try:
        await query.bot.send_message(
            pending["recipient_id"],
            f"🎁 <b>زرکوین دریافت کردی!</b>\n\n"
            f"💰 مبلغ: <b>{fmt(pending['amount'])}</b> زرکوین\n"
            f"👤 از طرف: {escape(query.from_user.first_name)}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


# ============================== ادمین ==============================
async def owner_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return
    m = re.match(r"^انتقال زرکوین\s+([\d۰-۹,،]+)\s*$", msg.text or "")
    if not m:
        return
    amount = parse_amount(m.group(1))
    if not amount:
        await msg.reply_text("❌ مبلغ نامعتبر"); return
    target = msg.reply_to_message.from_user
    if target.is_bot:
        await msg.reply_text("❌ به بات نمی‌شه انتقال داد"); return
    await ensure_user(target)
    await add_balance(target.id, amount)
    await msg.reply_text(
        f"✅ <b>{fmt(amount)}</b> زرکوین به {escape(target.first_name)} واریز شد.",
        parse_mode=ParseMode.HTML)


# ============================== پیام‌های متنی ==============================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    if text == "لغو" and update.message.reply_to_message:
        await handle_cancel(user_id, update.message)
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state["action"]

    if action == "bank_deposit":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        await ensure_user(user)
        ok = await bank_deposit(user_id, amount)
        user_states.pop(user_id, None)
        if ok:
            await update.message.reply_text(
                f"✅ <b>{fmt(amount)}</b> زرکوین به بانک واریز شد.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        else:
            await update.message.reply_text("❌ موجودی کافی نیست", reply_markup=main_menu_kb())
        return

    if action == "bank_withdraw":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        ok = await bank_withdraw(user_id, amount)
        user_states.pop(user_id, None)
        if ok:
            await update.message.reply_text(
                f"✅ <b>{fmt(amount)}</b> زرکوین از بانک برداشت شد.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        else:
            await update.message.reply_text("❌ موجودی بانک کافی نیست", reply_markup=main_menu_kb())
        return

    if action == "game_entry":
        gk = state["game"]
        g = GAMES.get(gk)
        if not g:
            user_states.pop(user_id, None); return
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]:
            await update.message.reply_text(f"❌ حداقل ورودی {fmt(g['min'])} است"); return
        await ensure_user(user)
        if not await deduct_balance(user_id, amount):
            await update.message.reply_text("❌ موجودی کافی نیست"); return
        user_states.pop(user_id, None)

        if gk == "penalty":
            await penalty_entry_done(update, amount)
            return

        rid = new_room_id()
        rooms[rid] = {
            "id": rid, "game": gk, "entry": amount, "creator": user_id,
            "players": [user_id], "status": "waiting",
            "user_names": {user_id: user.first_name or str(user_id)},
            "chat_id": update.effective_chat.id, "created_at": now_iso(),
        }
        text_out = (
            f"{g['emoji']} <b>{g['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 ورودی: <b>{fmt(amount)}</b>\n\n"
            f"👤 بازیکن ۱: {escape(user.first_name)}\n\n"
            f"⏳ منتظر بازیکن دوم...")
        await update.message.reply_text(text_out, parse_mode=ParseMode.HTML,
                                         reply_markup=join_room_kb(rid, gk))
        return

    if action == "casino_entry":
        cg = state["game"]
        g = CASINO_GAMES.get(cg)
        if not g:
            user_states.pop(user_id, None); return
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        if amount < g["min"]:
            await update.message.reply_text(f"❌ حداقل ورودی {fmt(g['min'])} است"); return
        await ensure_user(user)
        if not await deduct_balance(user_id, amount):
            await update.message.reply_text("❌ موجودی کافی نیست"); return
        user_states.pop(user_id, None)

        if cg == "slots":
            await play_slots_message(update, user_id, amount)
            return

        casino_pending[user_id] = {"entry": amount, "game": cg,
                                    "chat_id": update.effective_chat.id}
        if cg == "dice":
            await update.message.reply_text(
                f"🎲 <b>تاس</b>\n"
                f"💰 ورودی: {fmt(amount)}\n\n"
                f"⚠️ <b>دقت کن! اگر اشتباه حدس بزنی پولت برنمی‌گرده.</b>\n\n"
                f"انتخاب کن:",
                parse_mode=ParseMode.HTML, reply_markup=casino_dice_kb())
        elif cg == "coin":
            await update.message.reply_text(
                f"🪙 <b>شیر یا خط</b>\n💰 ورودی: {fmt(amount)}\n\nانتخاب کن:",
                parse_mode=ParseMode.HTML, reply_markup=casino_coin_kb())
        elif cg == "card":
            await update.message.reply_text(
                f"🃏 <b>کارت شانس</b>\n💰 ورودی: {fmt(amount)}\n\nکدام خال؟",
                parse_mode=ParseMode.HTML, reply_markup=casino_card_kb())
        return

    if action == "transfer_amount":
        amount = parse_amount(text)
        if not amount:
            await update.message.reply_text("❌ مبلغ نامعتبر"); return
        await ensure_user(user)
        fee = int(amount * TRANSFER_FEE_RATE) if amount > TRANSFER_FEE_MIN else 0
        total = amount + fee
        u = await get_user(user_id)
        if int(u["balance"]) < total:
            await update.message.reply_text(
                f"❌ موجودی کافی نیست (نیاز: {fmt(total)})"); return
        user_states[user_id] = {"action": "transfer_card", "amount": amount, "fee": fee}
        await update.message.reply_text(
            f"💸 مبلغ: <b>{fmt(amount)}</b>\n"
            f"💵 کارمزد: <b>{fmt(fee)}</b>\n"
            f"📊 مجموع کسر: <b>{fmt(total)}</b>\n\n"
            f"شماره کارت مقصد رو بفرست:",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return

    if action == "transfer_card":
        recipient = await find_user_by_card(text)
        if not recipient:
            await update.message.reply_text("❌ کاربری با این شماره کارت پیدا نشد"); return
        if recipient["user_id"] == user_id:
            await update.message.reply_text("❌ به خودت نمی‌تونی انتقال بدی"); return
        amount = state["amount"]
        fee = state["fee"]
        total = amount + fee
        sender = await get_user(user_id)
        if int(sender["balance"]) < total:
            user_states.pop(user_id, None)
            await update.message.reply_text("❌ موجودی کافی نیست"); return
        pending_transfers[user_id] = {
            "recipient_id": recipient["user_id"],
            "recipient_name": recipient["first_name"] or str(recipient["user_id"]),
            "amount": amount, "fee": fee, "total": total,
        }
        user_states.pop(user_id, None)
        await update.message.reply_text(
            f"💸 <b>تأیید انتقال</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 گیرنده: {escape(recipient['first_name'])}\n"
            f"💳 کارت: <code>{format_card(recipient['card_number'])}</code>\n"
            f"💰 مبلغ: <b>{fmt(amount)}</b>\n"
            f"💵 کارمزد: <b>{fmt(fee)}</b>\n"
            f"📊 مجموع کسر: <b>{fmt(total)}</b>\n\n"
            f"آیا تأیید می‌کنی؟",
            parse_mode=ParseMode.HTML, reply_markup=transfer_confirm_kb(user_id))
        return


# ============================== خوش‌آمد گروه ==============================
async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if not cm or not update.effective_chat:
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    if cm.new_chat_member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and \
       cm.old_chat_member.status in (ChatMember.LEFT, ChatMember.KICKED):
        try:
            await context.bot.send_message(
                update.effective_chat.id,
                "✨ <b>زرکوین بات در این گروه فعال شد!</b> ✨\n\n"
                "💡 برای شروع بنویس: <code>زربات</code>\n"
                "🎮 برای بازی‌ها بنویس: <code>زر بازی</code>",
                parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("welcome failed")


# ============================== راهنما ==============================
HELP_TEXT = (
    "📚 <b>راهنمای زرکوین بات</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🪙 <b>زرکوین چیه؟</b>\n"
    "واحد پول بازی، قابل کسب از طریق خرید ملک، استخدام کارگر، سود بانکی و برد در بازی‌ها.\n\n"
    "🎯 <b>دستورات</b>\n"
    "• <code>زربات</code> — باز کردن منوی اصلی\n"
    "• <code>زر بازی</code> — رفتن به بخش بازی‌ها\n"
    "• <code>/start</code> یا <code>/menu</code> — منوی اصلی\n\n"
    "🏦 <b>بانک</b>\n"
    "سود روزانه 2% که هر شب ساعت 00:00 واریز میشه.\n"
    "شماره کارت اختصاصی بر اساس آیدی عددی.\n\n"
    "🏠 <b>ملک‌ها</b> (حداکثر 5 عدد از هر نوع)\n"
    "🛒 سوپرمارکت 500K → 50K/روز\n"
    "🍎 میوه‌فروشی 800K → 80K/روز\n"
    "🥩 قصابی 1M → 100K/روز\n"
    "💊 داروخانه 1.8M → 180K/روز\n"
    "💈 آرایشگاه 2.2M → 220K/روز\n"
    "👕 پوشاک 3M → 300K/روز\n"
    "📚 کتاب‌فروشی 3.5M → 350K/روز\n"
    "📱 موبایل 4M → 400K/روز\n\n"
    "👷 <b>کارگرها</b> (حداکثر 5 عدد از هر نوع)\n"
    "👨‍🏫 معلم 300K → 30K/روز\n"
    "👨‍⚕️ پزشک 500K → 50K/روز\n"
    "🚕 راننده 800K → 80K/روز\n"
    "👨‍💻 برنامه‌نویس 1.2M → 120K/روز\n"
    "🤖 متخصص AI 2M → 200K/روز\n\n"
    "🎮 <b>بازی‌ها</b> (حداقل 1,000 زرکوین)\n"
    "✊ سنگ کاغذ قیچی — 1.5x\n"
    "❌ دوز — 1.7x\n"
    "🧠 کوییز — 1.8x\n"
    "⚽ پنالتی — 2x\n\n"
    "🎰 <b>کازینو</b> (حداقل 10,000 زرکوین)\n"
    "🎰 اسلات — تا 15x\n"
    "🎲 تاس (دقیق 3x | زوج/فرد 1.5x) — بدون بازگشت پول در صورت باخت\n"
    "🪙 شیر یا خط — 2x\n"
    "🃏 کارت شانس — 4x\n\n"
    "💵 <b>کارمزد بات</b>: 10% از هر برد\n\n"
    "💸 <b>انتقال</b>: با شماره کارت. بالای 1M، 1% کارمزد.\n\n"
    "👑 <b>اهدا از طرف مالک</b>\n"
    "مالک با ریپلای روی پیام کسی بنویسه:\n"
    "<code>انتقال زرکوین 5000</code>"
)


# ============================== main ==============================
async def post_init(app: Application):
    await init_db_pool()
    await init_db()
    try:
        await daily_payout()
    except Exception:
        logger.exception("initial daily_payout failed")
    app.job_queue.run_daily(
        daily_payout, time=time(hour=0, minute=0, tzinfo=TEHRAN), name="daily_payout")


async def post_shutdown(app: Application):
    await close_db_pool()


def main():
    app = Application.builder().token(BOT_TOKEN) \
        .post_init(post_init).post_shutdown(post_shutdown).build()

    app.add_handler(MessageHandler(filters.Regex(r"^زربات$"), cmd_zarbat))
    app.add_handler(MessageHandler(filters.Regex(r"^زر\s*بازی$"), cmd_zarbazi))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))

    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(
        filters.Regex(r"^انتقال زرکوین\s+[\d۰-۹,،]+"), owner_give))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🚀 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
