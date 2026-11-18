from datetime import datetime
from enum import Enum
from typing import Optional, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar('T')


class UserRole(str, Enum):
    TECHNICIAN = "technician"
    ADMIN = "admin"
    MODERATOR = "moderator"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    PENDING_APPROVAL = "pending_approval"


class PaymentType(str, Enum):
    REGISTRATION = "registration"
    MONTHLY_SUBSCRIPTION = "monthly_subscription"
    BUNDLE_INITIAL = "bundle_initial"


class PaymentMethod(str, Enum):
    CHAPA = "chapa"
    TELEBIRR = "telebirr"
    CBE_BIRR = "cbe_birr"
    MANUAL_RECEIPT = "manual_receipt"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PartCondition(str, Enum):
    ORIGINAL_PULLED = "original_pulled"
    OEM_NEW = "oem_new"
    AFTERMARKET = "aftermarket"
    FOR_PARTS_ONLY = "for_parts_only"


class UserBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=1, max_length=20)
    shop_name: Optional[str] = Field(None, max_length=120)
    shop_location: Optional[str] = Field(None, max_length=255)


class UserCreate(UserBase):
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = Field(None, max_length=100)
    clerk_user_id: Optional[str] = Field(None, max_length=120)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    shop_name: Optional[str] = Field(None, max_length=120)
    shop_location: Optional[str] = Field(None, max_length=255)
    is_verified: Optional[bool] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    clerk_user_id: Optional[str] = None
    role: UserRole
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class SubscriptionBase(BaseModel):
    registration_fee_paid: bool = False
    monthly_rate: float = Field(default=0.00, ge=0)


class SubscriptionCreate(SubscriptionBase):
    user_id: UUID


class SubscriptionUpdate(BaseModel):
    registration_fee_paid: Optional[bool] = None
    status: Optional[SubscriptionStatus] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    monthly_rate: Optional[float] = Field(None, ge=0)


class SubscriptionResponse(SubscriptionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    status: SubscriptionStatus
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    created_at: datetime


class TransactionBase(BaseModel):
    amount: float = Field(..., gt=0)
    payment_type: PaymentType
    payment_method: PaymentMethod
    transaction_reference: str = Field(..., min_length=1, max_length=100)


class TransactionCreate(TransactionBase):
    user_id: UUID
    receipt_image_url: Optional[str] = None


class TransactionUpdate(BaseModel):
    status: Optional[TransactionStatus] = None
    receipt_image_url: Optional[str] = None
    verified_by: Optional[UUID] = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    status: TransactionStatus
    receipt_image_url: Optional[str] = None
    verified_by: Optional[UUID] = None
    created_at: datetime


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PartListingBase(BaseModel):
    category_id: int
    brand: str = Field(..., min_length=1, max_length=50)
    model_name: str = Field(..., min_length=1, max_length=100)
    part_name: str = Field(..., min_length=1, max_length=100)
    condition: PartCondition
    price: float = Field(..., ge=0)
    is_negotiable: bool = True
    description: Optional[str] = None
    telegram_file_ids: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)


class PartListingCreate(PartListingBase):
    pass


class PartListingUpdate(BaseModel):
    category_id: Optional[int] = None
    brand: Optional[str] = Field(None, min_length=1, max_length=50)
    model_name: Optional[str] = Field(None, min_length=1, max_length=100)
    part_name: Optional[str] = Field(None, min_length=1, max_length=100)
    condition: Optional[PartCondition] = None
    price: Optional[float] = Field(None, ge=0)
    is_negotiable: Optional[bool] = None
    description: Optional[str] = None
    telegram_file_ids: Optional[list[str]] = None
    image_urls: Optional[list[str]] = None
    is_available: Optional[bool] = None


class PartListingResponse(PartListingBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    is_available: bool
    created_at: datetime


class PartListingSearchParams(BaseModel):
    category_id: Optional[int] = None
    brand: Optional[str] = None
    model_name: Optional[str] = None
    condition: Optional[PartCondition] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    is_available: Optional[bool] = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# Admin schemas
class UserWithSubscriptionResponse(UserResponse):
    subscription: Optional[SubscriptionResponse] = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_subscriptions: int
    pending_payments: int
    total_listings: int
    revenue_this_month: float
    new_users_this_month: int


class AdminUserSearchParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: Optional[str] = None
    role: Optional[UserRole] = None


class AdminTransactionSearchParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Optional[TransactionStatus] = None


class UserRoleUpdate(BaseModel):
    role: UserRole


class BulkUploadResult(BaseModel):
    success: int
    failed: int
    errors: list[dict]


class AnalyticsPeriod(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class AnalyticsParams(BaseModel):
    period: AnalyticsPeriod = AnalyticsPeriod.MONTH


class AnalyticsData(BaseModel):
    revenue: list[dict]
    users: list[dict]
    listings: list[dict]
    subscriptions: list[dict]
    top_categories: list[dict]
    top_brands: list[dict]