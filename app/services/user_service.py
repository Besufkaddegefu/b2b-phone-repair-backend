import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, SubscriptionStatus, Transaction, TransactionStatus, User, UserRole
from app.schemas import PartCondition


async def get_or_create_user(
    db: AsyncSession,
    telegram_id: int,
    telegram_username: Optional[str] = None,
) -> User:
    """Get existing user or create new one with telegram_id."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            full_name="",
            phone_number="",
        )
        db.add(user)
        await db.flush()

        # Create subscription record
        subscription = Subscription(
            user_id=user.id,
            registration_fee_paid=False,
            status=SubscriptionStatus.PENDING_APPROVAL,
            monthly_rate=0.00,
        )
        db.add(subscription)
        await db.commit()
        await db.refresh(user)

    return user


async def update_user_from_registration(
    db: AsyncSession,
    telegram_id: int,
    telegram_username: Optional[str],
    full_name: str,
    shop_name: str,
    shop_location: str,
    phone_number: str,
) -> User:
    """Update user with registration details."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            full_name=full_name,
            phone_number=phone_number,
            shop_name=shop_name,
            shop_location=shop_location,
        )
        db.add(user)
    else:
        user.full_name = full_name
        user.phone_number = phone_number
        user.shop_name = shop_name
        user.shop_location = shop_location
        if telegram_username:
            user.telegram_username = telegram_username

    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> Optional[User]:
    """Get user by Clerk user ID."""
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    return result.scalar_one_or_none()


async def link_clerk_account(db: AsyncSession, user_id: UUID, clerk_user_id: str) -> User:
    """Link Clerk account to existing user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    user.clerk_user_id = clerk_user_id
    await db.commit()
    await db.refresh(user)
    return user


async def generate_web_login_code(db: AsyncSession, user_id: UUID) -> str:
    """Generate a one-time code for web login linking."""
    code = secrets.token_urlsafe(16)
    # Store code in database with expiry (in production, use Redis or a dedicated table)
    # For now, we'll use a simple approach - store in user metadata or separate table
    # This is a placeholder - implement proper code storage
    return code


async def verify_web_login_code(db: AsyncSession, code: str) -> Optional[UUID]:
    """Verify web login code and return user_id."""
    # Placeholder - implement proper code verification
    return None


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


async def create_transaction(
    db: AsyncSession,
    user_id: UUID,
    amount: float,
    payment_type: str,
    payment_method: str,
    transaction_reference: str,
    receipt_image_url: Optional[str] = None,
) -> Transaction:
    """Create a new transaction record."""
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        payment_type=payment_type,
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        receipt_image_url=receipt_image_url,
        status=TransactionStatus.PENDING,
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def update_transaction_status(
    db: AsyncSession,
    transaction_id: UUID,
    status: TransactionStatus,
    verified_by: Optional[UUID] = None,
) -> Transaction:
    """Update transaction status."""
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise ValueError("Transaction not found")

    transaction.status = status
    if verified_by:
        transaction.verified_by = verified_by
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def activate_subscription(
    db: AsyncSession,
    user_id: UUID,
    period_days: int = 30,
) -> Subscription:
    """Activate user subscription."""
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise ValueError("Subscription not found")

    now = datetime.utcnow()
    subscription.registration_fee_paid = True
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=period_days)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def renew_subscription(
    db: AsyncSession,
    user_id: UUID,
    period_days: int = 30,
) -> Subscription:
    """Renew user subscription."""
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise ValueError("Subscription not found")

    now = datetime.utcnow()
    if subscription.current_period_end and subscription.current_period_end > now:
        subscription.current_period_end = subscription.current_period_end + timedelta(days=period_days)
    else:
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=period_days)
    subscription.status = SubscriptionStatus.ACTIVE
    await db.commit()
    await db.refresh(subscription)
    return subscription