"""Tiện ích DB dev, chạy SAU khi nạp seed T10 (seed_t10_2026.sql — dữ liệu Eggyolk, đã có tồn tới 31/10).

  python scripts/dev_db.py --map-codes                       # gán items.code = MÃ VT cho món kho tổng (1 lần)
  python scripts/dev_db.py --invite "Lan" [--role manager]   # tạo nhân viên (chưa gắn Zalo) + mã mời, in mã
  python scripts/dev_db.py --link-staff "Nash" <chat_id>     # đường tắt dev: gắn chat không cần mã mời
  python scripts/dev_db.py --fake-moves [--seed 1]           # cặp NHẬP/XUẤT ảo 01/11 → hôm qua, tồn không đổi
  python scripts/dev_db.py --reset                           # xoá sạch dữ liệu (chỉ DB localhost)

Bản nạp Excel cũ: scripts/_archive/import_opening.py (thay bằng seed).
"""

import argparse
import random
import sys
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Text, cast, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.models import Admin
from app.config import settings
from app.database import SessionLocal, engine
from app.inventory.models import InventoryLog
from app.items.models import Item
from app.staff import service as staff_service
from app.staff.models import InviteCode, Location, Staff

LOCAL_TZ = ZoneInfo(settings.TZ)
# ponytail: seed T10 tạo món kho tổng theo thứ tự sheet nên id 1–123 = MÃ VT (đã kiểm 06/11: 123/123 tên và
# tồn khớp Excel). Seed sinh lại khác thứ tự → phải gán code theo tên thay vì theo id.
SEED_WAREHOUSE_ITEM_IDS = range(1, 124)
IMPORT_ADMIN_EMAIL = "import@storagemate.local"
FAKE_NOTE = "DỮ LIỆU ẢO (dev)"
FAKE_START = date(2026, 11, 1)
FAKE_ITEMS_PER_DAY = 5
FAKE_MAX_QTY = 20
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def warehouse(session: Session) -> Location:
    """Kho tổng = kho kind 'warehouse' đầu tiên (seed: KT_SG)."""
    found = session.scalars(
        select(Location).where(Location.kind == "warehouse").order_by(Location.id)
    ).first()
    if found is None:
        raise SystemExit("Chưa có kho nào — nạp seed trước.")
    return found


def map_codes(session: Session) -> int:
    """Ghi sổ tra món theo items.code (= mã trong catalog.json); seed để trống cột này."""
    result = session.execute(
        update(Item)
        .where(Item.id.in_(SEED_WAREHOUSE_ITEM_IDS), Item.code.is_(None))
        .values(code=cast(Item.id, Text))
    )
    return result.rowcount


def link_staff(session: Session, name: str, chat_id: str) -> Staff:
    """Thay mã mời trong Phase 1: gắn chat Zalo vào nhân viên kho tổng (tạo mới nếu chưa có)."""
    home = warehouse(session)
    staff = session.scalars(select(Staff).where(Staff.zalo_chat_id == chat_id)).first()
    if staff is None:
        staff = Staff(tenant_id=home.tenant_id, default_location_id=home.id, name=name)
        session.add(staff)
    staff.name, staff.zalo_chat_id, staff.linked_at = name, chat_id, datetime.now(LOCAL_TZ)
    session.flush()
    return staff


def invite(session: Session, name: str, role: str, now: datetime) -> tuple[Staff, InviteCode]:
    """Thay màn hình dashboard: thêm nhân viên (hoặc dùng lại hồ sơ cùng tên) rồi cấp mã mời mới."""
    same_name = list(session.scalars(select(Staff).where(func.lower(Staff.name) == name.lower())))
    if len(same_name) > 1:
        raise SystemExit(f"Có {len(same_name)} nhân viên tên «{name}» — đổi tên cho khác nhau trước.")
    staff = same_name[0] if same_name else None
    if staff is None:
        home = warehouse(session)
        staff = Staff(tenant_id=home.tenant_id, default_location_id=home.id, name=name, role=role)
        session.add(staff)
        session.flush()
    return staff, staff_service.create_invite(session, staff, now)


def fake_moves(session: Session, seed: int, end: date) -> int:
    """Cặp NHẬP q (sáng) + XUẤT q (chiều) cùng món mỗi ngày ở kho tổng → tồn cuối ngày không đổi."""
    if session.scalar(select(func.count()).select_from(InventoryLog).where(InventoryLog.note == FAKE_NOTE)):
        raise SystemExit("Đã có dữ liệu ảo — dùng --reset rồi nạp lại seed để làm lại.")
    admin = session.scalars(select(Admin).where(Admin.email == IMPORT_ADMIN_EMAIL)).one()
    home = warehouse(session)
    others = list(session.scalars(select(Location.id).where(Location.id != home.id).order_by(Location.id)))
    stocked = list(
        session.scalars(
            select(Item)
            .join(InventoryLog, InventoryLog.item_id == Item.id)
            .where(InventoryLog.location_id == home.id)
            .group_by(Item.id)
            .having(func.sum(InventoryLog.delta_base) > 0)
            .order_by(Item.id)
        )
    )
    rng = random.Random(seed)
    count = 0
    for day in _days(FAKE_START, end):
        for item in rng.sample(stocked, min(FAKE_ITEMS_PER_DAY, len(stocked))):
            qty = Decimal(rng.randint(1, FAKE_MAX_QTY))
            session.add_all(
                [
                    _fake_row(item, home.id, admin.id, "IN", qty, _at(day, 8, rng), None),
                    _fake_row(item, home.id, admin.id, "OUT", qty, _at(day, 16, rng), rng.choice(others)),
                ]
            )
            count += 2
    session.flush()
    return count


def _at(day: date, hour: int, rng: random.Random) -> datetime:
    return datetime.combine(day, time(hour, rng.randint(0, 59)), tzinfo=LOCAL_TZ)


def _fake_row(
    item: Item,
    location_id: int,
    admin_id: int,
    action: str,
    qty: Decimal,
    at: datetime,
    counterpart: int | None,
) -> InventoryLog:
    return InventoryLog(
        tenant_id=item.tenant_id,
        location_id=location_id,
        item_id=item.id,
        action=action,
        qty=qty,
        unit=item.base_unit,
        qty_base=qty,
        delta_base=qty if action == "IN" else -qty,
        counterpart_location_id=counterpart,
        event_time=at,
        admin_id=admin_id,
        parser_source="manual",
        note=FAKE_NOTE,
    )


def _days(start: date, end: date) -> Iterator[date]:
    """Từ start tới hết hôm qua — giờ ảo của hôm nay có thể ở tương lai."""
    day = start
    while day < end:
        yield day
        day += timedelta(days=1)


def reset() -> None:
    """Xoá sạch dữ liệu (TRUNCATE được, trigger chỉ chặn UPDATE/DELETE). Từ chối nếu DB không ở máy này."""
    host = make_url(settings.DATABASE_URL).host
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"--reset chỉ chạy trên DB localhost (đang trỏ {host}).")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE tenants, inbound_messages RESTART IDENTITY CASCADE"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--map-codes", action="store_true")
    parser.add_argument("--invite", metavar="TÊN")
    parser.add_argument("--role", choices=["staff", "manager"], default="staff")
    parser.add_argument("--link-staff", nargs=2, metavar=("TÊN", "CHAT_ID"))
    parser.add_argument("--fake-moves", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    print(f"DB: {make_url(settings.DATABASE_URL).render_as_string(hide_password=True)}")

    if args.reset:
        reset()
        print("Đã xoá sạch dữ liệu. Nạp lại seed trước khi dùng tiếp.")
    if args.map_codes:
        with SessionLocal.begin() as session:
            print(f"Đã gán code cho {map_codes(session)} món kho tổng.")
    if args.invite:
        with SessionLocal.begin() as session:
            staff, code = invite(session, args.invite, args.role, datetime.now(LOCAL_TZ))
            expires = code.expires_at.astimezone(LOCAL_TZ)
            print(f"Mã mời cho {staff.name}: {code.code} (hết hạn {expires:%d/%m %H:%M})")
    if args.link_staff:
        with SessionLocal.begin() as session:
            staff = link_staff(session, *args.link_staff)
            print(f"Đã gắn chat {staff.zalo_chat_id} cho «{staff.name}».")
    if args.fake_moves:
        with SessionLocal.begin() as session:
            print(f"Đã ghi {fake_moves(session, args.seed, datetime.now(LOCAL_TZ).date())} dòng ảo.")
    if not (args.reset or args.map_codes or args.invite or args.link_staff or args.fake_moves):
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    sys.exit(main(sys.argv[1:]))
