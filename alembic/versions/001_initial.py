"""Initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2026-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing objects for idempotency (dev databases)
    for table in [
        "part_listings", "categories", "transactions", "subscriptions", "users",
    ]:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    for enum_name in [
        "part_condition_enum", "transaction_status_enum", "payment_method_enum",
        "payment_type_enum", "subscription_status_enum", "user_role_enum",
    ]:
        op.execute(f'DROP TYPE IF EXISTS "{enum_name}"')

    # Create enum types
    user_role_enum = postgresql.ENUM(
        "technician", "admin", "moderator", name="user_role_enum", create_type=False
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    subscription_status_enum = postgresql.ENUM(
        "active", "past_due", "canceled", "pending_approval", name="subscription_status_enum", create_type=False
    )
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    payment_type_enum = postgresql.ENUM(
        "registration", "monthly_subscription", "bundle_initial", name="payment_type_enum", create_type=False
    )
    payment_type_enum.create(op.get_bind(), checkfirst=True)

    payment_method_enum = postgresql.ENUM(
        "chapa", "telebirr", "cbe_birr", "manual_receipt", name="payment_method_enum", create_type=False
    )
    payment_method_enum.create(op.get_bind(), checkfirst=True)

    transaction_status_enum = postgresql.ENUM(
        "pending", "completed", "failed", name="transaction_status_enum", create_type=False
    )
    transaction_status_enum.create(op.get_bind(), checkfirst=True)

    part_condition_enum = postgresql.ENUM(
        "original_pulled", "oem_new", "aftermarket", "for_parts_only", name="part_condition_enum", create_type=False
    )
    part_condition_enum.create(op.get_bind(), checkfirst=True)

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=100), nullable=True),
        sa.Column("clerk_user_id", sa.String(length=120), nullable=True),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("shop_name", sa.String(length=120), nullable=True),
        sa.Column("shop_location", sa.String(length=255), nullable=True),
        sa.Column("role", user_role_enum, nullable=False, server_default="technician"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("clerk_user_id"),
        sa.UniqueConstraint("phone_number"),
    )
    op.create_index("idx_users_telegram_id", "users", ["telegram_id"], unique=False)
    op.create_index("idx_users_clerk_id", "users", ["clerk_user_id"], unique=False)

    # Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("registration_fee_paid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", subscription_status_enum, nullable=False, server_default="pending_approval"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_rate", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # Create transactions table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("payment_type", payment_type_enum, nullable=False),
        sa.Column("payment_method", payment_method_enum, nullable=False),
        sa.Column("transaction_reference", sa.String(length=100), nullable=False),
        sa.Column("receipt_image_url", sa.Text(), nullable=True),
        sa.Column("status", transaction_status_enum, nullable=False, server_default="pending"),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_reference"),
    )

    # Create categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create part_listings table
    op.create_table(
        "part_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("part_name", sa.String(length=100), nullable=False),
        sa.Column("condition", part_condition_enum, nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_negotiable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("telegram_file_ids", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("image_urls", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("price >= 0", name="check_price_positive"),
    )
    op.create_index("idx_listings_search", "part_listings", ["brand", "model_name", "category_id", "is_available"], unique=False)

    # Insert default categories
    op.bulk_insert(
        sa.table("categories", sa.column("name", sa.String)),
        [
            {"name": "Screens"},
            {"name": "Motherboards"},
            {"name": "Batteries"},
            {"name": "Cameras"},
            {"name": "IC Chips"},
            {"name": "Flex Cables"},
            {"name": "Tools"},
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_listings_search", table_name="part_listings")
    op.drop_table("part_listings")
    op.drop_table("categories")
    op.drop_table("transactions")
    op.drop_table("subscriptions")
    op.drop_index("idx_users_clerk_id", table_name="users")
    op.drop_index("idx_users_telegram_id", table_name="users")
    op.drop_table("users")

    # Drop enum types
    for enum_name in [
        "part_condition_enum",
        "transaction_status_enum",
        "payment_method_enum",
        "payment_type_enum",
        "subscription_status_enum",
        "user_role_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")