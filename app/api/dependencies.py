import json
import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models import User, UserRole

settings = get_settings()
logger = logging.getLogger(__name__)

# Cache for JWKS keys
_jwks_cache: dict = {}
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_TTL = 3600  # 1 hour


async def fetch_jwks() -> dict:
    """Fetch JWKS from Clerk."""
    global _jwks_cache, _jwks_cache_time
    
    now = datetime.now(timezone.utc)
    if _jwks_cache and _jwks_cache_time and (now - _jwks_cache_time).total_seconds() < JWKS_CACHE_TTL:
        return _jwks_cache
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.CLERK_JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            return _jwks_cache
        raise HTTPException(status_code=503, detail="Authentication service unavailable")


def get_rsa_key(jwks: dict, kid: str) -> Optional[dict]:
    """Find RSA key by key ID."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def verify_clerk_token(token: str) -> Optional[dict]:
    """Verify Clerk JWT token using JWKS."""
    try:
        # Get unverified header to find key ID
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        if not kid:
            return None
        
        # Fetch JWKS
        jwks = await fetch_jwks()
        rsa_key = get_rsa_key(jwks, kid)
        
        if not rsa_key:
            # Try refreshing cache once
            global _jwks_cache_time
            _jwks_cache_time = None
            jwks = await fetch_jwks()
            rsa_key = get_rsa_key(jwks, kid)
            if not rsa_key:
                return None
        
        # Verify token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.CLERK_PUBLISHABLE_KEY,  # Clerk uses publishable key as audience
            options={"verify_aud": True},
        )
        
        return payload
    
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return None


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_telegram_user_id: Optional[str] = Header(None, alias="X-Telegram-User-Id"),
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from Clerk JWT, Telegram header, or initData."""
    user: Optional[User] = None
    
    # Try Telegram header first (for bot)
    if x_telegram_user_id:
        try:
            telegram_id = int(x_telegram_user_id)
            result = await db.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
        except ValueError:
            pass
    
    # Try Telegram initData (for Mini App)
    if not user and x_telegram_init_data:
        # Parse initData to get user info
        import urllib.parse
        params = urllib.parse.parse_qs(x_telegram_init_data)
        user_json = params.get("user", [None])[0]
        if user_json:
            import json
            try:
                tg_user = json.loads(user_json)
                telegram_id = tg_user.get("id")
                if telegram_id:
                    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
                    user = result.scalar_one_or_none()
            except json.JSONDecodeError:
                pass
    
    # Try Clerk JWT (for web app)
    if not user and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = await verify_clerk_token(token)
        
        if payload:
            clerk_user_id = payload.get("sub")  # Clerk uses 'sub' for user ID
            if clerk_user_id:
                result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
                user = result.scalar_one_or_none()
                
                # If user not found but we have a valid Clerk token, they might need to link account
                # This is handled by the web login flow
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user (allows all authenticated users)."""
    return current_user


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin or moderator role."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MODERATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_technician(current_user: User = Depends(get_current_active_user)) -> User:
    """Require technician role (or higher)."""
    if current_user.role == UserRole.TECHNICIAN:
        return current_user
    # Admins and moderators can also access technician endpoints
    return current_user