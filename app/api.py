"""🖥️ Gom router của các domain mà dashboard gọi.

main.py mount api_router với prefix="/api", nên:
    prefix "/api" (main.py) + prefix "/stock" (inventory/router.py) = GET /api/stock

Thêm domain mới cho UI: tạo <domain>/router.py rồi include_router ở đây.
"""

from fastapi import APIRouter

from app.auth import router as auth
from app.chat import router as chat
from app.dashboard import router as dashboard
from app.inventory import router as inventory
from app.items import router as items
from app.labels import router as labels
from app.locations import router as locations
from app.reports import router as reports
from app.staff import router as staff

api_router = APIRouter()
api_router.include_router(auth.router)  # /api/auth
api_router.include_router(items.router)  # /api/items
api_router.include_router(staff.router)  # /api/staff
api_router.include_router(inventory.period_router)  # /api/period
api_router.include_router(inventory.stock_router)  # /api/stock
api_router.include_router(inventory.transactions_router)  # /api/transactions
api_router.include_router(labels.router)  # /api/labels
api_router.include_router(reports.router)  # /api/reports
api_router.include_router(chat.router)  # /api/chat
api_router.include_router(locations.router)  # /api/locations
api_router.include_router(dashboard.router)  # /api/dashboard
