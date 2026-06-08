from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_blacklist import TokenBlacklist


async def blacklist_token(db: AsyncSession, entry: TokenBlacklist) -> TokenBlacklist:
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def is_token_blacklisted(db: AsyncSession, jti: str) -> bool:
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.token_jti == jti)
    )
    return result.scalar_one_or_none() is not None
