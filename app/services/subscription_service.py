from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, SubscriptionStatus


async def get_user_subscription(db: AsyncSession, user_id: UUID) -> Optional[Subscription]:
    """Get user's subscription."""
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


async def get_subscription_status(db: AsyncSession, user_id: UUID) -> str:
    """Get user's subscription status as string."""
    subscription = await get_user_subscription(db, user_id)
    if not subscription:
        return "inactive"
    return subscription.status.value


async def is_subscription_active(db: AsyncSession, user_id: UUID) -> bool:
    """Check if user has active subscription."""
    subscription = await get_user_subscription(db, user_id)
    if not subscription:
        return False
    return subscription.status == SubscriptionStatus.ACTIVE


async def check_subscription_access(db: AsyncSession, user_id: UUID) -> tuple[bool, str]:
    """
    Check if user can access marketplace features.
    Returns (has_access, reason_if_blocked).
    """
    subscription = await get_user_subscription(db, user_id)
    if not subscription:
        return False, "No subscription found. Please complete registration."

    if subscription.status == SubscriptionStatus.ACTIVE:
        return True, ""

    if subscription.status == SubscriptionStatus.PENDING_APPROVAL:
        return False, "Subscription pending approval. Please complete payment."

    if subscription.status == SubscriptionStatus.PAST_DUE:
        return False, "Subscription past due. Please renew to continue."

    if subscription.status == SubscriptionStatus.CANCELED:
        return False, "Subscription canceled. Please reactivate."

    return False, "Subscription inactive. Please contact support."