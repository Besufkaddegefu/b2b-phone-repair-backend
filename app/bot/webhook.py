from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.loader import dp, bot
from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter()
settings = get_settings()


@router.post("/tg")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming Telegram webhook updates."""
    # Verify secret token (only when configured)
    if settings.TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret token")

    # Get update data
    update_data = await request.json()

    # Process update with aiogram
    from aiogram.types import Update
    update = Update.model_validate(update_data, context={"db": db})
    await dp.feed_update(bot, update)

    return {"ok": True}


@router.get("/tg/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {"status": "ok", "bot": "ready"}