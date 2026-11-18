import asyncio
import os
import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base
from app.main import app
from app.models import User, UserRole, Subscription, SubscriptionStatus, Category, PartListing, PartCondition
from app.core.config import Settings


# Test database URL - use SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with overridden database."""
    from app.db.session import get_db
    
    app.dependency_overrides[get_db] = lambda: db_session
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        telegram_id=123456789,
        telegram_username="testuser",
        full_name="Test User",
        phone_number="+251911223344",
        shop_name="Test Shop",
        shop_location="Bole, Addis Ababa",
        role=UserRole.TECHNICIAN,
        is_verified=True,
    )
    db_session.add(user)
    
    subscription = Subscription(
        user_id=user.id,
        registration_fee_paid=True,
        status=SubscriptionStatus.ACTIVE,
        monthly_rate=100.00,
    )
    db_session.add(subscription)
    
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user."""
    user = User(
        telegram_id=987654321,
        telegram_username="admin",
        full_name="Admin User",
        phone_number="+251911223345",
        role=UserRole.ADMIN,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_category(db_session: AsyncSession) -> Category:
    """Create a test category."""
    category = Category(name="Screens")
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest.fixture
async def test_listing(db_session: AsyncSession, test_user: User, test_category: Category) -> PartListing:
    """Create a test listing."""
    listing = PartListing(
        seller_id=test_user.id,
        category_id=test_category.id,
        brand="Samsung",
        model_name="Galaxy S22 Ultra",
        part_name="Original OLED Screen",
        condition=PartCondition.ORIGINAL_PULLED,
        price=15000.00,
        is_negotiable=True,
        description="Original pulled screen, no scratches",
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing


# Override settings for testing
@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Override settings for testing."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://test.com/webhook/tg")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEBUG", "true")
    
    # Re-import settings to pick up new values
    from app.core.config import get_settings
    get_settings.cache_clear()