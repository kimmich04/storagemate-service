"""🖥️ get_current_user: đọc JWT từ header Authorization của UI, gắn vào router cần đăng nhập."""

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user() -> None:
    """TODO Pha 4: nhận token = Depends(oauth2_scheme), giải mã JWT, trả admin hiện tại."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Auth chưa được hiện thực")
