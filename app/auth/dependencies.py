"""🖥️ get_current_user: đọc JWT từ header Authorization của UI, gắn vào router cần đăng nhập."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.auth.models import Admin
from app.config import settings
from app.database import DbSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user() -> None:
    """TODO Pha 4: nhận token = Depends(oauth2_scheme), giải mã JWT, trả admin hiện tại."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Auth chưa được hiện thực")


def get_dev_admin(db: DbSession) -> Admin:
    """Admin tạm cho demo dashboard: admin đầu tiên. Chỉ chạy khi DEV_AUTH_ENABLED=true."""
    if not settings.DEV_AUTH_ENABLED:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Auth chưa được hiện thực")
    admin = db.scalars(select(Admin).order_by(Admin.id).limit(1)).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa có admin nào")
    return admin


# Khi có auth thật chỉ cần đổi get_dev_admin → get_current_user ở đây.
CurrentAdmin = Annotated[Admin, Depends(get_dev_admin)]
