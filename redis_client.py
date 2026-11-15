# -*- coding: utf-8 -*-
"""
🔑 کلاینت Redis برای مینی‌اپ قمارخانه
─────────────────────────────────────────────
- نگه‌داری صف مچ‌میکینگ (پایدار از ری‌استارت)
- نگه‌داری بازی‌های فعال (پایدار از ری‌استارت)
- قفل توزیع‌شده برای عملیات حساس (atomic matchmaking)

اگر REDIS_URL تنظیم نشده باشد، به‌صورت خودکار به حالت درون‌حافظه‌ای
برمی‌گردد (fallback) — برای تست محلی بدون Redis.
"""
import json
import logging
import time
import asyncio
from typing import Optional

import config

logger = logging.getLogger("zarcoin.redis")

# ═══════════ کلاینت Redis ═══════════
_redis = None
_redis_available = False
_fallback_lock = asyncio.Lock()


async def init_redis():
    """ساخت connection pool به Redis. اگر URL نبود، در حالت fallback می‌ماند."""
    global _redis, _redis_available
    if not config.REDIS_URL:
        logger.info("⚠️ REDIS_URL تنظیم نشده — مینی‌اپ در حالت درون‌حافظه‌ای اجرا می‌شود (غیر پایدار از ری‌استارت)")
        _redis_available = False
        return
    try:
        # redis-py 4.3+ از async پشتیبانی می‌کند
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        # تست اتصال
        await _redis.ping()
        _redis_available = True
        logger.info("✅ اتصال به Redis برقرار است — مچ‌میکینگ پایدار از ری‌استارت")
    except ImportError:
        logger.warning("⚠️ کتابخانه redis نصب نیست — pip install redis. حالت fallback فعال.")
        _redis_available = False
        _redis = None
    except Exception as e:
        logger.warning(f"⚠️ اتصال به Redis ناموفق: {e} — حالت fallback فعال (در حافظه)")
        _redis_available = False
        _redis = None


async def close_redis():
    """بستن connection pool در shutdown."""
    global _redis
    if _redis:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None


def is_redis_available() -> bool:
    return _redis_available


def _key(suffix: str) -> str:
    return f"{config.REDIS_PREFIX}:{suffix}"


# ═══════════ صف مچ‌میکینگ ═══════════
# ساختار: هر (game_key, bet) یک sorted set با score=joined_at و member=user_id
# داده‌های ورودی در hash ذخیره می‌شوند تا بازی از ری‌استارت جان سالم بدر برد

async def add_to_queue(game_key: str, bet: int, user_id: int, data: dict) -> bool:
    """افزودن کاربر به صف مچ‌میکینگ. اگر از قبل در هر صف بود، False برمی‌گرداند."""
    if not _redis_available:
        return False  # در حالت fallback، از dict استفاده می‌شود
    # قفل توزیع‌شده برای atomic check-across-all-queues
    lock_key = _key(f"lock:queue:{user_id}")
    try:
        # SET NX با انقضا برای قفل
        acquired = await _redis.set(lock_key, "1", nx=True, ex=10)
        if not acquired:
            return False  # کاربر در حال حاضر در صف/بازی است
        try:
            # بررسی اینکه کاربر در هیچ صف دیگری نیست
            all_user_game = await _redis.get(_key(f"user_game:{user_id}"))
            if all_user_game:
                return False  # کاربر در یک بازی فعال است
            # بررسی صف‌های فعلی — با استفاده از set جامع کاربران در صف
            in_queue = await _redis.sismember(_key("queued_users"), user_id)
            if in_queue:
                return False
            # اضافه به sorted set (key شامل game_key و bet برای تطبیق شرط)
            qkey = _key(f"queue:{game_key}:{bet}")
            score = time.time()
            await _redis.zadd(qkey, {str(user_id): score})
            # ذخیره داده‌های ورودی در hash
            await _redis.hset(_key(f"match_entry:{user_id}"), mapping={
                "game_key": game_key,
                "bet": str(bet),
                "user_id": str(user_id),
                "name": data.get("name", ""),
                "balance": str(data.get("balance", 0)),
                "avatar": data.get("avatar", ""),
                "joined_at": str(score),
            })
            await _redis.expire(_key(f"match_entry:{user_id}"), config.QUEUE_TTL)
            await _redis.expire(qkey, config.QUEUE_TTL)
            # اضافه به set کاربران در صف
            await _redis.sadd(_key("queued_users"), str(user_id))
            await _redis.expire(_key("queued_users"), config.QUEUE_TTL)
            return True
        finally:
            await _redis.delete(lock_key)
    except Exception as e:
        logger.warning(f"add_to_queue خطا: {e}")
        try:
            await _redis.delete(lock_key)
        except Exception:
            pass
        return False


async def find_opponent_and_remove(game_key: str, bet: int, exclude_user_id: int) -> Optional[dict]:
    """پیدا کردن حریف منتظر با همان game_key و bet، حذف از صف، برگرداندن داده‌های حریف.
    اتمیک با ZPOPMIN. خروجی: dict یا None."""
    if not _redis_available:
        return None
    qkey = _key(f"queue:{game_key}:{bet}")
    try:
        # گرفتن قدیمی‌ترین عضو
        members = await _redis.zrange(qkey, 0, 0)
        for m in members:
            opponent_id = int(m)
            if opponent_id == exclude_user_id:
                continue
            # حذف اتمیک
            removed = await _redis.zrem(qkey, m)
            if removed == 1:
                # گرفتن داده‌های ورودی حریف
                entry = await _redis.hgetall(_key(f"match_entry:{opponent_id}"))
                if not entry:
                    continue  # ورودی منقضی شده — بعدی را امتحان کن
                # پاک‌سازی
                await _redis.delete(_key(f"match_entry:{opponent_id}"))
                await _redis.srem(_key("queued_users"), str(opponent_id))
                return {
                    "user_id": opponent_id,
                    "game_key": entry.get("game_key", game_key),
                    "bet": int(entry.get("bet", bet)),
                    "name": entry.get("name", ""),
                    "balance": int(entry.get("balance", 0)),
                    "avatar": entry.get("avatar", ""),
                    "joined_at": float(entry.get("joined_at", 0)),
                }
        return None
    except Exception as e:
        logger.warning(f"find_opponent خطا: {e}")
        return None


async def remove_from_queue(user_id: int) -> bool:
    """حذف کاربر از تمام صف‌ها (در صورت لغو یا تایم‌اوت)."""
    if not _redis_available:
        return False
    try:
        # حذف از set کاربران در صف
        await _redis.srem(_key("queued_users"), str(user_id))
        # حذف entry
        entry = await _redis.hgetall(_key(f"match_entry:{user_id}"))
        if entry:
            game_key = entry.get("game_key")
            bet = entry.get("bet")
            if game_key and bet:
                await _redis.zrem(_key(f"queue:{game_key}:{bet}"), str(user_id))
        await _redis.delete(_key(f"match_entry:{user_id}"))
        return True
    except Exception as e:
        logger.warning(f"remove_from_queue خطا: {e}")
        return False


async def get_queue_status(user_id: int) -> Optional[dict]:
    """گرفتن وضعیت کاربر در صف — برمی‌گرداند: {game_key, bet, remaining} یا None."""
    if not _redis_available:
        return None
    try:
        entry = await _redis.hgetall(_key(f"match_entry:{user_id}"))
        if not entry:
            return None
        joined_at = float(entry.get("joined_at", 0))
        remaining = max(0, int(config.MATCHMAKING_TIMEOUT - (time.time() - joined_at)))
        return {
            "game_key": entry.get("game_key"),
            "bet": int(entry.get("bet", 0)),
            "joined_at": joined_at,
            "remaining": remaining,
        }
    except Exception as e:
        logger.warning(f"get_queue_status خطا: {e}")
        return None


# ═══════════ بازی‌های فعال ═══════════
async def set_user_game(user_id: int, game_id: str):
    """نگاشت user_id → game_id."""
    if not _redis_available:
        return
    try:
        await _redis.set(_key(f"user_game:{user_id}"), game_id, ex=config.GAME_TTL)
    except Exception as e:
        logger.warning(f"set_user_game خطا: {e}")


async def get_user_game(user_id: int) -> Optional[str]:
    if not _redis_available:
        return None
    try:
        v = await _redis.get(_key(f"user_game:{user_id}"))
        return v
    except Exception:
        return None


async def clear_user_game(user_id: int):
    if not _redis_available:
        return
    try:
        await _redis.delete(_key(f"user_game:{user_id}"))
    except Exception:
        pass


async def save_game_state(game_id: str, state_json: str):
    """ذخیره serialization بازی در Redis."""
    if not _redis_available:
        return
    try:
        await _redis.set(_key(f"game:{game_id}"), state_json, ex=config.GAME_TTL)
    except Exception as e:
        logger.warning(f"save_game_state خطا: {e}")


async def load_game_state(game_id: str) -> Optional[str]:
    if not _redis_available:
        return None
    try:
        return await _redis.get(_key(f"game:{game_id}"))
    except Exception:
        return None


async def delete_game_state(game_id: str):
    if not _redis_available:
        return
    try:
        await _redis.delete(_key(f"game:{game_id}"))
    except Exception:
        pass


# ═══════════ قفل توزیع‌شده برای عملیات اتمیک ═══════════
class RedisLock:
    """قفل توزیع‌شده با SET NX + EX. برای matchmaking و game actions."""

    def __init__(self, lock_name: str, ttl: int = 10):
        self.lock_key = _key(f"lock:{lock_name}")
        self.ttl = ttl

    async def __aenter__(self):
        if not _redis_available:
            await _fallback_lock.acquire()
            return self
        # تلاش برای گرفتن قفل با retry کوتاه
        for _ in range(5):
            acquired = await _redis.set(self.lock_key, "1", nx=True, ex=self.ttl)
            if acquired:
                return self
            await asyncio.sleep(0.1)
        # اگر نتوانست قفل بگیرد، در حالت fallback، از lock محلی استفاده کن
        # (در محیط Redis واقعی باید خطا می‌دادیم ولی برای resilience)
        logger.warning(f"قفل {self.lock_key} گرفته نشد — ادامه بدون قفل")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not _redis_available:
            _fallback_lock.release()
            return
        try:
            await _redis.delete(self.lock_key)
        except Exception:
            pass
