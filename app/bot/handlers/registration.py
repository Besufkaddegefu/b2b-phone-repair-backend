from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    get_cancel_keyboard,
    get_contact_keyboard,
    get_main_menu_keyboard,
)
from app.bot.loader import bot
from app.bot.states import RegistrationStates
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.services.user_service import get_or_create_user, update_user_from_registration

router = Router()
settings = get_settings()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: AsyncSession = None):
    """Handle /start command - check if user exists or start registration."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)

    if user.full_name and user.phone_number:
        # Existing user - show main menu
        await message.answer(
            f"Welcome back, {user.full_name}! 👋\n"
            f"Shop: {user.shop_name or 'Not set'}\n"
            f"Location: {user.shop_location or 'Not set'}",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        # New user - start registration
        await state.set_state(RegistrationStates.waiting_full_name)
        await message.answer(
            "Welcome to B2B Phone Repair Marketplace! 🛠️\n\n"
            "Let's set up your technician profile.\n\n"
            "Step 1/4: What's your full name?",
            reply_markup=get_cancel_keyboard(),
        )


@router.message(RegistrationStates.waiting_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext):
    """Process full name input."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Registration cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.update_data(full_name=message.text.strip())
    await state.set_state(RegistrationStates.waiting_shop_name)
    await message.answer(
        "Step 2/4: What's your shop name? (e.g., Bole Phone Repair)",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(RegistrationStates.waiting_shop_name, F.text)
async def process_shop_name(message: Message, state: FSMContext):
    """Process shop name input."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Registration cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.update_data(shop_name=message.text.strip())
    await state.set_state(RegistrationStates.waiting_shop_location)
    await message.answer(
        "Step 3/4: What's your shop location? (e.g., Bole, Merkato, Megenagna)",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(RegistrationStates.waiting_shop_location, F.text)
async def process_shop_location(message: Message, state: FSMContext):
    """Process shop location input."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Registration cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.update_data(shop_location=message.text.strip())
    await state.set_state(RegistrationStates.waiting_contact)
    await message.answer(
        "Step 4/4: Please share your phone number for verification.",
        reply_markup=get_contact_keyboard(),
    )


@router.message(RegistrationStates.waiting_contact, F.contact)
async def process_contact(message: Message, state: FSMContext, db: AsyncSession = None):
    """Process contact sharing."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    contact: Contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("Please share your own contact.", reply_markup=get_contact_keyboard())
        return

    data = await state.get_data()
    user = await update_user_from_registration(
        db,
        message.from_user.id,
        message.from_user.username,
        data["full_name"],
        data["shop_name"],
        data["shop_location"],
        contact.phone_number,
    )

    await state.clear()

    # Check subscription status
    from app.services.subscription_service import get_subscription_status
    sub_status = await get_subscription_status(db, user.id)

    if sub_status in ("inactive", "past_due", "pending_approval"):
        await message.answer(
            f"Registration complete! Welcome, {user.full_name}! 🎉\n\n"
            f"⚠️ <b>Subscription Required</b>\n"
            f"To access the marketplace, you need to activate your subscription.\n"
            f"This includes a one-time registration fee + first month subscription.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await message.answer(
            f"Registration complete! Welcome, {user.full_name}! 🎉\n\n"
            f"Your subscription is active. You can now buy and sell parts.",
            reply_markup=get_main_menu_keyboard(),
        )


@router.message(RegistrationStates.waiting_contact, F.text == "❌ Cancel")
async def cancel_registration(message: Message, state: FSMContext):
    """Cancel registration."""
    await state.clear()
    await message.answer("Registration cancelled.", reply_markup=get_main_menu_keyboard())


@router.message(F.text == "❌ Cancel")
async def cancel_any(message: Message, state: FSMContext):
    """Global cancel handler."""
    await state.clear()
    await message.answer("Action cancelled.", reply_markup=get_main_menu_keyboard())


@router.message(F.text == "ℹ️ Help")
async def cmd_help(message: Message):
    """Show help information."""
    await message.answer(
        "<b>B2B Phone Repair Marketplace - Help</b> 📖\n\n"
        "<b>🔍 Find Part</b> - Search for repair parts by category, brand, model\n"
        "<b>📦 Post Part</b> - List a part for sale (requires active subscription)\n"
        "<b>📋 My Listings</b> - View and manage your active listings\n"
        "<b>💳 Subscription</b> - Check and manage your subscription status\n"
        "<b>🌐 Web Login</b> - Link your account to the web dashboard\n\n"
        "<b>Subscription Model:</b>\n"
        "• One-time registration fee\n"
        "• Monthly subscription\n"
        "• Pay via Chapa, Telebirr, CBE Birr, or upload receipt\n\n"
        "For support, contact admin.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.message(F.text == "💳 Subscription")
async def cmd_subscription(message: Message, db: AsyncSession = None):
    """Show subscription status."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    from app.services.subscription_service import get_user_subscription
    from app.bot.keyboards import get_subscription_status_keyboard

    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
    subscription = await get_user_subscription(db, user.id)

    if not subscription:
        await message.answer(
            "No subscription found. Please complete registration first.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    status_text = {
        "active": "✅ Active",
        "past_due": "⚠️ Past Due",
        "canceled": "❌ Canceled",
        "pending_approval": "⏳ Pending Approval",
    }.get(subscription.status.value, subscription.status.value)

    await message.answer(
        f"<b>Subscription Status</b>\n\n"
        f"Status: {status_text}\n"
        f"Registration Fee Paid: {'Yes' if subscription.registration_fee_paid else 'No'}\n"
        f"Monthly Rate: {subscription.monthly_rate:.2f} ETB\n"
        f"Period: {subscription.current_period_start or 'N/A'} to {subscription.current_period_end or 'N/A'}",
        reply_markup=get_subscription_status_keyboard(subscription.status.value),
    )


@router.callback_query(F.data == "sub_pay")
async def callback_sub_pay(callback: CallbackQuery):
    """Handle pay subscription callback."""
    await callback.answer()
    await callback.message.edit_text(
        "Choose payment method:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_payment_methods_keyboard"]).get_payment_methods_keyboard(),
    )


@router.callback_query(F.data == "sub_receipt")
async def callback_sub_receipt(callback: CallbackQuery, state: FSMContext):
    """Handle upload receipt callback."""
    await callback.answer()
    from app.bot.states import PaymentStates
    await state.set_state(PaymentStates.waiting_receipt)
    await callback.message.answer(
        "Please upload a photo/screenshot of your payment receipt.\n"
        "An admin will review and approve it.",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(F.data == "close")
async def callback_close(callback: CallbackQuery):
    """Close inline keyboard."""
    await callback.answer()
    await callback.message.delete()


@router.message(Command("web_login"))
async def cmd_web_login(message: Message, state: FSMContext, db: AsyncSession = None):
    """Generate web login link code."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    from app.services.user_service import generate_web_login_code
    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
    code = await generate_web_login_code(db, user.id)

    await message.answer(
        f"🔗 <b>Web Dashboard Login</b>\n\n"
        f"Your one-time login code: <code>{code}</code>\n\n"
        f"1. Go to the web dashboard\n"
        f"2. Click 'Login with Telegram'\n"
        f"3. Enter this code\n\n"
        f"Code expires in 10 minutes.",
        reply_markup=get_main_menu_keyboard(),
    )