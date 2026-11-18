import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    TECHNICIAN = "technician"
    ADMIN = "admin"
    MODERATOR = "moderator"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    PENDING_APPROVAL = "pending_approval"


class PaymentType(str, enum.Enum):
    REGISTRATION = "registration"
    MONTHLY_SUBSCRIPTION = "monthly_subscription"
    BUNDLE_INITIAL = "bundle_initial"


class PaymentMethod(str, enum.Enum):
    CHAPA = "chapa"
    TELEBIRR = "telebirr"
    CBE_BIRR = "cbe_birr"
    MANUAL_RECEIPT = "manual_receipt"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PartCondition(str, enum.Enum):
    ORIGINAL_PULLED = "original_pulled"
    OEM_NEW = "oem_new"
    AFTERMARKET = "aftermarket"
    FOR_PARTS_ONLY = "for_parts_only"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clerk_user_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    shop_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shop_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True),
        default=UserRole.TECHNICIAN,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subscription: Mapped["Subscription"] = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user", foreign_keys="Transaction.user_id", cascade="all, delete-orphan"
    )
    listings: Mapped[list["PartListing"]] = relationship(
        "PartListing", back_populates="seller", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_users_telegram_id", "telegram_id"),
        Index("idx_users_clerk_id", "clerk_user_id"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    registration_fee_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True),
        default=SubscriptionStatus.PENDING_APPROVAL,
        nullable=False,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monthly_rate: Mapped[float] = mapped_column(default=0.00, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="subscription")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[float] = mapped_column(nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, name="payment_type_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True), nullable=False
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True), nullable=False
    )
    transaction_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    receipt_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True),
        default=TransactionStatus.PENDING,
        nullable=False,
    )
    verified_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="transactions", foreign_keys=[user_id])
    verifier: Mapped["User | None"] = relationship("User", foreign_keys=[verified_by])


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    listings: Mapped[list["PartListing"]] = relationship("PartListing", back_populates="category")


class PartListing(Base):
    __tablename__ = "part_listings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    seller_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    brand: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    part_name: Mapped[str] = mapped_column(String(100), nullable=False)
    condition: Mapped[PartCondition] = mapped_column(
        Enum(PartCondition, name="part_condition_enum", values_callable=lambda x: [e.value for e in x], create_constraint=True), nullable=False
    )
    price: Mapped[float] = mapped_column(nullable=False)
    is_negotiable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    seller: Mapped["User"] = relationship("User", back_populates="listings")
    category: Mapped["Category"] = relationship("Category", back_populates="listings")

    __table_args__ = (
        Index("idx_listings_search", "brand", "model_name", "category_id", "is_available"),
        CheckConstraint("price >= 0", name="check_price_positive"),
    )