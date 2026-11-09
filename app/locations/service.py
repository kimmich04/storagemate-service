"""Truy vấn kho. Luôn lọc tenant_id tường minh (user app bypass RLS)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import NotFoundError
from app.locations.models import Location


def list_branches(db: Session, tenant_id: int) -> list[Location]:
    stmt = (
        select(Location)
        .where(Location.tenant_id == tenant_id, Location.kind == "branch", Location.archived_at.is_(None))
        .order_by(Location.id)
    )
    return list(db.scalars(stmt))


def get_branch(db: Session, tenant_id: int, location_id: int) -> Location:
    """Chỉ nhận kho chi nhánh của đúng tenant; kho khác → 404."""
    loc = db.scalars(
        select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
            Location.kind == "branch",
            Location.archived_at.is_(None),
        )
    ).first()
    if loc is None:
        raise NotFoundError("Không tìm thấy chi nhánh")
    return loc


def get_warehouse(db: Session, tenant_id: int) -> Location:
    """Kho tổng của tenant: kho `warehouse` đầu tiên."""
    loc = db.scalars(
        select(Location)
        .where(Location.tenant_id == tenant_id, Location.kind == "warehouse", Location.archived_at.is_(None))
        .order_by(Location.id)
    ).first()
    if loc is None:
        raise NotFoundError("Chưa có kho tổng")
    return loc
