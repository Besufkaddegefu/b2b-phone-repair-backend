from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import get_cancel_keyboard, get_main_menu_keyboard
from app.bot.loader import bot
from app.bot.states import PaymentStates
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Transaction, TransactionStatus, User
from app.services.user_service import create_transaction, get_or_create_user, update_transaction_status, activate_subscription

router = Router()
settings = get_settings()

ADMIN_IDS = settings.admin_telegram_ids_list


@router.message(PaymentStates.waiting_receipt, F.photo)
async def process_payment_receipt(message: Message, state: FSMContext, db: AsyncSession = None):
    """Process uploaded payment receipt."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)

    # Get largest photo
    photo: PhotoSize = message.photo[-1]

    # Create transaction record
    transaction = await create_transaction(
        db=db,
        user_id=user.id,
        amount=0,  # Amount will be verified by admin
        payment_type="registration",  # or monthly_subscription
        payment_method="manual_receipt",
        transaction_reference=f"MANUAL_{user.id}_{message.message_id}",
        receipt_image_url=photo.file_id,  # Store telegram file_id
    )

    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=(
                    f"💰 <b>New Payment Receipt</b>\n\n"
                    f"User: {user.full_name} (@{user.telegram_username or 'N/A'})\n"
                    f"Phone: {user.phone_number}\n"
                    f"Shop: {user.shop_name}\n"
                    f"Transaction ID: {transaction.id}\n"
                    f"Type: Manual Receipt Upload"
                ),
                reply_markup=__import__("app.bot.keyboards", fromlist=["get_admin_approval_keyboard"]).get_admin_approval_keyboard(
                    str(transaction.id), user.telegram_id or 0
                ),
            )
        except Exception:
            pass  # Admin might have blocked bot

    await state.clear()
    await message.answer(
        "✅ Receipt uploaded successfully!\n\n"
        "An admin will review and approve your payment. You'll be notified once it's processed.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_approve_"))
async def callback_admin_approve(callback: CallbackQuery, db: AsyncSession = None):
    """Handle admin approval of payment."""
    await callback.answer()

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Not authorized", show_alert=True)
        return

    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    from uuid import UUID
    transaction_id = UUID(callback.data.split("_")[2])

    # Update transaction
    transaction = await update_transaction_status(
        db, transaction_id, TransactionStatus.COMPLETED, verified_by=callback.from_user.id
    )

    # Activate subscription for user
    await activate_subscription(db, transaction.user_id)

    # Notify user
    user = await db.get(User, transaction.user_id)
    if user and user.telegram_id:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text="✅ <b>Payment Approved!</b>\n\nYour subscription is now active. You can access all marketplace features.",
            )
        except Exception:
            pass

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>APPROVED</b> by admin",
        reply_markup=None,
    )


@router.callback_query(F.data.startswith("admin_reject_"))
async def callback_admin_reject(callback: CallbackQuery, db: AsyncSession = None):
    """Handle admin rejection of payment."""
    await callback.answer()

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Not authorized", show_alert=True)
        return

    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    from uuid import UUID
    transaction_id = UUID(callback.data.split("_")[2])

    # Update transaction
    await update_transaction_status(
        db, transaction_id, TransactionStatus.FAILED, verified_by=callback.from_user.id
    )

    # Notify user
    transaction = await db.get(Transaction, transaction_id)
    user = await db.get(User, transaction.user_id) if transaction else None
    if user and user.telegram_id:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text="❌ <b>Payment Rejected</b>\n\nYour payment receipt was not approved. Please try again or contact support.",
            )
        except Exception:
            pass

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>REJECTED</b> by admin",
        reply_markup=None,
    )


@router.callback_query(F.data.startswith("pay_"))
async def callback_payment_method(callback: CallbackQuery, state: FSMContext):
    """Handle payment method selection."""
    await callback.answer()

    method = callback.data.split("_")[1]

    if method == "chapa":
        await callback.message.edit_text(
            "💳 <b>Chapa Payment</b>\n\n"
            "Chapa integration coming soon.\n"
            "For now, please use 'Upload Receipt' option.",
            reply_markup=__import__("app.bot.keyboards", fromlist=["get_payment_methods_keyboard"]).get_payment_methods_keyboard(),
        )
    elif method == "telebirr":
        await callback.message.edit_text(
            "📱 <b>Telebirr Payment</b>\n\n"
            "Telebirr integration coming soon.\n"
            "For now, please use 'Upload Receipt' option.",
            reply_markup=__import__("app.bot.keyboards", fromlist=["get_payment_methods_keyboard"]).get_payment_methods_keyboard(),
        )
    elif method == "cbe":
        await callback.message.edit_text(
            "🏦 <b>CBE Birr Payment</b>\n\n"
            "CBE Birr integration coming soon.\n"
            "For now, please use 'Upload Receipt' option.",
            reply_markup=__import__("app.bot.keyboards", fromlist=["get_payment_methods_keyboard"]).get_payment_methods_keyboard(),
        )
    elif method == "manual":
        await state.set_state(PaymentStates.waiting_receipt)
        await callback.message.answer(
            "Please upload a photo/screenshot of your payment receipt.\n"
            "An admin will review and approve it.",
            reply_markup=get_cancel_keyboard(),
        )