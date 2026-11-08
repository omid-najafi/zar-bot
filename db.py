# -*- coding: utf-8 -*-
import logging
import random
import aiomysql
from datetime import datetime
import config
import utils

logger = logging.getLogger("zarcoin")
db_pool = None

SCHEMA_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username VARCHAR(255), first_name VARCHAR(255), balance BIGINT NOT NULL DEFAULT 0, bank_balance BIGINT NOT NULL DEFAULT 0, card_number VARCHAR(16) UNIQUE, last_daily VARCHAR(10), created_at VARCHAR(32) NOT NULL, INDEX idx_card (card_number)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    "CREATE TABLE IF NOT EXISTS assets (id INT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, asset_type VARCHAR(32) NOT NULL, asset_key VARCHAR(64) NOT NULL, purchase_price BIGINT NOT NULL, daily_income BIGINT NOT NULL, purchased_at VARCHAR(32) NOT NULL, INDEX idx_user_asset (user_id, asset_type), INDEX idx_user_key (user_id, asset_key)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    "CREATE TABLE IF NOT EXISTS user_missions (id INT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, mission_key VARCHAR(64) NOT NULL, mission_date VARCHAR(10) NOT NULL, progress INT DEFAULT 0, target INT NOT NULL, xp_reward INT NOT NULL, completed TINYINT DEFAULT 0, INDEX idx_user_date (user_id, mission_date)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
]

# ✅ ستون‌های جدید که باید به جدول users اضافه بشن
EXTRA_COLUMNS = [
    ("total_xp", "BIGINT NOT NULL DEFAULT 0"),
    ("level", "INT NOT NULL DEFAULT 1"),
    ("kabareh_unlocked", "TINYINT NOT NULL DEFAULT 0"),
    ("last_zar", "VARCHAR(32) DEFAULT NULL"),
    ("last_mission_date", "VARCHAR(10) DEFAULT NULL"),
]


async def init_db_pool():
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
        db=config.DB_NAME, autocommit=False, minsize=2, maxsize=30, charset="utf8mb4")
    logger.info("✅ Connection Pool به MySQL ساخته شد.")


async def close_db_pool():
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()


async def init_db():
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            for stmt in SCHEMA_STATEMENTS:
                await cur.execute(stmt)
            # اضافه کردن ستون‌های جدید (اگر وجود نداشته باشند)
            for col_name, col_type in EXTRA_COLUMNS:
                try:
                    await cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ ستون {col_name} اضافه شد.")
                except Exception:
                    pass  # ستون از قبل وجود داره
            await conn.commit()
    logger.info("✅ دیتابیس آماده است.")


async def ensure_user(user) -> dict:
    if user.id in utils.user_cache:
        return utils.user_cache[user.id]

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "INSERT IGNORE INTO users (user_id, username, first_name, balance, bank_balance, card_number, created_at) VALUES (%s, %s, %s, %s, 0, %s, %s)",
                (user.id, user.username, user.first_name, config.START_BALANCE, utils.card_number_for(user.id), utils.now_iso())
            )
            await cur.execute("UPDATE users SET username=%s, first_name=%s WHERE user_id=%s", (user.username, user.first_name, user.id))
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user.id,))
            row = await cur.fetchone()
            await conn.commit()
            user_dict = dict(row)
            utils.user_cache[user.id] = user_dict
            return user_dict


async def get_user(user_id: int):
    if user_id in utils.user_cache:
        return utils.user_cache[user_id]

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            if row:
                user_dict = dict(row)
                utils.user_cache[user_id] = user_dict
                return user_dict
            return None


async def add_balance(user_id: int, amount: int):
    if amount <= 0: return
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, user_id))
            await conn.commit()


async def deduct_balance(user_id: int, amount: int) -> bool:
    if amount <= 0: return False
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s", (amount, user_id, amount))
            await conn.commit()
            return cur.rowcount == 1


async def bank_deposit(user_id: int, amount: int) -> bool:
    if amount <= 0: return False
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET balance = balance - %s, bank_balance = bank_balance + %s WHERE user_id=%s AND balance >= %s", (amount, amount, user_id, amount))
                if cur.rowcount != 1:
                    await conn.rollback(); return False
            await conn.commit(); return True
        except Exception:
            await conn.rollback(); return False


async def bank_withdraw(user_id: int, amount: int) -> bool:
    if amount <= 0: return False
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET bank_balance = bank_balance - %s, balance = balance + %s WHERE user_id=%s AND bank_balance >= %s", (amount, amount, user_id, amount))
                if cur.rowcount != 1:
                    await conn.rollback(); return False
            await conn.commit(); return True
        except Exception:
            await conn.rollback(); return False


async def transfer_coins(sender_id: int, recipient_id: int, amount: int, fee: int) -> bool:
    total = amount + fee
    utils.invalidate_cache(sender_id); utils.invalidate_cache(recipient_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s", (total, sender_id, total))
                if cur.rowcount != 1:
                    await conn.rollback(); return False
                await cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, recipient_id))
            await conn.commit(); return True
        except Exception:
            await conn.rollback(); return False


async def get_assets_summary(user_id: int) -> dict:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT asset_key, COUNT(*) as count, SUM(daily_income) as total_income FROM assets WHERE user_id=%s GROUP BY asset_key", (user_id,))
            rows = await cur.fetchall()
            return {r["asset_key"]: {"count": int(r["count"]), "total_income": int(r["total_income"])} for r in rows}


async def get_assets(user_id: int, asset_type: str) -> list[dict]:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM assets WHERE user_id=%s AND asset_type=%s ORDER BY id ASC", (user_id, asset_type))
            return [dict(r) for r in await cur.fetchall()]


async def buy_asset(user_id: int, asset_type: str, asset_key: str, price: int, income: int) -> str:
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM assets WHERE user_id=%s AND asset_key=%s", (user_id, asset_key))
                count = int((await cur.fetchone())[0])
                if count >= config.MAX_PER_KEY:
                    await conn.rollback(); return "limit"
                await cur.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s", (price, user_id, price))
                if cur.rowcount != 1:
                    await conn.rollback(); return "balance"
                await cur.execute("INSERT INTO assets (user_id, asset_type, asset_key, purchase_price, daily_income, purchased_at) VALUES (%s, %s, %s, %s, %s, %s)", (user_id, asset_type, asset_key, price, income, utils.now_iso()))
            await conn.commit(); return "ok"
        except Exception:
            await conn.rollback(); return "error"


async def find_user_by_card(card: str):
    digits = "".join(ch for ch in (card or "") if ch.isdigit())
    if len(digits) != 16: return None
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE card_number=%s", (digits,))
            row = await cur.fetchone()
            return dict(row) if row else None


async def daily_payout(context=None):
    async with utils.daily_lock:
        today = datetime.now(utils.TEHRAN).date()
        today_iso = today.isoformat()
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT user_id, SUM(daily_income) as total FROM assets GROUP BY user_id")
                incomes = {r["user_id"]: int(r["total"] or 0) for r in await cur.fetchall()}
                await cur.execute("SELECT user_id, bank_balance, last_daily FROM users")
                updates = []
                for row in await cur.fetchall():
                    user_id = row["user_id"]
                    last_daily = row["last_daily"]
                    if last_daily == today_iso: continue
                    days = 1
                    if last_daily:
                        try: days = max(1, min((today - datetime.fromisoformat(last_daily).date()).days, 7))
                        except Exception: pass
                    interest, current = 0, int(row["bank_balance"] or 0)
                    for _ in range(days):
                        d = int(current * config.BANK_RATE)
                        interest += d; current += d
                    asset_income = incomes.get(user_id, 0) * days
                    if interest > 0 or asset_income > 0: utils.invalidate_cache(user_id)
                    updates.append((interest, asset_income, today_iso, user_id))
                if updates:
                    await cur.executemany("UPDATE users SET bank_balance = bank_balance + %s, balance = balance + %s, last_daily = %s WHERE user_id=%s", updates)
                await conn.commit()


# ═══════════════════════════════════════════
# ═══════════ XP & Level ═══════════
# ═══════════════════════════════════════════
async def add_xp(user_id: int, amount: int) -> tuple[int, int, bool]:
    """اضافه کردن XP. خروجی: (new_xp, new_level, leveled_up)"""
    if amount <= 0:
        return 0, 1, False
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT total_xp FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            old_xp = int(row["total_xp"] or 0) if row else 0
            new_xp = old_xp + amount

            # محاسبه لول جدید
            new_level, _, _ = utils.calc_level(new_xp)
            old_level, _, _ = utils.calc_level(old_xp)

            await cur.execute("UPDATE users SET total_xp = %s, level = %s WHERE user_id=%s", (new_xp, new_level, user_id))
            await conn.commit()

    return new_xp, new_level, new_level > old_level


# ═══════════════════════════════════════════
# ═══════════ Kabareh (کاباره) ═══════════
# ═══════════════════════════════════════════
async def unlock_kabareh(user_id: int) -> bool:
    """
    باز کردن کاباره.
    خروجی: True اگه موفق، False اگر موجودی کم بود یا از قبل باز بود.
    """
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                # 1. چک کردن اینکه قبلاً باز نشده
                await cur.execute("SELECT kabareh_unlocked, balance FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                row = await cur.fetchone()
                if not row:
                    await conn.rollback()
                    return False
                kabareh_unlocked = int(row[0] or 0)
                balance = int(row[1] or 0)

                if kabareh_unlocked == 1:
                    await conn.rollback()
                    return False  # قبلاً باز شده

                if balance < config.KABAREH_UNLOCK_COST:
                    await conn.rollback()
                    return False  # موجودی کافی نیست

                # 2. کسر پول و باز کردن
                await cur.execute(
                    "UPDATE users SET balance = balance - %s, kabareh_unlocked = 1 WHERE user_id=%s AND kabareh_unlocked = 0 AND balance >= %s",
                    (config.KABAREH_UNLOCK_COST, user_id, config.KABAREH_UNLOCK_COST)
                )
                if cur.rowcount != 1:
                    await conn.rollback()
                    return False

            await conn.commit()
            logger.info(f"✅ Kabareh unlocked for user {user_id}")
            return True
        except Exception as e:
            await conn.rollback()
            logger.exception(f"unlock_kabareh failed: {e}")
            return False


# ═══════════════════════════════════════════
# ═══════════ Missions (ماموریت‌ها) ═══════════
# ═══════════════════════════════════════════
async def ensure_daily_missions(user_id: int):
    today = utils.today_str()
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT last_mission_date FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            if row and row["last_mission_date"] == today:
                return

            await cur.execute(
                "UPDATE users SET last_mission_date=%s WHERE user_id=%s AND (last_mission_date IS NULL OR last_mission_date != %s)",
                (today, user_id, today)
            )
            if cur.rowcount == 0:
                await conn.commit()
                return

            await cur.execute("DELETE FROM user_missions WHERE user_id=%s", (user_id,))
            keys = list(config.MISSION_TEMPLATES.keys())
            n = min(config.DAILY_MISSION_COUNT, len(keys))
            chosen = random.sample(keys, n)

            for key in chosen:
                t = config.MISSION_TEMPLATES[key]
                await cur.execute(
                    "INSERT INTO user_missions (user_id, mission_key, mission_date, progress, target, xp_reward) VALUES (%s, %s, %s, 0, %s, %s)",
                    (user_id, key, today, t["target"], t["xp"])
                )
            await conn.commit()


async def get_user_missions(user_id: int) -> list[dict]:
    today = utils.today_str()
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM user_missions WHERE user_id=%s AND mission_date=%s ORDER BY id ASC",
                (user_id, today)
            )
            return [dict(r) for r in await cur.fetchall()]


async def progress_mission(user_id: int, mission_type: str, amount: int = 1, base_xp: int = 0) -> dict | None:
    await ensure_daily_missions(user_id)
    today = utils.today_str()

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, mission_key, progress, target, xp_reward FROM user_missions WHERE user_id=%s AND mission_date=%s AND completed=0",
                (user_id, today)
            )
            missions = await cur.fetchall()
            completed_missions = []

            for m in missions:
                template = config.MISSION_TEMPLATES.get(m["mission_key"])
                if not template or template["type"] != mission_type:
                    continue
                target = int(m["target"])
                new_progress = int(m["progress"]) + amount

                if new_progress >= target:
                    await cur.execute("UPDATE user_missions SET progress=%s, completed=1 WHERE id=%s", (target, m["id"]))
                    completed_missions.append({
                        "key": m["mission_key"],
                        "desc": template["desc"],
                        "xp": int(m["xp_reward"])
                    })
                else:
                    await cur.execute("UPDATE user_missions SET progress=%s WHERE id=%s", (new_progress, m["id"]))
            await conn.commit()

    mission_xp = sum(cm["xp"] for cm in completed_missions)
    total_xp = base_xp + mission_xp
    if total_xp <= 0:
        return None

    new_xp, new_level, leveled_up = await add_xp(user_id, total_xp)
    return {
        "user_id": user_id,
        "completed": completed_missions,
        "mission_xp": mission_xp,
        "base_xp": base_xp,
        "total_xp": total_xp,
        "new_level": new_level,
        "leveled_up": leveled_up,
    }


# ═══════════════════════════════════════════
# ═══════════ Zar Cooldown ═══════════
# ═══════════════════════════════════════════
async def get_last_zar(user_id: int) -> str | None:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT last_zar FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            return row[0] if row else None


async def set_last_zar(user_id: int, when: str):
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET last_zar=%s WHERE user_id=%s", (when, user_id))
            await conn.commit()
