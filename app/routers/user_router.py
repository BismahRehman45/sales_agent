from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import OAuth2PasswordBearer, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user, oauth2_scheme
from app.models.user import User
from app.schemas.user_schema import UserUpdate, UserResponse, DeleteResponse
from app.services import user_service
from app.services.user_service import blacklist_access_token

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Security(HTTPBearer(auto_error=False))],
)


@router.get("/me", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fields = update_data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    return await user_service.update_user(db, current_user, fields)


@router.delete("/me", response_model=DeleteResponse)
async def delete_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    await user_service.delete_user(db, current_user)

    if token:
        await blacklist_access_token(db, token, reason="account_deleted")

    return DeleteResponse(message="Account successfully deactivated", deleted=True)
