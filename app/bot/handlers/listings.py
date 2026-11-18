from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    get_cancel_keyboard,
    get_confirmation_keyboard,
    get_main_menu_keyboard,
    get_my_listings_keyboard,
)
from app.bot.loader import bot
from app.bot.states import ListingStates, SearchStates
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Category, PartCondition, PartListing, User
from app.schemas import PartCondition as PartConditionSchema
from app.services.subscription_service import check_subscription_access
from app.services.user_service import get_or_create_user

router = Router()
settings = get_settings()


# Category and brand constants
BRANDS = ["Samsung", "Apple", "Xiaomi", "Tecno", "Infinix", "Huawei", "Oppo", "Vivo", "Nokia", "Other"]


@router.message(F.text == "🔍 Find Part")
async def cmd_find_part(message: Message, state: FSMContext, db: AsyncSession = None):
    """Start part search flow."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    # Check subscription access
    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
    has_access, reason = await check_subscription_access(db, user.id)
    if not has_access:
        await message.answer(f"❌ {reason}", reply_markup=get_main_menu_keyboard())
        return

    # Get categories
    result = await db.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()

    await state.set_state(SearchStates.waiting_category)
    await message.answer(
        "🔍 <b>Find Repair Part</b>\n\n"
        "Step 1/3: Select category:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_categories_keyboard"]).get_categories_keyboard(categories),
    )


@router.callback_query(SearchStates.waiting_category, F.data.startswith("cat_"))
async def process_search_category(callback: CallbackQuery, state: FSMContext, db: AsyncSession = None):
    """Process category selection for search."""
    await callback.answer()

    if callback.data == "cancel":
        await state.clear()
        await callback.message.edit_text("Search cancelled.", reply_markup=get_main_menu_keyboard())
        return

    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)

    await state.set_state(SearchStates.waiting_brand)
    await callback.message.edit_text(
        "Step 2/3: Select brand:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_brands_keyboard"]).get_brands_keyboard(BRANDS),
    )


@router.callback_query(SearchStates.waiting_brand, F.data.startswith("brand_"))
async def process_search_brand(callback: CallbackQuery, state: FSMContext):
    """Process brand selection for search."""
    await callback.answer()

    if callback.data == "cancel":
        await state.clear()
        await callback.message.edit_text("Search cancelled.", reply_markup=get_main_menu_keyboard())
        return

    brand = callback.data.split("_", 1)[1]
    await state.update_data(brand=brand)

    await state.set_state(SearchStates.waiting_model)
    await callback.message.edit_text(
        f"Step 3/3: Enter model name (e.g., S22 Ultra, iPhone 13 Pro):",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_cancel_keyboard"]).get_cancel_keyboard(),
    )


@router.message(SearchStates.waiting_model, F.text)
async def process_search_model(message: Message, state: FSMContext, db: AsyncSession = None):
    """Process model input and perform search."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Search cancelled.", reply_markup=get_main_menu_keyboard())
        return

    model = message.text.strip()
    data = await state.get_data()

    # Perform search
    from app.schemas import PartListingSearchParams
    params = PartListingSearchParams(
        category_id=data.get("category_id"),
        brand=data.get("brand"),
        model_name=model,
        is_available=True,
        page=1,
        page_size=10,
    )

    # Build query
    from sqlalchemy import select, func
    query = select(PartListing).where(PartListing.is_available == True)

    if params.category_id:
        query = query.where(PartListing.category_id == params.category_id)
    if params.brand:
        query = query.where(PartListing.brand.ilike(f"%{params.brand}%"))
    if params.model_name:
        query = query.where(PartListing.model_name.ilike(f"%{params.model_name}%"))

    query = query.order_by(PartListing.created_at.desc()).limit(params.page_size)

    result = await db.execute(query)
    listings = result.scalars().all()

    await state.clear()

    if not listings:
        await message.answer(
            "No parts found matching your criteria. Try different filters.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # Send results
    for listing in listings:
        seller = await db.get(User, listing.seller_id)
        caption = (
            f"📦 <b>{listing.brand} {listing.model_name}</b>\n"
            f"🔧 {listing.part_name}\n"
            f"🏷️ Condition: {listing.condition.value.replace('_', ' ').title()}\n"
            f"💰 Price: {listing.price:,.2f} ETB\n"
            f"📍 Location: {seller.shop_location or 'Not specified'}\n"
            f"{'🤝 Negotiable' if listing.is_negotiable else '💵 Fixed Price'}"
        )

        # Use telegram_file_ids for photos
        if listing.telegram_file_ids:
            await message.answer_photo(
                photo=listing.telegram_file_ids[0],
                caption=caption,
                reply_markup=__import__("app.bot.keyboards", fromlist=["get_listing_actions_keyboard"]).get_listing_actions_keyboard(
                    str(listing.id), seller.telegram_id or 0
                ),
            )
        else:
            await message.answer(
                caption,
                reply_markup=__import__("app.bot.keyboards", fromlist=["get_listing_actions_keyboard"]).get_listing_actions_keyboard(
                    str(listing.id), seller.telegram_id or 0
                ),
            )

    await message.answer(
        "End of results. Use 'Find Part' to search again.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.message(F.text == "📦 Post Part")
async def cmd_post_part(message: Message, state: FSMContext, db: AsyncSession = None):
    """Start part listing creation flow."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
    has_access, reason = await check_subscription_access(db, user.id)
    if not has_access:
        await message.answer(f"❌ {reason}", reply_markup=get_main_menu_keyboard())
        return

    result = await db.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()

    await state.set_state(ListingStates.waiting_category)
    await message.answer(
        "📦 <b>Post New Part</b>\n\n"
        "Step 1/7: Select category:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_categories_keyboard"]).get_categories_keyboard(categories),
    )


@router.callback_query(ListingStates.waiting_category, F.data.startswith("cat_"))
async def process_listing_category(callback: CallbackQuery, state: FSMContext):
    """Process category selection for listing."""
    await callback.answer()

    if callback.data == "cancel":
        await state.clear()
        await callback.message.edit_text("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)

    await state.set_state(ListingStates.waiting_brand)
    await callback.message.edit_text(
        "Step 2/7: Select brand:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_brands_keyboard"]).get_brands_keyboard(BRANDS),
    )


@router.callback_query(ListingStates.waiting_brand, F.data.startswith("brand_"))
async def process_listing_brand(callback: CallbackQuery, state: FSMContext):
    """Process brand selection for listing."""
    await callback.answer()

    if callback.data == "cancel":
        await state.clear()
        await callback.message.edit_text("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    brand = callback.data.split("_", 1)[1]
    await state.update_data(brand=brand)

    await state.set_state(ListingStates.waiting_model)
    await callback.message.answer(
        "Step 3/7: Enter model name (e.g., S22 Ultra, iPhone 13 Pro):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ListingStates.waiting_model, F.text)
async def process_listing_model(message: Message, state: FSMContext):
    """Process model input for listing."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.update_data(model_name=message.text.strip())
    await state.set_state(ListingStates.waiting_part_name)
    await message.answer(
        "Step 4/7: Enter part name (e.g., Original OLED Screen, Clean Motherboard):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ListingStates.waiting_part_name, F.text)
async def process_listing_part_name(message: Message, state: FSMContext):
    """Process part name input for listing."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.update_data(part_name=message.text.strip())
    await state.set_state(ListingStates.waiting_condition)
    await message.answer(
        "Step 5/7: Select condition:",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_conditions_keyboard"]).get_conditions_keyboard(),
    )


@router.callback_query(ListingStates.waiting_condition, F.data.startswith("cond_"))
async def process_listing_condition(callback: CallbackQuery, state: FSMContext):
    """Process condition selection for listing."""
    await callback.answer()

    if callback.data == "cancel":
        await state.clear()
        await callback.message.edit_text("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    condition = callback.data.split("_", 1)[1]
    try:
        part_condition = PartCondition(condition)
    except ValueError:
        await callback.message.answer("Invalid condition. Please try again.")
        return

    await state.update_data(condition=part_condition)

    await state.set_state(ListingStates.waiting_price)
    await callback.message.answer(
        "Step 6/7: Enter price in ETB (e.g., 1500):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ListingStates.waiting_price, F.text)
async def process_listing_price(message: Message, state: FSMContext):
    """Process price input for listing."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Invalid price. Please enter a valid number (e.g., 1500):")
        return

    await state.update_data(price=price)
    await state.set_state(ListingStates.waiting_photos)
    await message.answer(
        "Step 7/7: Send photo(s) of the part (max 5).\n"
        "Send all photos then tap 'Done', or tap 'Skip' if no photos.",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_cancel_keyboard"]).get_cancel_keyboard(),
    )


@router.message(ListingStates.waiting_photos, F.photo)
async def process_listing_photos(message: Message, state: FSMContext):
    """Process photo uploads for listing."""
    data = await state.get_data()
    telegram_file_ids = data.get("telegram_file_ids", [])

    # Get the largest photo
    photo: PhotoSize = message.photo[-1]
    telegram_file_ids.append(photo.file_id)

    if len(telegram_file_ids) >= 5:
        await state.update_data(telegram_file_ids=telegram_file_ids)
        await state.set_state(ListingStates.waiting_confirmation)
        await show_listing_preview(message, state)
    else:
        await state.update_data(telegram_file_ids=telegram_file_ids)
        await message.answer(f"Photo {len(telegram_file_ids)}/5 added. Send more or tap 'Done'.")


@router.message(ListingStates.waiting_photos, F.text.in_(["Done", "Skip", "❌ Cancel"]))
async def process_listing_photos_done(message: Message, state: FSMContext):
    """Handle done/skip for photos."""
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    await state.set_state(ListingStates.waiting_confirmation)
    await show_listing_preview(message, state)


async def show_listing_preview(message: Message, state: FSMContext):
    """Show listing preview for confirmation."""
    data = await state.get_data()

    preview = (
        "📋 <b>Listing Preview</b>\n\n"
        f"Category ID: {data.get('category_id')}\n"
        f"Brand: {data.get('brand')}\n"
        f"Model: {data.get('model_name')}\n"
        f"Part: {data.get('part_name')}\n"
        f"Condition: {data.get('condition').value.replace('_', ' ').title()}\n"
        f"Price: {data.get('price'):,.2f} ETB\n"
        f"Photos: {len(data.get('telegram_file_ids', []))}"
    )

    await message.answer(preview, reply_markup=get_confirmation_keyboard())


@router.message(ListingStates.waiting_confirmation, F.text.in_(["✅ Confirm", "✏️ Edit", "❌ Cancel"]))
async def process_listing_confirmation(message: Message, state: FSMContext, db: AsyncSession = None):
    """Process listing confirmation."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Listing cancelled.", reply_markup=get_main_menu_keyboard())
        return

    if message.text == "✏️ Edit":
        await message.answer("Editing not implemented yet. Please cancel and start over.")
        return

    # Confirm - create listing
    data = await state.get_data()
    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)

    listing = PartListing(
        seller_id=user.id,
        category_id=data["category_id"],
        brand=data["brand"],
        model_name=data["model_name"],
        part_name=data["part_name"],
        condition=data["condition"],
        price=data["price"],
        telegram_file_ids=data.get("telegram_file_ids", []),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    await state.clear()
    await message.answer(
        f"✅ <b>Listing posted successfully!</b>\n\n"
        f"Your part is now visible to other technicians.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.message(F.text == "📋 My Listings")
async def cmd_my_listings(message: Message, db: AsyncSession = None):
    """Show user's listings."""
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    user = await get_or_create_user(db, message.from_user.id, message.from_user.username)

    result = await db.execute(
        select(PartListing)
        .where(PartListing.seller_id == user.id)
        .order_by(PartListing.created_at.desc())
        .limit(10)
    )
    listings = result.scalars().all()

    if not listings:
        await message.answer("You have no listings yet. Tap 'Post Part' to create one.", reply_markup=get_main_menu_keyboard())
        return

    await message.answer(
        "📋 <b>Your Listings</b>",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_my_listings_keyboard"]).get_my_listings_keyboard(listings, 1, False),
    )


@router.callback_query(F.data.startswith("mylist_"))
async def callback_my_listing(callback: CallbackQuery, db: AsyncSession = None):
    """Handle my listing selection."""
    await callback.answer()

    if callback.data.startswith("mylist_page_"):
        # Pagination not fully implemented
        return

    listing_id = callback.data.split("_")[1]
    if db is None:
        async for db_session in get_db():
            db = db_session
            break

    from uuid import UUID
    listing = await db.get(PartListing, UUID(listing_id))
    if not listing:
        await callback.message.answer("Listing not found.")
        return

    status_emoji = "✅" if listing.is_available else "❌"
    await callback.message.answer(
        f"{status_emoji} <b>{listing.brand} {listing.model_name}</b>\n"
        f"🔧 {listing.part_name}\n"
        f"🏷️ {listing.condition.value.replace('_', ' ').title()}\n"
        f"💰 {listing.price:,.2f} ETB\n"
        f"📅 Posted: {listing.created_at.strftime('%Y-%m-%d')}",
        reply_markup=__import__("app.bot.keyboards", fromlist=["get_listing_actions_keyboard"]).get_listing_actions_keyboard(
            str(listing.id), callback.from_user.id
        ),
    )