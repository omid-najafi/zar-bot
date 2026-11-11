# -*- coding: utf-8 -*-
"""💀 بازار سیاه ربات زرکوین"""
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
import utils, db, config

logger = logging.getLogger("zarcoin")

# تیتر هر دسته
CATEGORY_TITLES = {
    "launcher": "🚀 وسایل شلیک",
    "projectile": "🚀 مهمات",
    "defense": "🛡️ سیستم‌های دفاعی",
}


def _get_items_by_type(item_type: str) -> list[tuple[str, dict]]:
    """گرفتن آیتم‌های یک دسته"""
    return [(k, v) for k, v in config.BLACKMARKET_ITEMS.items() if v.get("type") == item_type]


def _total_pages() -> int:
    """تعداد کل صفحات"""
    total = len(config.BLACKMARKET_ITEMS)
    per_page = config.BLACKMARKET_PER_PAGE
    return max(1, (total + per_page - 1) // per_page)


def _page_items(page: int) -> list[tuple[str, dict]]:
    """آیتم‌های یک صفحه"""
    per_page = config.BLACKMARKET_PER_PAGE
    all_items = list(config.BLACKMARKET_ITEMS.items())
    start = page * per_page
    end = start + per_page
    return all_items[start:end]


def _item_kb(item_key: str, item: dict, count: int = 0, user_level: int = 0) -> InlineKeyboardMarkup:
    """کیبورد تأیید خرید یک آیتم"""
    # اگر آیتم قفل لول داره و کاربر هنوز به لول لازم نرسیده، دکمه خرید نشون نده
    locked = item_key in config.LAUNCHER_LEVEL_LOCKED and user_level < config.LAUNCHER_MIN_LEVEL
    if locked:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔒 نیاز به لول {config.LAUNCHER_MIN_LEVEL}", callback_data="bm:noop")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"bm:menu:0")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بخر", callback_data=f"bm:buy:{item_key}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"bm:menu:0")],
    ])


def _menu_kb(page: int, counts: dict, user_level: int = 0) -> InlineKeyboardMarkup:
    """کیبورد صفحه منو با صفحه‌بندی"""
    items = _page_items(page)
    rows = []
    for item_key, item in items:
        count = counts.get(item_key, 0)
        # نمایش تعداد دارایی در صورت وجود
        count_str = f" ×{count}" if count > 0 else ""
        # نشونه قفل برای لانچرهای قفل‌شده
        locked = item_key in config.LAUNCHER_LEVEL_LOCKED and user_level < config.LAUNCHER_MIN_LEVEL
        lock_str = f" 🔴 لول {config.LAUNCHER_MIN_LEVEL}+" if locked else ""
        label = f"{item['emoji']} {item['name']}\n💰 {utils.fmt(item['price'])}{count_str}{lock_str}"
        rows.append([InlineKeyboardButton(label, callback_data=f"bm:select:{item_key}")])

    # دکمه‌های صفحه‌بندی
    total_pages = _total_pages()
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(f"⬅️ قبلی", callback_data=f"bm:menu:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="bm:noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(f"➡️ بعدی", callback_data=f"bm:menu:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("🎒 اینونتوری من", callback_data="bm:inventory")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def _item_type_text(item_type: str) -> str:
    """توضیح نوع آیتم"""
    if item_type == "launcher":
        return "🚀 وسیله شلیک — برای شلیک مهمات الزامی است"
    elif item_type == "projectile":
        return "🚀 مهمات — با وسیله شلیک مناسب استفاده می‌شود"
    elif item_type == "defense":
        return "🛡️ سیستم دفاعی — از شما در برابر حملات محافظت می‌کند"
    return ""


async def _build_item_text(item_key: str, item: dict, count: int = 0, user_level: int = 0) -> str:
    """ساخت متن جزئیات آیتم"""
    # بررسی قفل لول
    locked = item_key in config.LAUNCHER_LEVEL_LOCKED and user_level < config.LAUNCHER_MIN_LEVEL

    text = (
        f"{item['emoji']} <b>{item['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    if locked:
        text += f"🔒 <b>قفل شده!</b> نیاز به لول {config.LAUNCHER_MIN_LEVEL}\n"
        text += f"⭐ لول فعلی شما: {user_level}\n\n"

    text += f"💰 قیمت: <b>{utils.fmt(item['price'])}</b> زرکوین\n"
    text += f"📋 نوع: {_item_type_text(item['type'])}\n"

    if count > 0:
        text += f"🎒 تعداد دارایی: <b>{count}</b>\n"

    # اطلاعات اضافی برای مهمات
    if item["type"] == "projectile":
        text += f"💥 درصد تخریب: <b>{int(item['damage'] * 100)}%</b>\n"
        text += f"🎯 دستور شلیک: <code>{item['command']}</code>\n"
        if item.get("defense_type"):
            text += f"🛡️ قابل دفاع: بله\n"
        else:
            text += f"🛡️ قابل دفاع: خیر (بمب)\n"
    elif item["type"] == "launcher":
        launches = item.get("launches", [])
        if launches:
            text += f"🎯 می‌تونی این مهمات رو شلیک کنی:\n"
            for p_key in launches:
                p = config.BLACKMARKET_ITEMS.get(p_key, {})
                text += f"   • {p.get('emoji', '')} {p.get('name', '')} ({int(p.get('damage', 0) * 100)}%)\n"
    elif item["type"] == "defense":
        text += f"🛡️ احتمال دفاع: <b>{int(item['defense_chance'] * 100)}%</b>\n"

    if not locked:
        text += "\nمطمئنی؟"
    else:
        text += f"\n⚠️ برای خرید و استفاده، باید به لول {config.LAUNCHER_MIN_LEVEL} برسی!"
    return text


async def _build_inventory_text(user_id: int) -> str:
    """ساخت متن اینونتوری کاربر"""
    counts = await db.get_inventory_counts(user_id)
    text = "🎒 <b>اینونتوری من</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if not counts:
        text += "📭 هنوز چیزی نخریدی.\n\n"
        text += "برای خرید، به منوی بازار سیاه برگرد."
    else:
        # گروه‌بندی بر اساس نوع
        for item_type, title in CATEGORY_TITLES.items():
            items_in_type = [(k, v) for k, v in config.BLACKMARKET_ITEMS.items()
                             if v.get("type") == item_type and counts.get(k, 0) > 0]
            if items_in_type:
                text += f"<b>{title}:</b>\n"
                for k, item in items_in_type:
                    cnt = counts.get(k, 0)
                    text += f"   {item['emoji']} {item['name']}: <b>{cnt}</b>\n"
                text += "\n"
    return text


def _inventory_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به بازار سیاه", callback_data="bm:menu:0")],
    ])


async def handle_callback(query, context, data, user_id):
    try:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else "menu"

        # ─────────── منو با صفحه‌بندی ───────────
        if action == "menu":
            page = int(parts[2]) if len(parts) > 2 else 0
            page = max(0, min(page, _total_pages() - 1))
            await db.ensure_user(query.from_user)
            counts = await db.get_inventory_counts(user_id)
            # گرفتن لول کاربر برای نمایش قفل‌ها
            user_data = await db.get_user(user_id)
            total_xp = int(user_data.get("total_xp", 0)) if user_data else 0
            user_level, _, _ = utils.calc_level(total_xp)
            text = (
                "💀 <b>بازار سیاه</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "آیتم‌های نظامی برای حمله به کاربران دیگر.\n"
                "برای خرید، روی آیتم مورد نظر بزن.\n\n"
                "📦 تعداد کل آیتم‌ها: " + str(len(config.BLACKMARKET_ITEMS)) + "\n"
                "📄 صفحه " + str(page + 1) + " از " + str(_total_pages())
            )
            msg = await utils.safe_edit(query, text, _menu_kb(page, counts, user_level))
            if msg:
                utils.remember_owner(msg, user_id)
            await utils.safe_answer(query)
            return

        # ─────────── اینونتوری ───────────
        if action == "inventory":
            await db.ensure_user(query.from_user)
            text = await _build_inventory_text(user_id)
            msg = await utils.safe_edit(query, text, _inventory_kb())
            if msg:
                utils.remember_owner(msg, user_id)
            await utils.safe_answer(query)
            return

        # ─────────── انتخاب آیتم (نمایش جزئیات) ───────────
        if action == "select":
            item_key = parts[2] if len(parts) > 2 else ""
            item = config.BLACKMARKET_ITEMS.get(item_key)
            if not item:
                await utils.safe_answer(query, "❌ آیتم نامعتبر", show_alert=True)
                return
            counts = await db.get_inventory_counts(user_id)
            count = counts.get(item_key, 0)
            # گرفتن لول کاربر
            user_data = await db.get_user(user_id)
            total_xp = int(user_data.get("total_xp", 0)) if user_data else 0
            user_level, _, _ = utils.calc_level(total_xp)
            text = await _build_item_text(item_key, item, count, user_level)
            msg = await utils.safe_edit(query, text, _item_kb(item_key, item, count, user_level))
            if msg:
                utils.remember_owner(msg, user_id)
            await utils.safe_answer(query)
            return

        # ─────────── خرید ───────────
        if action == "buy":
            item_key = parts[2] if len(parts) > 2 else ""
            item = config.BLACKMARKET_ITEMS.get(item_key)
            if not item:
                await utils.safe_answer(query, "❌ آیتم نامعتبر", show_alert=True)
                return
            # بررسی شرط لول برای لانچرهای قفل‌شده
            user_data = await db.get_user(user_id)
            total_xp = int(user_data.get("total_xp", 0)) if user_data else 0
            user_level, _, _ = utils.calc_level(total_xp)
            if item_key in config.LAUNCHER_LEVEL_LOCKED and user_level < config.LAUNCHER_MIN_LEVEL:
                await utils.safe_answer(
                    query,
                    f"🔒 برای خرید {item['name']} باید به لول {config.LAUNCHER_MIN_LEVEL} برسی!\n"
                    f"لول فعلی شما: {user_level}",
                    show_alert=True)
                return
            r = await db.buy_inventory_item(user_id, item_key)
            if r == "ok":
                await utils.safe_answer(query, f"✅ {item['name']} خریداری شد!", show_alert=True)
            elif r == "balance":
                await utils.safe_answer(query, "❌ موجودی کافی نیست!", show_alert=True)
            else:
                await utils.safe_answer(query, "❌ خطا", show_alert=True)
            # برگشت به صفحه جزئیات آیتم
            counts = await db.get_inventory_counts(user_id)
            count = counts.get(item_key, 0)
            text = await _build_item_text(item_key, item, count, user_level)
            # اگر خرید موفق بود و هنوز می‌تونه بخره، دکمه خرید دوباره نشون بده
            user = await db.get_user(user_id)
            can_buy_more = user and int(user["balance"]) >= item["price"]
            if can_buy_more and r == "ok":
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ خرید دوباره", callback_data=f"bm:buy:{item_key}")],
                    [InlineKeyboardButton("🔙 بازگشت به بازار سیاه", callback_data="bm:menu:0")],
                ])
            else:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت به بازار سیاه", callback_data="bm:menu:0")],
                ])
            msg = await utils.safe_edit(query, text, kb)
            if msg:
                utils.remember_owner(msg, user_id)
            return

        # ─────────── noop ───────────
        if action == "noop":
            await utils.safe_answer(query)
            return

        await utils.safe_answer(query)
    except Exception as e:
        logger.exception(f"Blackmarket error: {e}")
        try:
            await utils.safe_answer(query, "❌ خطا", show_alert=True)
        except Exception:
            pass
