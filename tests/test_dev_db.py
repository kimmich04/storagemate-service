"""scripts/dev_db.py: gán code cho món seed, gắn nhân viên, dữ liệu ảo không đổi tồn."""

import importlib.util
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.inventory.models import InventoryLog
from app.items.models import Item

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev_db.py"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dev_db", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stock(db: Session, item: Item, location_id: int) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(InventoryLog.delta_base), 0)).where(
            InventoryLog.item_id == item.id, InventoryLog.location_id == location_id
        )
    )


def _opening(db: Session, seeded: SimpleNamespace, item: Item, qty: int) -> None:
    db.add(
        InventoryLog(
            tenant_id=seeded.tenant.id,
            location_id=seeded.locations["KT"].id,
            item_id=item.id,
            action="ADJUST",
            qty=qty,
            unit=item.base_unit,
            qty_base=qty,
            delta_base=qty,
            event_time=datetime(2026, 9, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
            admin_id=seeded.admin.id,
            parser_source="opening",
        )
    )
    db.flush()


def test_map_codes_fills_only_seed_warehouse_ids(
    script: ModuleType, db_session: Session, seeded: SimpleNamespace
) -> None:
    db_session.execute(update(Item).values(code=None))

    script.map_codes(db_session)

    codes = dict(db_session.execute(select(Item.id, Item.code)).tuples().all())
    assert codes == {item_id: (str(item_id) if item_id <= 123 else None) for item_id in codes}


def test_link_staff_creates_then_reuses_staff_at_warehouse(
    script: ModuleType, db_session: Session, seeded: SimpleNamespace
) -> None:
    staff = script.link_staff(db_session, "Nash", "chat-9")

    assert (staff.default_location_id, staff.zalo_chat_id) == (seeded.locations["KT"].id, "chat-9")
    assert script.link_staff(db_session, "Nash 2", "chat-9").id == staff.id


def test_fake_moves_leave_warehouse_stock_unchanged(
    script: ModuleType, db_session: Session, seeded: SimpleNamespace
) -> None:
    seeded.admin.email = script.IMPORT_ADMIN_EMAIL
    first, second = seeded.items["1"], seeded.items["2"]
    _opening(db_session, seeded, first, 696)
    _opening(db_session, seeded, second, 484)

    written = script.fake_moves(db_session, seed=1, end=date(2026, 11, 6))

    assert written == 5 * 2 * 2  # 5 ngày × 2 món có tồn × (NHẬP + XUẤT)
    kt = seeded.locations["KT"].id
    assert (_stock(db_session, first, kt), _stock(db_session, second, kt)) == (Decimal("696"), Decimal("484"))


def test_invite_creates_unlinked_staff_and_valid_code(
    script: ModuleType, db_session: Session, seeded: SimpleNamespace
) -> None:
    now = datetime(2026, 11, 6, 21, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    staff, code = script.invite(db_session, "Hoa", "manager", now)

    assert (staff.role, staff.zalo_chat_id, staff.default_location_id) == (
        "manager",
        None,
        seeded.locations["KT"].id,
    )
    assert code.expires_at == now + timedelta(hours=24)


def test_invite_same_name_reuses_staff_and_revokes_old_code(
    script: ModuleType, db_session: Session, seeded: SimpleNamespace
) -> None:
    now = datetime(2026, 11, 6, 21, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    staff, first = script.invite(db_session, "Hoa", "staff", now)

    again, second = script.invite(db_session, "hoa", "staff", now)

    assert again.id == staff.id
    assert first.revoked_at == now and second.revoked_at is None
