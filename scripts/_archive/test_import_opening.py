"""scripts/import_opening.py trên workbook nhỏ dựng trong test (không dùng file Excel thật)."""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import openpyxl
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.inventory.models import InventoryLog
from app.items.models import Item

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_opening.py"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("import_opening", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    """Giống bố cục sheet T10: tiêu đề, hàng header, rồi nhóm + mặt hàng; cột I = Tồn cuối 31.10."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append([" ", None, "THEO DÕI TỒN KHO TỔNG SG T10.2026"])
    sheet.append(["MÃ VT", "Tên", "Đơn vị", "Tồn cuối 30.09", "Nhập", "", "", "", "Tồn cuối  31.10"])
    sheet.append([None, "MERCHANDISE"])
    sheet.append([1, "Hộp cà phê trứng sấy thăng hoa", "Hộp", 0, 0, 0, 0, 0, 696])
    sheet.append([4, "Ly Espresso", "Cái", 0, 0, 0, 0, 0, 0])
    sheet.append([None, "HÀNG SẢN XUẤT"])
    sheet.append([2, "Hộp cà phê kem béo sấy thăng hoa", "Hộp", 0, 0, 0, 0, 0, 484])
    sheet.append([99999, "Món lạ", "Cái", 0, 0, 0, 0, 0, 5])
    path = tmp_path / "t10.xlsx"
    book.save(path)
    return path


def _stock(db: Session, code: str) -> Decimal:
    item = db.scalars(select(Item).where(Item.code == code)).one()
    return db.scalar(
        select(func.coalesce(func.sum(InventoryLog.delta_base), 0)).where(InventoryLog.item_id == item.id)
    )


def test_opening_stock_matches_closing_column(
    script: ModuleType, workbook: Path, db_session: Session
) -> None:
    warnings = script.import_all(db_session, script.read_opening(workbook))

    assert _stock(db_session, "1") == Decimal("696")
    assert _stock(db_session, "2") == Decimal("484")
    assert _stock(db_session, "4") == 0  # tồn 0 → không có dòng
    assert warnings == ["Mã 99999 «Món lạ» không có trong catalog — bỏ qua"]


def test_item_category_from_nearest_group_header_above(
    script: ModuleType, workbook: Path, db_session: Session
) -> None:
    script.import_all(db_session, script.read_opening(workbook))

    query = select(Item.code, Item.category).where(Item.code.in_(["1", "4", "2"]))
    categories = dict(db_session.execute(query).tuples().all())
    assert categories == {"1": "MERCHANDISE", "4": "MERCHANDISE", "2": "HÀNG SẢN XUẤT"}


def test_second_import_is_refused(script: ModuleType, workbook: Path, db_session: Session) -> None:
    rows = script.read_opening(workbook)
    script.import_all(db_session, rows)

    with pytest.raises(SystemExit):
        script.import_all(db_session, rows)


def test_link_staff_creates_staff_at_warehouse(
    script: ModuleType, workbook: Path, db_session: Session
) -> None:
    script.import_all(db_session, script.read_opening(workbook))

    staff = script.link_staff(db_session, "Nash", "chat-9")

    assert (staff.name, staff.zalo_chat_id) == ("Nash", "chat-9")
    assert script.link_staff(db_session, "Nash 2", "chat-9").id == staff.id


def test_fake_moves_leave_current_stock_unchanged(
    script: ModuleType, workbook: Path, db_session: Session
) -> None:
    script.import_all(db_session, script.read_opening(workbook))

    written = script.fake_moves(db_session, seed=1, end=date(2026, 11, 6))

    assert written == 5 * 2 * 2  # 5 ngày × 2 món có tồn × (IN + OUT)
    assert _stock(db_session, "1") == Decimal("696")
    assert _stock(db_session, "2") == Decimal("484")


def test_fake_moves_same_seed_same_rows(script: ModuleType, workbook: Path, db_session: Session) -> None:
    script.import_all(db_session, script.read_opening(workbook))
    script.fake_moves(db_session, seed=7, end=date(2026, 11, 3))
    first = list(db_session.execute(select(InventoryLog.item_id, InventoryLog.qty, InventoryLog.event_time)))
    db_session.rollback()
    script.import_all(db_session, script.read_opening(workbook))
    script.fake_moves(db_session, seed=7, end=date(2026, 11, 3))
    second = list(db_session.execute(select(InventoryLog.item_id, InventoryLog.qty, InventoryLog.event_time)))

    assert [(q, t) for _, q, t in first] == [(q, t) for _, q, t in second]
