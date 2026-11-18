from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from app.core.config import get_settings

settings = get_settings()

# Bot instance
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# FSM Storage - use Redis in production, Memory for development
if settings.APP_ENV == "production":
    # storage = RedisStorage.from_url(settings.REDIS_URL)
    storage = MemoryStorage()  # Fallback for now
else:
    storage = MemoryStorage()

# Dispatcher
dp = Dispatcher(storage=storage)

# Middleware will be added in setup.py