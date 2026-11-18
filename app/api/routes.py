from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from uuid import UUID
import csv
import io

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.models import Category, PartListing, User, Subscription, Transaction, UserRole, SubscriptionStatus, TransactionStatus
from app.schemas import (
    CategoryResponse,
    PartListingCreate,
    PartListingResponse,
    PartListingSearchParams,
    PartListingUpdate,
    PaginatedResponse,
    UserResponse,
    UserUpdate,
    UserWithSubscriptionResponse,
    AdminStatsResponse,
    AdminUserSearchParams,
    AdminTransactionSearchParams,
    UserRoleUpdate,
    BulkUploadResult,
    AnalyticsParams,
    AnalyticsData,
    AnalyticsPeriod,
    TransactionResponse,
    SubscriptionResponse,
)

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in user_update.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


@router.post("/listings", response_model=PartListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    listing_data: PartListingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing = PartListing(seller_id=current_user.id, **listing_data.model_dump())
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return listing


@router.get("/listings", response_model=PaginatedResponse[PartListingResponse])
async def search_listings(
    params: PartListingSearchParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    query = select(PartListing).where(PartListing.is_available == params.is_available)

    if params.category_id:
        query = query.where(PartListing.category_id == params.category_id)
    if params.brand:
        query = query.where(PartListing.brand.ilike(f"%{params.brand}%"))
    if params.model_name:
        query = query.where(PartListing.model_name.ilike(f"%{params.model_name}%"))
    if params.condition:
        query = query.where(PartListing.condition == params.condition)
    if params.min_price is not None:
        query = query.where(PartListing.price >= params.min_price)
    if params.max_price is not None:
        query = query.where(PartListing.price <= params.max_price)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.order_by(PartListing.created_at.desc())
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/listings/{listing_id}", response_model=PartListingResponse)
async def get_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(PartListing, UUID(listing_id))
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.patch("/listings/{listing_id}", response_model=PartListingResponse)
async def update_listing(
    listing_id: str,
    listing_update: PartListingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(PartListing, UUID(listing_id))
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to update this listing")

    for field, value in listing_update.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    await db.commit()
    await db.refresh(listing)
    return listing


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(PartListing, UUID(listing_id))
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to delete this listing")

    await db.delete(listing)
    await db.commit()


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/admin/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Total users
    total_users = await db.scalar(select(func.count(User.id)))

    # Active subscriptions
    active_subs = await db.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE)
    )

    # Pending payments
    pending_payments = await db.scalar(
        select(func.count(Transaction.id)).where(Transaction.status == TransactionStatus.PENDING)
    )

    # Total listings
    total_listings = await db.scalar(select(func.count(PartListing.id)))

    # Revenue this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= month_start,
        )
    )
    revenue_this_month = revenue_result.scalar() or 0

    # New users this month
    new_users = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= month_start)
    )

    return AdminStatsResponse(
        total_users=total_users or 0,
        active_subscriptions=active_subs or 0,
        pending_payments=pending_payments or 0,
        total_listings=total_listings or 0,
        revenue_this_month=float(revenue_this_month),
        new_users_this_month=new_users or 0,
    )


@router.get("/admin/users", response_model=PaginatedResponse[UserWithSubscriptionResponse])
async def get_admin_users(
    params: AdminUserSearchParams = Depends(),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).options(selectinload(User.subscription))

    if params.search:
        search_term = f"%{params.search}%"
        query = query.where(
            or_(
                User.full_name.ilike(search_term),
                User.phone_number.ilike(search_term),
                User.telegram_username.ilike(search_term),
                User.shop_name.ilike(search_term),
            )
        )

    if params.role:
        query = query.where(User.role == params.role)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.order_by(User.created_at.desc())
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

    result = await db.execute(query)
    users = result.scalars().all()

    # Convert to response with subscription
    items = []
    for user in users:
        user_dict = UserResponse.model_validate(user).model_dump()
        if user.subscription:
            user_dict["subscription"] = SubscriptionResponse.model_validate(user.subscription).model_dump()
        items.append(UserWithSubscriptionResponse.model_validate(user_dict))

    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.patch("/admin/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    role_update: UserRoleUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role_update.role
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/admin/transactions", response_model=PaginatedResponse[TransactionResponse])
async def get_admin_transactions(
    params: AdminTransactionSearchParams = Depends(),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Transaction).options(selectinload(Transaction.user))

    if params.status:
        query = query.where(Transaction.status == params.status)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.order_by(Transaction.created_at.desc())
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.post("/admin/transactions/{transaction_id}/approve", response_model=TransactionResponse)
async def approve_transaction(
    transaction_id: str,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    transaction = await db.get(Transaction, UUID(transaction_id))
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transaction is not pending")

    transaction.status = TransactionStatus.COMPLETED
    transaction.verified_by = admin_user.id

    # Activate subscription for the user
    from app.services.user_service import activate_subscription
    await activate_subscription(db, transaction.user_id)

    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.post("/admin/transactions/{transaction_id}/reject", response_model=TransactionResponse)
async def reject_transaction(
    transaction_id: str,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    transaction = await db.get(Transaction, UUID(transaction_id))
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transaction is not pending")

    transaction.status = TransactionStatus.FAILED
    transaction.verified_by = admin_user.id

    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.post("/admin/listings/bulk-upload", response_model=BulkUploadResult)
async def bulk_upload_listings(
    file: UploadFile = File(...),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be CSV or Excel")

    content = await file.read()

    # Parse CSV or Excel
    rows = []
    if file.filename.endswith('.csv'):
        text = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    elif file.filename.endswith(('.xlsx', '.xls')):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows.append(dict(zip(headers, row)))
    else:
        raise HTTPException(status_code=400, detail="File must be CSV or Excel")

    success = 0
    failed = 0
    errors = []

    for idx, row in enumerate(rows, start=1):
        try:
            # Validate required fields
            required = ['category', 'brand', 'model_name', 'part_name', 'condition', 'price']
            for field in required:
                if not row.get(field) or str(row.get(field)).strip() == '':
                    raise ValueError(f"Missing required field: {field}")

            # Find category
            category_result = await db.execute(
                select(Category).where(Category.name == row['category'].strip())
            )
            category = category_result.scalar_one_or_none()
            if not category:
                raise ValueError(f"Category not found: {row['category']}")

            # Validate condition
            try:
                condition = row['condition'].strip().lower()
                # Check if valid enum value
                from app.schemas import PartCondition
                PartCondition(condition)
            except ValueError:
                raise ValueError(f"Invalid condition: {row['condition']}")

            # Create listing
            listing = PartListing(
                seller_id=admin_user.id,
                category_id=category.id,
                brand=row['brand'].strip(),
                model_name=row['model_name'].strip(),
                part_name=row['part_name'].strip(),
                condition=condition,
                price=float(row['price']),
                is_negotiable=str(row.get('is_negotiable', 'true')).lower() == 'true',
                description=row.get('description', '').strip() or None,
                image_urls=[url.strip() for url in row.get('image_urls', '').split(',') if url.strip()],
            )
            db.add(listing)
            success += 1

        except Exception as e:
            failed += 1
            errors.append({"row": idx, "error": str(e)})

    await db.commit()

    return BulkUploadResult(success=success, failed=failed, errors=errors)


@router.get("/admin/analytics", response_model=AnalyticsData)
async def get_admin_analytics(
    params: AnalyticsParams = Depends(),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Determine date range
    now = datetime.utcnow()
    if params.period == AnalyticsPeriod.DAY:
        start_date = now - timedelta(days=1)
        group_format = "%H:00"
    elif params.period == AnalyticsPeriod.WEEK:
        start_date = now - timedelta(weeks=1)
        group_format = "%Y-%m-%d"
    elif params.period == AnalyticsPeriod.MONTH:
        start_date = now - timedelta(days=30)
        group_format = "%Y-%m-%d"
    else:  # YEAR
        start_date = now - timedelta(days=365)
        group_format = "%Y-%m"

    # Revenue over time
    revenue_query = """
        SELECT date_trunc('day', created_at) as date, SUM(amount) as amount
        FROM transactions
        WHERE status = 'completed' AND created_at >= :start_date
        GROUP BY date_trunc('day', created_at)
        ORDER BY date
    """
    revenue_result = await db.execute(
        select(func.date_trunc('day', Transaction.created_at).label('date'),
               func.sum(Transaction.amount).label('amount'))
        .where(Transaction.status == TransactionStatus.COMPLETED, Transaction.created_at >= start_date)
        .group_by(func.date_trunc('day', Transaction.created_at))
        .order_by(func.date_trunc('day', Transaction.created_at))
    )
    revenue_data = [{"date": r.date.isoformat(), "amount": float(r.amount or 0)} for r in revenue_result]

    # New users over time
    users_result = await db.execute(
        select(func.date_trunc('day', User.created_at).label('date'),
               func.count(User.id).label('count'))
        .where(User.created_at >= start_date)
        .group_by(func.date_trunc('day', User.created_at))
        .order_by(func.date_trunc('day', User.created_at))
    )
    users_data = [{"date": r.date.isoformat(), "count": r.count} for r in users_result]

    # New listings over time
    listings_result = await db.execute(
        select(func.date_trunc('day', PartListing.created_at).label('date'),
               func.count(PartListing.id).label('count'))
        .where(PartListing.created_at >= start_date)
        .group_by(func.date_trunc('day', PartListing.created_at))
        .order_by(func.date_trunc('day', PartListing.created_at))
    )
    listings_data = [{"date": r.date.isoformat(), "count": r.count} for r in listings_result]

    # Subscriptions by status
    subs_result = await db.execute(
        select(Subscription.status, func.count(Subscription.id).label('count'))
        .group_by(Subscription.status)
    )
    subscriptions_data = [{"status": r.status.value, "count": r.count} for r in subs_result]

    # Top categories
    cat_result = await db.execute(
        select(Category.name, func.count(PartListing.id).label('count'))
        .join(PartListing, PartListing.category_id == Category.id)
        .group_by(Category.name)
        .order_by(func.count(PartListing.id).desc())
        .limit(10)
    )
    top_categories = [{"category": r.name, "count": r.count} for r in cat_result]

    # Top brands
    brand_result = await db.execute(
        select(PartListing.brand, func.count(PartListing.id).label('count'))
        .group_by(PartListing.brand)
        .order_by(func.count(PartListing.id).desc())
        .limit(10)
    )
    top_brands = [{"brand": r.brand, "count": r.count} for r in brand_result]

    return AnalyticsData(
        revenue=revenue_data,
        users=users_data,
        listings=listings_data,
        subscriptions=subscriptions_data,
        top_categories=top_categories,
        top_brands=top_brands,
    )


# =============================================================================
# MEDIA UPLOAD ENDPOINTS
# =============================================================================

from pydantic import BaseModel, HttpUrl
from typing import List


class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str


class PresignedUrlResponse(BaseModel):
    url: str
    fields: dict
    public_url: str
    key: str


class MediaUploadResponse(BaseModel):
    urls: List[str]


@router.post("/media/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    request: PresignedUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """Get presigned URL for direct browser upload to R2/S3."""
    from app.services.media_storage import get_upload_presigned_url
    
    result = await get_upload_presigned_url(request.filename, request.content_type)
    if not result:
        raise HTTPException(status_code=503, detail="Media storage not configured")
    
    return PresignedUrlResponse(**result)


@router.post("/media/upload", response_model=MediaUploadResponse)
async def upload_media(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload media files directly (fallback for non-browser clients)."""
    from app.services.media_storage import upload_listing_images
    
    # Validate files
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    max_size = 10 * 1024 * 1024  # 10MB
    
    file_objects = []
    filenames = []
    content_types = []
    
    for file in files:
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed")
        
        content = await file.read()
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds 10MB limit")
        
        import io
        file_objects.append(io.BytesIO(content))
        filenames.append(file.filename)
        content_types.append(file.content_type)
    
    urls = await upload_listing_images(file_objects, filenames, content_types)
    
    if not urls:
        raise HTTPException(status_code=503, detail="Media storage not configured or upload failed")
    
    return MediaUploadResponse(urls=urls)


@router.delete("/media/delete")
async def delete_media(
    urls: List[str],
    current_user: User = Depends(get_current_user),
):
    """Delete media files."""
    from app.services.media_storage import delete_listing_images
    
    deleted = await delete_listing_images(urls)
    return {"deleted": deleted}