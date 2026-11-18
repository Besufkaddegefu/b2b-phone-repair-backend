from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.models import Category, PartCondition
from app.schemas import PartCondition as PartConditionSchema


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent menu keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 Find Part")
    builder.button(text="📦 Post Part")
    builder.button(text="📋 My Listings")
    builder.button(text="💳 Subscription")
    builder.button(text="🌐 Web Login")
    builder.button(text="ℹ️ Help")
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


def get_contact_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard to request contact sharing."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Share Contact", request_contact=True)
    builder.button(text="❌ Cancel")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Simple cancel keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Cancel")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Inline keyboard for category selection."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat_{cat.id}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_brands_keyboard(brands: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard for brand selection."""
    builder = InlineKeyboardBuilder()
    for brand in brands:
        builder.button(text=brand, callback_data=f"brand_{brand}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_conditions_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for condition selection."""
    builder = InlineKeyboardBuilder()
    conditions = [
        (PartConditionSchema.ORIGINAL_PULLED, "🔧 Original (Pulled)"),
        (PartConditionSchema.OEM_NEW, "✨ OEM New"),
        (PartConditionSchema.AFTERMARKET, "📦 Aftermarket"),
        (PartConditionSchema.FOR_PARTS_ONLY, "⚠️ For Parts Only"),
    ]
    for cond, label in conditions:
        builder.button(text=label, callback_data=f"cond_{cond.value}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_payment_methods_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for payment method selection."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Chapa", callback_data="pay_chapa")
    builder.button(text="📱 Telebirr", callback_data="pay_telebirr")
    builder.button(text="🏦 CBE Birr", callback_data="pay_cbe")
    builder.button(text="📸 Upload Receipt", callback_data="pay_manual")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_listing_actions_keyboard(listing_id: str, seller_telegram_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for listing actions (buyer view)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📞 Contact Seller", url=f"tg://user?id={seller_telegram_id}")
    builder.button(text="🌐 Open in Mini App", url=f"https://t.me/yourbot/app?startapp=listing_{listing_id}")
    builder.button(text="❌ Close", callback_data="close")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_my_listings_keyboard(listings: list, page: int, has_next: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for my listings with pagination."""
    builder = InlineKeyboardBuilder()
    for listing in listings:
        status_emoji = "✅" if listing.is_available else "❌"
        builder.button(
            text=f"{status_emoji} {listing.brand} {listing.model_name} - {listing.part_name}",
            callback_data=f"mylist_{listing.id}"
        )
    if page > 1:
        builder.button(text="⬅️ Prev", callback_data=f"mylist_page_{page-1}")
    if has_next:
        builder.button(text="Next ➡️", callback_data=f"mylist_page_{page+1}")
    builder.button(text="❌ Close", callback_data="close")
    builder.adjust(1)
    return builder.as_markup()


def get_subscription_status_keyboard(status: str) -> InlineKeyboardMarkup:
    """Inline keyboard for subscription management."""
    builder = InlineKeyboardBuilder()
    if status in ("inactive", "past_due", "pending_approval"):
        builder.button(text="💳 Pay Now", callback_data="sub_pay")
        builder.button(text="📸 Upload Receipt", callback_data="sub_receipt")
    else:
        builder.button(text="🔄 Renew Early", callback_data="sub_renew")
    builder.button(text="❌ Close", callback_data="close")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_admin_approval_keyboard(transaction_id: str, user_telegram_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for admin payment approval."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"admin_approve_{transaction_id}")
    builder.button(text="❌ Reject", callback_data=f"admin_reject_{transaction_id}")
    builder.button(text="👤 View User", url=f"tg://user?id={user_telegram_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """Simple confirmation keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Confirm")
    builder.button(text="✏️ Edit")
    builder.button(text="❌ Cancel")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)