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
    "CREATE TABLE IF NOT EXISTS inventory (id INT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, item_key VARCHAR(64) NOT NULL, purchased_at VARCHAR(32) NOT NULL, INDEX idx_user_item (user_id, item_key)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
]

EXTRA_COLUMNS = [
    ("total_xp", "BIGINT NOT NULL DEFAULT 0"),
    ("level", "INT NOT NULL DEFAULT 1"),
    ("kabareh_unlocked", "TINYINT NOT NULL DEFAULT 0"),
    ("last_kabareh", "VARCHAR(32) DEFAULT NULL"),
    ("last_zar", "VARCHAR(32) DEFAULT NULL"),
    ("last_mission_date", "VARCHAR(10) DEFAULT NULL"),
    ("last_payout", "VARCHAR(32) DEFAULT NULL"),  # زمان آخرین پرداخت درآمد
]


async def init_db_pool():
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
        db=config.DB_NAME, autocommit=False, minsize=2, maxsize=20, charset="utf8mb4")
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
            for col_name, col_type in EXTRA_COLUMNS:
                try:
                    await cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ ستون {col_name} اضافه شد.")
                except Exception:
                    pass
            await conn.commit()
    logger.info("✅ دیتابیس آماده است.")


# ═══════════ مدیریت کاربر ═══════════
async def ensure_user(user) -> dict:
    """ایجاد یا به‌روزرسانی کاربر. با ON DUPLICATE KEY UPDATE بهینه‌شده."""
    if user.id in utils.user_cache:
        return utils.user_cache[user.id]
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "INSERT INTO users (user_id, username, first_name, balance, bank_balance, card_number, created_at) "
                "VALUES (%s, %s, %s, %s, 0, %s, %s) "
                "ON DUPLICATE KEY UPDATE username=VALUES(username), first_name=VALUES(first_name)",
                (user.id, user.username, user.first_name, config.START_BALANCE,
                 utils.card_number_for(user.id), utils.now_iso()))
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


# ═══════════ دارایی‌ها ═══════════
async def get_assets_summary(user_id: int) -> dict:
    """خلاصه دارایی‌ها با کش ۶۰ ثانیه‌ای"""
    cached = utils.assets_summary_cache.get(user_id)
    if cached is not None:
        return cached
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT asset_key, COUNT(*) as count, SUM(daily_income) as total_income "
                "FROM assets WHERE user_id=%s GROUP BY asset_key", (user_id,))
            rows = await cur.fetchall()
            result = {r["asset_key"]: {"count": int(r["count"]), "total_income": int(r["total_income"])} for r in rows}
            utils.assets_summary_cache[user_id] = result
            return result


async def get_assets(user_id: int, asset_type: str) -> list[dict]:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM assets WHERE user_id=%s AND asset_type=%s ORDER BY id ASC", (user_id, asset_type))
            return [dict(r) for r in await cur.fetchall()]


async def buy_asset(user_id: int, asset_type: str, asset_key: str, price: int, income: int) -> str:
    utils.invalidate_cache(user_id)
    utils.invalidate_assets_cache(user_id)
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


# ═══════════ درآمد ساعتی (جایگزین daily_payout) ═══════════
def _calc_income(bank_balance: int, daily_asset: int, seconds: float) -> tuple[int, int]:
    """محاسبه درآمد دارایی و سود بانکی برای مدت زمان مشخص"""
    if seconds <= 0:
        return 0, 0
    # درآمد دارایی: daily_income * (seconds / 86400)
    asset_income = int(daily_asset * seconds / 86400)
    # سود بانکی: bank_balance * RATE * (seconds / 86400) - به bank_balance اضافه می‌شود (سود مرکب)
    bank_interest = int(bank_balance * config.BANK_RATE * seconds / 86400)
    return asset_income, bank_interest


async def accrue_income(user_id: int) -> tuple[int, int, int]:
    """
    محاسبه و واریز درآمد انباشته‌شده برای یک کاربر (برداشت دستی).
    درآمد دارایی به balance اضافه می‌شود.
    سود بانکی به bank_balance اضافه می‌شود (سود مرکب).
    خروجی: (asset_income, bank_interest, total)
    """
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT bank_balance, last_payout FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                row = await cur.fetchone()
                if not row:
                    await conn.rollback(); return 0, 0, 0
                now = datetime.now(utils.TEHRAN)
                last = row.get("last_payout")
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        seconds = (now - last_dt).total_seconds()
                    except Exception:
                        seconds = 0
                else:
                    seconds = 0
                if seconds < 1:
                    await conn.rollback(); return 0, 0, 0
                # درآمد دارایی‌ها
                await cur.execute("SELECT COALESCE(SUM(daily_income), 0) as total FROM assets WHERE user_id=%s", (user_id,))
                arow = await cur.fetchone()
                daily_asset = int(arow["total"] or 0)
                bank_balance = int(row["bank_balance"] or 0)
                asset_income, bank_interest = _calc_income(bank_balance, daily_asset, seconds)
                now_iso = now.isoformat()
                if asset_income > 0 or bank_interest > 0:
                    await cur.execute(
                        "UPDATE users SET balance = balance + %s, bank_balance = bank_balance + %s, last_payout = %s WHERE user_id=%s",
                        (asset_income, bank_interest, now_iso, user_id))
                else:
                    await cur.execute("UPDATE users SET last_payout = %s WHERE user_id=%s", (now_iso, user_id))
            await conn.commit()
            if asset_income > 0 or bank_interest > 0:
                utils.invalidate_cache(user_id)
            return asset_income, bank_interest, asset_income + bank_interest
        except Exception:
            await conn.rollback()
            logger.exception("accrue_income failed")
            return 0, 0, 0


async def peek_income(user_id: int) -> tuple[int, int, int]:
    """محاسبه درآمد انباشته بدون واریز (برای نمایش). خروجی: (asset_income, bank_interest, total)"""
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT bank_balance, last_payout FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            if not row:
                return 0, 0, 0
            now = datetime.now(utils.TEHRAN)
            last = row.get("last_payout")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    seconds = (now - last_dt).total_seconds()
                except Exception:
                    seconds = 0
            else:
                seconds = 0
            if seconds < 1:
                return 0, 0, 0
            await cur.execute("SELECT COALESCE(SUM(daily_income), 0) as total FROM assets WHERE user_id=%s", (user_id,))
            arow = await cur.fetchone()
            daily_asset = int(arow["total"] or 0)
            bank_balance = int(row["bank_balance"] or 0)
            asset_income, bank_interest = _calc_income(bank_balance, daily_asset, seconds)
            return asset_income, bank_interest, asset_income + bank_interest


async def hourly_payout(context=None):
    """
    پرداخت خودکار ساعتی برای همه کاربران.
    حداکثر HOURLY_PAYOUT_MAX_CATCHUP ثانیه درآمد پرداخت می‌کند (برای جلوگیری از پرداخت زیاد هنگام ری‌استارت).
    """
    if db_pool is None:
        logger.warning("⚠️ hourly_payout: db_pool هنوز مقداردهی نشده")
        return
    try:
        async with utils.hourly_lock:
            now = datetime.now(utils.TEHRAN)
            now_iso = now.isoformat()
            async with db_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("SELECT user_id, bank_balance, last_payout FROM users")
                    users = await cur.fetchall()
                    await cur.execute("SELECT user_id, COALESCE(SUM(daily_income), 0) as total FROM assets GROUP BY user_id")
                    asset_incomes = {r["user_id"]: int(r["total"] or 0) for r in await cur.fetchall()}

                    income_updates = []  # کاربرانی که درآمد > 0
                    for row in users:
                        user_id = row["user_id"]
                        last = row.get("last_payout")
                        if last:
                            try:
                                last_dt = datetime.fromisoformat(last)
                                seconds = (now - last_dt).total_seconds()
                            except Exception:
                                seconds = config.HOURLY_PAYOUT_INTERVAL
                        else:
                            seconds = config.HOURLY_PAYOUT_INTERVAL
                        # محدود کردن زمان برای جلوگیری از پرداخت زیاد
                        seconds = max(0, min(seconds, config.HOURLY_PAYOUT_MAX_CATCHUP))
                        if seconds < 1:
                            continue
                        daily_asset = asset_incomes.get(user_id, 0)
                        bank_balance = int(row["bank_balance"] or 0)
                        asset_income, bank_interest = _calc_income(bank_balance, daily_asset, seconds)
                        if asset_income > 0 or bank_interest > 0:
                            income_updates.append((asset_income, bank_interest, now_iso, user_id))
                            utils.invalidate_cache(user_id)
                    if income_updates:
                        await cur.executemany(
                            "UPDATE users SET balance = balance + %s, bank_balance = bank_balance + %s, last_payout = %s WHERE user_id=%s",
                            income_updates)
                    # آپدیت last_payout برای همه کاربران (حتی بدون درآمد) تا ثانیه‌ها انباشته نشوند
                    await cur.execute("UPDATE users SET last_payout = %s WHERE last_payout IS NULL OR last_payout != %s", (now_iso, now_iso))
                    await conn.commit()
        logger.info(f"✅ پرداخت ساعتی انجام شد. {len(income_updates)} کاربر درآمد دریافت کردند.")
    except Exception as e:
        logger.exception(f"❌ hourly_payout error: {e}")


async def daily_payout(context=None):
    """
    پرداخت روزانه کامل درآمد برای همه کاربران (ساعت 00:00).
    این تابع مطمئن می‌شه همه درآمدهای انباشته‌شده روزانه واریز شده.
    هر کاربر درآمد دارایی‌ها رو به‌صورت کامل (۲۴ ساعت) دریافت می‌کنه.
    """
    if db_pool is None:
        logger.warning("⚠️ daily_payout: db_pool هنوز مقداردهی نشده")
        return
    try:
        async with utils.hourly_lock:
            now = datetime.now(utils.TEHRAN)
            now_iso = now.isoformat()
            async with db_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # همه کاربران و آخرین پرداخت‌شون
                    await cur.execute("SELECT user_id, bank_balance, last_payout FROM users")
                    users = await cur.fetchall()
                    # درآمد روزانه هر کاربر از دارایی‌ها
                    await cur.execute("SELECT user_id, COALESCE(SUM(daily_income), 0) as total FROM assets GROUP BY user_id")
                    asset_incomes = {r["user_id"]: int(r["total"] or 0) for r in await cur.fetchall()}

                    daily_updates = []  # کاربرانی که درآمد روزانه دارن
                    for row in users:
                        user_id = row["user_id"]
                        last = row.get("last_payout")
                        if last:
                            try:
                                last_dt = datetime.fromisoformat(last)
                                seconds = (now - last_dt).total_seconds()
                            except Exception:
                                seconds = 86400  # ۲۴ ساعت
                        else:
                            seconds = 86400  # ۲۴ ساعت
                        # برای daily_payout حداقل ۱ ساعت درآمد واریز کن
                        seconds = max(3600, min(seconds, config.HOURLY_PAYOUT_MAX_CATCHUP))
                        daily_asset = asset_incomes.get(user_id, 0)
                        bank_balance = int(row["bank_balance"] or 0)
                        asset_income, bank_interest = _calc_income(bank_balance, daily_asset, seconds)
                        if asset_income > 0 or bank_interest > 0:
                            daily_updates.append((asset_income, bank_interest, now_iso, user_id))
                            utils.invalidate_cache(user_id)
                    if daily_updates:
                        await cur.executemany(
                            "UPDATE users SET balance = balance + %s, bank_balance = bank_balance + %s, last_payout = %s WHERE user_id=%s",
                            daily_updates)
                    # آپدیت last_payout برای همه کاربران
                    await cur.execute("UPDATE users SET last_payout = %s WHERE last_payout IS NULL OR last_payout != %s", (now_iso, now_iso))
                    await conn.commit()
        logger.info(f"✅ پرداخت روزانه (00:00) انجام شد. {len(daily_updates)} کاربر درآمد دریافت کردند.")
    except Exception as e:
        logger.exception(f"❌ daily_payout error: {e}")


# ═══════════ XP و لول ═══════════
async def add_xp(user_id: int, amount: int) -> tuple[int, int, bool]:
    if amount <= 0: return 0, 1, False
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT total_xp FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            old_xp = int(row["total_xp"] or 0) if row else 0
            new_xp = old_xp + amount
            new_level, _, _ = utils.calc_level(new_xp)
            old_level, _, _ = utils.calc_level(old_xp)
            await cur.execute("UPDATE users SET total_xp = %s, level = %s WHERE user_id=%s", (new_xp, new_level, user_id))
            await conn.commit()
    return new_xp, new_level, new_level > old_level


async def unlock_kabareh(user_id: int) -> bool:
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("SELECT kabareh_unlocked, balance FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                row = await cur.fetchone()
                if not row:
                    await conn.rollback(); return False
                kab = int(row[0] or 0); bal = int(row[1] or 0)
                if kab == 1 or bal < config.KABAREH_UNLOCK_COST:
                    await conn.rollback(); return False
                await cur.execute(
                    "UPDATE users SET balance = balance - %s, kabareh_unlocked = 1 WHERE user_id=%s AND kabareh_unlocked = 0 AND balance >= %s",
                    (config.KABAREH_UNLOCK_COST, user_id, config.KABAREH_UNLOCK_COST))
                if cur.rowcount != 1:
                    await conn.rollback(); return False
            await conn.commit()
            return True
        except Exception:
            await conn.rollback()
            logger.exception("unlock_kabareh failed")
            return False


# ═══════════ کاباره: کول‌داون ═══════════
async def set_last_kabareh(user_id: int, when: str):
    utils.invalidate_cache(user_id)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET last_kabareh=%s WHERE user_id=%s", (when, user_id))
            await conn.commit()


# ═══════════ ماموریت‌های روزانه ═══════════
async def _get_eligible_missions(user_id: int, cur) -> list[str]:
    """
    فیلتر ماموریت‌ها بر اساس وضعیت کاربر:
    - اگر تمام ملک‌ها را خریده → buy_property فیلتر می‌شود
    - اگر تمام کارگرها را خریده → buy_worker فیلتر می‌شود
    - اگر کاباره را باز نکرده → kabareh فیلتر می‌شود
    - اگر کاربر نتواند target خرید را تکمیل کند → فیلتر می‌شود
    """
    await cur.execute("SELECT kabareh_unlocked FROM users WHERE user_id=%s", (user_id,))
    urow = await cur.fetchone()
    kabareh_unlocked = bool(urow and int(urow["kabareh_unlocked"] or 0))

    await cur.execute("SELECT asset_type, COUNT(*) as cnt FROM assets WHERE user_id=%s GROUP BY asset_type", (user_id,))
    asset_counts = {r["asset_type"]: int(r["cnt"]) for r in await cur.fetchall()}
    prop_count = asset_counts.get("property", 0)
    worker_count = asset_counts.get("worker", 0)
    max_props = len(config.PROPERTIES) * config.MAX_PER_KEY
    max_workers = len(config.WORKERS) * config.MAX_PER_KEY

    eligible = []
    for key, t in config.MISSION_TEMPLATES.items():
        mtype = t["type"]
        target = t["target"]
        if mtype == "buy_property":
            # اگر کاربر + target > حداکثر، ماموریت غیرممکن است
            if prop_count + target > max_props:
                continue
        elif mtype == "buy_worker":
            if worker_count + target > max_workers:
                continue
        elif mtype == "kabareh":
            if not kabareh_unlocked:
                continue
        eligible.append(key)
    return eligible


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
                (today, user_id, today))
            if cur.rowcount == 0:
                await conn.commit(); return
            await cur.execute("DELETE FROM user_missions WHERE user_id=%s", (user_id,))
            eligible = await _get_eligible_missions(user_id, cur)
            n = min(config.DAILY_MISSION_COUNT, len(eligible))
            if n <= 0:
                await conn.commit(); return
            chosen = random.sample(eligible, n)
            for key in chosen:
                t = config.MISSION_TEMPLATES[key]
                await cur.execute(
                    "INSERT INTO user_missions (user_id, mission_key, mission_date, progress, target, xp_reward) VALUES (%s, %s, %s, 0, %s, %s)",
                    (user_id, key, today, t["target"], t["xp"]))
            await conn.commit()


async def get_user_missions(user_id: int) -> list[dict]:
    today = utils.today_str()
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM user_missions WHERE user_id=%s AND mission_date=%s ORDER BY id ASC", (user_id, today))
            return [dict(r) for r in await cur.fetchall()]


async def progress_mission(user_id: int, mission_type: str, amount: int = 1, base_xp: int = 0) -> dict | None:
    await ensure_daily_missions(user_id)
    today = utils.today_str()
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, mission_key, progress, target, xp_reward FROM user_missions WHERE user_id=%s AND mission_date=%s AND completed=0",
                (user_id, today))
            missions = await cur.fetchall()
            completed_missions = []
            for m in missions:
                template = config.MISSION_TEMPLATES.get(m["mission_key"])
                if not template or template["type"] != mission_type: continue
                target = int(m["target"]); new_progress = int(m["progress"]) + amount
                if new_progress >= target:
                    await cur.execute("UPDATE user_missions SET progress=%s, completed=1 WHERE id=%s", (target, m["id"]))
                    completed_missions.append({"key": m["mission_key"], "desc": template["desc"], "xp": int(m["xp_reward"])})
                else:
                    await cur.execute("UPDATE user_missions SET progress=%s WHERE id=%s", (new_progress, m["id"]))
            await conn.commit()
    mission_xp = sum(cm["xp"] for cm in completed_missions)
    total_xp = base_xp + mission_xp
    if total_xp <= 0: return None
    new_xp, new_level, leveled_up = await add_xp(user_id, total_xp)
    return {"user_id": user_id, "completed": completed_missions, "mission_xp": mission_xp, "base_xp": base_xp, "total_xp": total_xp, "new_level": new_level, "leveled_up": leveled_up}


async def get_last_zar(user_id: int):
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


# ═══════════ لیدربورد ═══════════
async def get_leaderboard(limit: int = 10, around_user_id: int = None) -> tuple[list[dict], int | None]:
    """
    گرفتن لیدربورد بر اساس ثروت (balance + bank_balance).
    خروجی: (لیست کاربران، رتبه کاربر درخواست‌کننده یا None)
    """
    if db_pool is None:
        logger.warning("⚠️ get_leaderboard: db_pool هنوز مقداردهی نشده")
        return [], None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # ─── دریافت ۱۵ کاربر برتر ───
                await cur.execute(
                    "SELECT user_id, first_name, username, balance, bank_balance "
                    "FROM users ORDER BY (balance + bank_balance) DESC LIMIT %s",
                    (limit,))
                top_users = []
                for r in await cur.fetchall():
                    try:
                        row_dict = dict(r)
                        # تبدیل Decimal به int (MySQL ممکنه Decimal برگردونه)
                        row_dict["balance"] = int(row_dict.get("balance") or 0)
                        row_dict["bank_balance"] = int(row_dict.get("bank_balance") or 0)
                        row_dict["total_wealth"] = row_dict["balance"] + row_dict["bank_balance"]
                        top_users.append(row_dict)
                    except Exception as e:
                        logger.warning(f"⚠️ خطا در پردازش ردیف لیدربورد: {e}")
                        continue

                # ─── محاسبه رتبه کاربر ───
                user_rank = None
                if around_user_id:
                    # اول بررسی کن کاربر وجود داره
                    await cur.execute(
                        "SELECT balance, bank_balance FROM users WHERE user_id=%s",
                        (around_user_id,))
                    urow = await cur.fetchone()
                    if urow:
                        user_wealth = int(urow.get("balance") or 0) + int(urow.get("bank_balance") or 0)
                        # تعداد کاربرانی که ثروتشون بیشتره + 1
                        await cur.execute(
                            "SELECT COUNT(*) as cnt FROM users "
                            "WHERE (balance + bank_balance) > %s",
                            (user_wealth,))
                        rrow = await cur.fetchone()
                        if rrow and rrow.get("cnt") is not None:
                            user_rank = int(rrow["cnt"]) + 1
            return top_users, user_rank
    except Exception as e:
        logger.exception(f"❌ get_leaderboard error: {e}")
        return [], None


# ═══════════ اینونتوری (بازار سیاه) ═══════════
async def buy_inventory_item(user_id: int, item_key: str) -> str:
    """خرید آیتم بازار سیاه"""
    utils.invalidate_cache(user_id)
    item = config.BLACKMARKET_ITEMS.get(item_key)
    if not item:
        return "invalid"
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s AND balance >= %s",
                                  (item["price"], user_id, item["price"]))
                if cur.rowcount != 1:
                    await conn.rollback(); return "balance"
                await cur.execute("INSERT INTO inventory (user_id, item_key, purchased_at) VALUES (%s, %s, %s)",
                                  (user_id, item_key, utils.now_iso()))
            await conn.commit(); return "ok"
        except Exception:
            await conn.rollback(); return "error"


async def get_inventory_counts(user_id: int) -> dict:
    """تعداد هر آیتم در اینونتوری کاربر"""
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT item_key, COUNT(*) as cnt FROM inventory WHERE user_id=%s GROUP BY item_key",
                (user_id,))
            return {r["item_key"]: int(r["cnt"]) for r in await cur.fetchall()}


async def has_item(user_id: int, item_key: str) -> bool:
    """بررسی اینکه آیا کاربر آیتم رو داره"""
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM inventory WHERE user_id=%s AND item_key=%s LIMIT 1",
                              (user_id, item_key))
            return cur.rowcount > 0


async def consume_item(user_id: int, item_key: str) -> bool:
    """مصرف یک آیتم (مثلاً بعد از شلیک موشک)"""
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM inventory WHERE user_id=%s AND item_key=%s LIMIT 1",
                                  (user_id, item_key))
                if cur.rowcount != 1:
                    await conn.rollback(); return False
            await conn.commit(); return True
        except Exception:
            await conn.rollback(); return False


# ═══════════ آسیب (شلیک سلاح) ═══════════
async def apply_damage(target_id: int, damage_percent: float) -> int:
    """
    اعمال آسیب به کاربر هدف.
    درصد از (balance + bank_balance) کم می‌شه.
    ابتدا از balance کم می‌شه، اگر کافی نبود از bank_balance.
    خروجی: مقدار کل آسیب وارد شده
    """
    utils.invalidate_cache(target_id)
    async with db_pool.acquire() as conn:
        try:
            await conn.begin()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT balance, bank_balance FROM users WHERE user_id=%s FOR UPDATE", (target_id,))
                row = await cur.fetchone()
                if not row:
                    await conn.rollback(); return 0
                balance = int(row["balance"] or 0)
                bank = int(row["bank_balance"] or 0)
                total = balance + bank
                damage = int(total * damage_percent)
                if damage <= 0:
                    await conn.rollback(); return 0
                # اول از balance کم کن
                if balance >= damage:
                    await cur.execute("UPDATE users SET balance = balance - %s WHERE user_id=%s", (damage, target_id))
                else:
                    # تمام balance رو صفر کن، بقیه از bank
                    remaining = damage - balance
                    await cur.execute("UPDATE users SET balance = 0, bank_balance = bank_balance - %s WHERE user_id=%s",
                                      (remaining, target_id))
            await conn.commit(); return damage
        except Exception:
            await conn.rollback()
            logger.exception("apply_damage failed")
            return 0


async def get_user_total_wealth(user_id: int) -> int:
    """مجموع ثروت کاربر (balance + bank_balance)"""
    user = await get_user(user_id)
    if not user: return 0
    return int(user.get("balance", 0)) + int(user.get("bank_balance", 0))


async def get_user_by_id(user_id: int):
    """گرفتن کاربر با آیدی"""
    return await get_user(user_id)
