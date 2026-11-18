#!/usr/bin/env python
"""Main entry point for the B2B Phone Repair Marketplace application."""

import asyncio
import uvicorn
from app.core.config import get_settings

settings = get_settings()


def run_web():
    """Run the FastAPI web server."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )


async def run_bot():
    """Run the Telegram bot in polling mode (for development)."""
    from app.bot.loader import dp, bot
    from app.bot.setup import setup_bot

    await setup_bot()
    await dp.start_polling(bot)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "bot":
        asyncio.run(run_bot())
    else:
        run_web()