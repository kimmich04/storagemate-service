"""🖥️ /api/locations — bộ chọn kho của dashboard (chỉ chi nhánh; bỏ chọn = kho tổng)."""

from fastapi import APIRouter

from app.auth.dependencies import CurrentAdmin
from app.database import DbSession
from app.locations import service
from app.locations.schemas import LocationRead

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
def list_locations(db: DbSession, admin: CurrentAdmin) -> list[LocationRead]:
    branches = service.list_branches(db, admin.tenant_id)
    if admin.location_id is not None:  # admin bị khoá kho chỉ thấy kho của mình
        branches = [b for b in branches if b.id == admin.location_id]
    return [LocationRead.model_validate(b) for b in branches]
