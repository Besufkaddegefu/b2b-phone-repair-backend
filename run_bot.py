import asyncio
import logging
import sys

from aiogram.types import ErrorEvent
from app.bot.setup import setup_bot
from app.bot.loader import bot, dp
from app.core.config import get_settings
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

settings = get_settings()


@dp.errors()
async def error_handler(event: ErrorEvent):
    """Global error handler - logs all bot errors."""
    logger.exception("Bot error in %s: %s", event.update, event.exception)
    return True


async def main():
    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Setup bot (handlers, middleware, commands)
    await setup_bot()

    # Start polling
    logger.info("Bot is polling. Send /start on Telegram to test.")
    try:
        await dp.start_polling(bot)
    finally:
        await dp.storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
