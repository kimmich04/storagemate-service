"""Phạm vi chung của các API kho tổng: tenant + kho tổng + múi giờ (dùng cho Tồn Kho, Nhập/Xuất Kho)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.auth.dependencies import CurrentAdmin
from app.database import DbSession
from app.locations import service as locations_service
from app.staff.models import Location, Tenant


@dataclass(frozen=True)
class WarehouseScope:
    tenant_id: int
    location: Location  # kho tổng
    timezone: str


def get_warehouse_scope(db: DbSession, admin: CurrentAdmin) -> WarehouseScope:
    """Luôn là kho tổng của tenant, không có tham số location_id.

    Phân quyền (admin bị khoá chi nhánh) tạm thời bỏ qua theo yêu cầu: chỉ làm core trang.
    """
    location = locations_service.get_warehouse(db, admin.tenant_id)
    tz = db.scalars(select(Tenant.timezone).where(Tenant.id == admin.tenant_id)).one()
    return WarehouseScope(tenant_id=admin.tenant_id, location=location, timezone=tz)


Scope = Annotated[WarehouseScope, Depends(get_warehouse_scope)]
