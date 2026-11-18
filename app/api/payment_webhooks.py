import hashlib
import hmac
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.models import Transaction, TransactionStatus, User, Subscription, SubscriptionStatus
from app.services.user_service import activate_subscription, update_transaction_status

router = APIRouter(prefix="/webhook", tags=["payments"])
settings = get_settings()
logger = logging.getLogger(__name__)


def verify_chapa_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Chapa webhook signature."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_telebirr_signature(payload: dict, public_key: str) -> bool:
    """Verify Telebirr webhook signature (simplified)."""
    # Telebirr uses RSA signature verification
    # This is a placeholder - implement proper RSA verification
    return True


def verify_cbe_signature(payload: dict, secret: str) -> bool:
    """Verify CBE Birr webhook signature."""
    # CBE uses HMAC-SHA256 similar to Chapa
    return True


@router.post("/chapa")
async def chapa_webhook(
    request: Request,
    x_chapa_signature: Optional[str] = Header(None, alias="X-Chapa-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Chapa payment webhook."""
    payload = await request.body()
    
    # Verify signature
    if not x_chapa_signature or not verify_chapa_signature(payload, x_chapa_signature, settings.CHAPA_WEBHOOK_SECRET):
        logger.warning("Invalid Chapa signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = json.loads(payload)
    tx_ref = data.get("tx_ref")
    status = data.get("status")
    
    if not tx_ref:
        raise HTTPException(status_code=400, detail="Missing tx_ref")
    
    # Find transaction
    result = await db.execute(select(Transaction).where(Transaction.transaction_reference == tx_ref))
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        logger.warning(f"Transaction not found: {tx_ref}")
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != TransactionStatus.PENDING:
        logger.info(f"Transaction already processed: {tx_ref}")
        return {"status": "already_processed"}
    
    if status == "success":
        await update_transaction_status(db, transaction.id, TransactionStatus.COMPLETED)
        await activate_subscription(db, transaction.user_id)
        logger.info(f"Chapa payment approved: {tx_ref}")
    else:
        await update_transaction_status(db, transaction.id, TransactionStatus.FAILED)
        logger.info(f"Chapa payment failed: {tx_ref}")
    
    return {"status": "ok"}


@router.post("/telebirr")
async def telebirr_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Telebirr payment webhook."""
    data = await request.json()
    
    # Verify signature (implement proper RSA verification)
    if not verify_telebirr_signature(data, settings.TELEBIRR_PUBLIC_KEY):
        logger.warning("Invalid Telebirr signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    out_trade_no = data.get("out_trade_no")
    trade_status = data.get("trade_status")
    
    if not out_trade_no:
        raise HTTPException(status_code=400, detail="Missing out_trade_no")
    
    result = await db.execute(select(Transaction).where(Transaction.transaction_reference == out_trade_no))
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != TransactionStatus.PENDING:
        return {"status": "already_processed"}
    
    if trade_status == "TRADE_SUCCESS":
        await update_transaction_status(db, transaction.id, TransactionStatus.COMPLETED)
        await activate_subscription(db, transaction.user_id)
    else:
        await update_transaction_status(db, transaction.id, TransactionStatus.FAILED)
    
    return {"status": "ok"}


@router.post("/cbe")
async def cbe_webhook(
    request: Request,
    x_cbe_signature: Optional[str] = Header(None, alias="X-CBE-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle CBE Birr payment webhook."""
    payload = await request.body()
    data = json.loads(payload)
    
    # Verify signature
    if not verify_cbe_signature(data, settings.CBE_WEBHOOK_SECRET):
        logger.warning("Invalid CBE signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    merchant_order_id = data.get("merchant_order_id")
    status = data.get("status")
    
    if not merchant_order_id:
        raise HTTPException(status_code=400, detail="Missing merchant_order_id")
    
    result = await db.execute(select(Transaction).where(Transaction.transaction_reference == merchant_order_id))
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != TransactionStatus.PENDING:
        return {"status": "already_processed"}
    
    if status == "SUCCESS":
        await update_transaction_status(db, transaction.id, TransactionStatus.COMPLETED)
        await activate_subscription(db, transaction.user_id)
    else:
        await update_transaction_status(db, transaction.id, TransactionStatus.FAILED)
    
    return {"status": "ok"}


@router.post("/initiate/chapa")
async def initiate_chapa_payment(
    user_id: UUID,
    amount: float,
    tx_ref: str,
    db: AsyncSession = Depends(get_db),
):
    """Initiate Chapa payment - returns payment URL."""
    import httpx
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.CHAPA_BASE_URL}/transaction/initialize",
            headers={"Authorization": f"Bearer {settings.CHAPA_SECRET_KEY}"},
            json={
                "amount": str(amount),
                "currency": "ETB",
                "email": user.phone_number + "@b2bphone.local",  # Chapa requires email
                "first_name": user.full_name.split()[0] if user.full_name else "User",
                "last_name": user.full_name.split()[-1] if user.full_name else "",
                "phone_number": user.phone_number,
                "tx_ref": tx_ref,
                "callback_url": f"{settings.TELEGRAM_WEBHOOK_URL.replace('/webhook/tg', '')}/webhook/chapa",
                "return_url": f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}",
                "customization": {
                    "title": "B2B Phone Repair",
                    "description": "Subscription payment",
                },
            },
        )
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to initiate Chapa payment")
    
    data = response.json()
    return {"checkout_url": data.get("data", {}).get("checkout_url")}


@router.post("/initiate/telebirr")
async def initiate_telebirr_payment(
    user_id: UUID,
    amount: float,
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
):
    """Initiate Telebirr payment - returns payment URL."""
    import httpx
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Telebirr uses different API - this is a simplified version
    # Actual implementation requires proper Telebirr SDK or API integration
    
    payment_data = {
        "app_id": settings.TELEBIRR_APP_ID,
        "app_key": settings.TELEBIRR_APP_KEY,
        "out_trade_no": out_trade_no,
        "total_amount": str(amount),
        "subject": "B2B Phone Repair Subscription",
        "body": "Monthly subscription payment",
        "notify_url": f"{settings.TELEGRAM_WEBHOOK_URL.replace('/webhook/tg', '')}/webhook/telebirr",
        "return_url": f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}",
    }
    
    # In production, sign the data and redirect to Telebirr gateway
    return {"payment_data": payment_data, "gateway_url": "https://pay.telebirr.com"}


@router.post("/initiate/cbe")
async def initiate_cbe_payment(
    user_id: UUID,
    amount: float,
    merchant_order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Initiate CBE Birr payment."""
    # CBE Birr integration - placeholder
    return {"message": "CBE integration pending"}


# Admin endpoint to create payment transaction
@router.post("/admin/create-payment")
async def create_payment_transaction(
    user_id: UUID,
    amount: float,
    payment_type: str,
    payment_method: str,
    db: AsyncSession = Depends(get_db),
):
    """Create a payment transaction record (admin use)."""
    from app.services.user_service import create_transaction
    import uuid
    
    tx_ref = f"{payment_method.upper()}_{user_id}_{uuid.uuid4().hex[:8]}"
    
    transaction = await create_transaction(
        db=db,
        user_id=user_id,
        amount=amount,
        payment_type=payment_type,
        payment_method=payment_method,
        transaction_reference=tx_ref,
    )
    
    # Return initiation URL based on method
    if payment_method == "chapa":
        result = await initiate_chapa_payment(user_id, amount, tx_ref, db)
        return {"transaction_id": str(transaction.id), "checkout_url": result.get("checkout_url")}
    elif payment_method == "telebirr":
        result = await initiate_telebirr_payment(user_id, amount, tx_ref, db)
        return {"transaction_id": str(transaction.id), "payment_data": result.get("payment_data")}
    else:
        return {"transaction_id": str(transaction.id), "message": "Manual payment - upload receipt"}