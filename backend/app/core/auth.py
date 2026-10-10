import os
import uuid
from typing import Optional
import httpx
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

async def verify_supabase_token(token: str) -> Optional[dict]:
    """
    Validates a Supabase JWT by querying Supabase Auth /user endpoint.
    Returns the user dict if valid, or None.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_ANON_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"Token verification exception: {e}")
    return None


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency:
    If Bearer token is valid, returns the corresponding User database instance.
    If no token or invalid token, returns None.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.split("Bearer ")[1].strip()
    user_data = await verify_supabase_token(token)
    if not user_data or "id" not in user_data:
        return None

    try:
        user_uuid = uuid.UUID(user_data["id"])
    except ValueError:
        return None

    # Fetch or create in public.users table
    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        email = user_data.get("email", f"user_{str(user_uuid)[:8]}@gym.app")
        user = User(id=user_uuid, email=email)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """
    Strict authentication dependency:
    Raises HTTP 401 Unauthorized if user is not authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
