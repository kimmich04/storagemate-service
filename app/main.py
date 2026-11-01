"""Điểm vào FastAPI: tạo app, gắn CORS, mount router.

🖥️ UI (dashboard) đi vào qua api_router, prefix /api  → xem app/api.py
⚡ /webhooks/zalo do Zalo gọi (không phải UI)           → xem app/channels/router.py
⚙️ /health do Docker/CI gọi

Chạy dev:  fastapi dev     (entrypoint khai báo trong pyproject.toml)
Docs:      http://127.0.0.1:8000/docs
OpenAPI:   http://127.0.0.1:8000/api/openapi.json  ← repo web sinh client TypeScript từ đây
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api import api_router
from app.channels import router as channels
from app.config import settings
from app.exceptions import register_exception_handlers


def custom_generate_unique_id(route: APIRoute) -> str:
    """Đặt operationId dạng '<tag>-<tên hàm>' để client TypeScript sinh ra có tên gọn."""
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


app = FastAPI(
    title="Storagemate Service",
    openapi_url="/api/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# 🖥️ (1) CORS: chỉ cho phép domain của dashboard (CORS_ORIGINS trong .env) gọi vào
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# 🖥️ (2) Toàn bộ API cho dashboard: /api/...
app.include_router(api_router, prefix="/api")

# ⚡ Webhook Zalo: /webhooks/zalo (không có prefix /api)
app.include_router(channels.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """⚙️ Docker/CI gọi. TODO Pha 1: kiểm tra DB, hàng đợi, Zalo getMe."""
    return {"status": "ok"}
