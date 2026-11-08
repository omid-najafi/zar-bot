import logging
import aiomysql
from datetime import datetime
import config
import utils

logger = logging.getLogger("zarcoin")
db_pool = None

SCHEMA_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username VARCHAR(255), first_name VARCHAR(255), balance BIGINT NOT NULL DEFAULT 0, bank_balance BIGINT NOT NULL DEFAULT 0, card_number VARCHAR(16) UNIQUE, last_daily VARCHAR(10), created_at VARCHAR(32) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    "CREATE TABLE IF NOT EXISTS assets (id INT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, asset_type VARCHAR(32) NOT NULL, asset_key VARCHAR(64) NOT NULL, purchase_price BIGINT NOT NULL, daily_income BIGINT NOT NULL, purchased_at VARCHAR(32) NOT NULL, INDEX idx_assets (user_id, asset_type, asset_key)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
]

async def init_db_pool():
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
        db=config.DB_NAME, autocommit=False, minsize=1, maxsize=20, charset="utf8mb4")
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
            await conn.commit()

async def ensure_user(user) -> dict:
    now = datetime.now(utils.TEHRAN).timestamp()
    if user.id in utils.user_cache:
        cached_data, ts = utils.user_cache[user.id]
        if now - ts < 60: return cached_data

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("INSERT IGNORE INTO users (user_id, username, first_name, balance, bank_balance, card_number, created_at) VALUES (%s, %s, %s, %s, 0, %s, %s)", (user.id, user.username, user.first_name, config.START_BALANCE, utils.card_number_for(user.id), utils.now_iso()))
            await cur.execute("UPDATE users SET username=%s, first_name=%s WHERE user_id=%s", (user.username, user.first_name, user.id))
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user.id,))
            row = await cur.fetchone()
            await conn.commit()
            user_dict = dict(row)
            utils.user_cache[user.id] = (user_dict, now)
            return user_dict

async def get_user(user_id: int):
    now = datetime.now(utils.TEHRAN).timestamp()
    if user_id in utils.user_cache:
        cached_data, ts = utils.user_cache[user_id]
        if now - ts < 60: return cached_data

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
            row = await cur.fetchone()
            if row:
                user_dict = dict(row)
                utils.user_cache[user_id] = (user_dict, now)
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
            return {r["asset_key"]: r for r in await cur.fetchall()}

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
                if int((await cur.fetchone())[0]) >= config.MAX_PER_KEY:
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
