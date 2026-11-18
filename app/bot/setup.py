from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Awaitable, Callable, Dict

from app.db.session import get_db


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to inject database session into handler context."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async for db in get_db():
            data["db"] = db
            try:
                return await handler(event, data)
            finally:
                await db.close()


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware to check subscription status for protected actions."""

    PROTECTED_COMMANDS = {"post_part", "find_part", "my_listings"}
    PROTECTED_CALLBACKS = {"cat_", "brand_", "cond_"}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Check if this is a protected action
        if isinstance(event, Update):
            if event.message and event.message.text:
                text = event.message.text
                if text == "📦 Post Part" or text == "🔍 Find Part" or text == "📋 My Listings":
                    # Check subscription in handler instead
                    pass

        return await handler(event, data)


async def setup_bot():
    """Setup bot with all handlers and middleware."""
    from app.bot.loader import dp
    from app.bot.handlers import registration, listings, payments

    # Add middleware
    dp.update.middleware(DatabaseMiddleware())

    # Register routers
    dp.include_router(registration.router)
    dp.include_router(listings.router)
    dp.include_router(payments.router)

    # Set bot commands
    from aiogram.types import BotCommand
    from app.bot.loader import bot

    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help"),
        BotCommand(command="web_login", description="Link to web dashboard"),
    ]
    await bot.set_my_commands(commands)

    return dp