"""Phạm vi chung của mọi API dashboard: tenant + kho đang xem + múi giờ."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select

from app.auth.dependencies import CurrentAdmin
from app.database import DbSession
from app.locations import service as locations_service
from app.staff.models import Location, Tenant


@dataclass(frozen=True)
class DashboardScope:
    tenant_id: int
    location: Location
    timezone: str


def get_scope(
    db: DbSession,
    admin: CurrentAdmin,
    location_id: Annotated[int | None, Query(description="Chi nhánh; bỏ trống = kho tổng")] = None,
) -> DashboardScope:
    """Bỏ trống location_id → kho tổng (hoặc kho của admin nếu bị khoá). Chỉ nhận kho chi nhánh."""
    if location_id is None:
        if admin.location_id is not None:
            location = locations_service.get_branch(db, admin.tenant_id, admin.location_id)
        else:
            location = locations_service.get_warehouse(db, admin.tenant_id)
    else:
        if admin.location_id is not None and admin.location_id != location_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền xem kho này")
        location = locations_service.get_branch(db, admin.tenant_id, location_id)
    tz = db.scalars(select(Tenant.timezone).where(Tenant.id == admin.tenant_id)).one()
    return DashboardScope(tenant_id=admin.tenant_id, location=location, timezone=tz)


Scope = Annotated[DashboardScope, Depends(get_scope)]
