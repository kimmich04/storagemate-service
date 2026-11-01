"""🖥️ /api/auth — UI gọi để đăng nhập."""

from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

# TODO — endpoint theo plan:
#   POST /api/auth/login   OAuth2 password flow → trả JWT
