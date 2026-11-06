"""ledger.record(): ghi từng dòng phiếu regex vào inventory_log của kho tổng (DB thật, rollback mỗi test)."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.inventory import ledger
from app.inventory.models import InventoryLog
from app.parser.regex import parse_phieu

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
SENT_AT = NOW - timedelta(minutes=5)


def _record(db: Session, seeded: SimpleNamespace, text: str, now: datetime = NOW) -> ledger.LedgerResult:
    phieu = parse_phieu(text, SENT_AT)
    assert phieu is not None
    return ledger.record(
        db, phieu, staff=seeded.staff, inbound_id=None, raw_message=text, sent_at=SENT_AT, now=now
    )


def _rows(db: Session) -> list[InventoryLog]:
    return list(db.scalars(select(InventoryLog).order_by(InventoryLog.id)))


def _give_stock(db: Session, seeded: SimpleNamespace, code: str, qty: int) -> None:
    item = seeded.items[code]
    db.add(
        InventoryLog(
            tenant_id=seeded.tenant.id,
            location_id=seeded.staff.default_location_id,
            item_id=item.id,
            action="ADJUST",
            qty=qty,
            unit=item.base_unit,
            qty_base=qty,
            delta_base=qty,
            event_time=NOW - timedelta(days=5),
            admin_id=seeded.admin.id,
            parser_source="opening",
        )
    )
    db.flush()


def test_in_phieu_writes_one_row_per_line_in_base_unit(db_session: Session, seeded: SimpleNamespace) -> None:
    result = _record(
        db_session,
        seeded,
        "ngày 05/11 nhập hàng về kho tổng\nHộp cà phê trứng sấy thăng hoa: 2 thùng\nCà phê kem béo: 10",
    )

    rows = _rows(db_session)
    assert (result.written, result.total, result.route) == (2, 2, "phieu")
    assert [(r.action, r.qty, r.unit, r.qty_base, r.delta_base) for r in rows] == [
        ("IN", Decimal("2"), "thùng", Decimal("48"), Decimal("48")),
        ("IN", Decimal("10"), "Hộp", Decimal("10"), Decimal("10")),
    ]
    assert {r.parser_source for r in rows} == {"regex"}
    assert {r.location_id for r in rows} == {seeded.locations["KT"].id}
    assert rows[0].event_time == datetime(2026, 11, 5, 14, 55, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_unknown_item_line_skipped_others_written(db_session: Session, seeded: SimpleNamespace) -> None:
    result = _record(
        db_session,
        seeded,
        "ngày 05/11 nhập hàng về kho tổng\nCà phê kem béo: 10\nxyz abc khong co: 3\nlinh tinh",
    )

    assert (result.written, result.total, result.route) == (1, 3, "phieu_partial")
    assert [(s.raw, s.reason) for s in result.skipped] == [
        ("linh tinh", ledger.REASON_BAD_LINE),
        ("xyz abc khong co: 3", ledger.REASON_UNKNOWN),
    ]
    assert len(_rows(db_session)) == 1


def test_out_more_than_stock_skips_only_that_line(db_session: Session, seeded: SimpleNamespace) -> None:
    _give_stock(db_session, seeded, "1", 5)
    _give_stock(db_session, seeded, "2", 50)

    result = _record(
        db_session,
        seeded,
        "ngày 05/11 xuất từ kho tổng sang kho 220\nHộp cà phê trứng sấy thăng hoa: 6\nCà phê kem béo: 10",
    )

    assert (result.written, result.route) == (1, "phieu_partial")
    assert "chỉ còn 5 hộp, không thể xuất 6 hộp" in result.skipped[0].reason
    out = [r for r in _rows(db_session) if r.action == "OUT"]
    assert [(r.item_id, r.delta_base, r.counterpart_location_id) for r in out] == [
        (seeded.items["2"].id, Decimal("-10"), seeded.locations["K220"].id)
    ]


def test_two_out_lines_same_item_checked_cumulatively(db_session: Session, seeded: SimpleNamespace) -> None:
    _give_stock(db_session, seeded, "2", 10)

    result = _record(
        db_session, seeded, "ngày 05/11 xuất từ kho tổng sang PQ\nCà phê kem béo: 6\nCà phê kem béo: 5"
    )

    assert result.written == 1
    assert "chỉ còn 4 hộp" in result.skipped[0].reason


def test_bundle_line_writes_components(db_session: Session, seeded: SimpleNamespace) -> None:
    result = _record(db_session, seeded, "ngày 05/11 nhập hàng về kho tổng\nLy Espresso: 2 bộ")

    assert result.written == 1
    rows = _rows(db_session)
    assert sorted((r.item_id, r.qty_base) for r in rows) == sorted(
        [(seeded.items["4"].id, Decimal("2")), (seeded.items["5"].id, Decimal("2"))]
    )


def test_bundle_with_one_component_short_is_skipped_whole(
    db_session: Session, seeded: SimpleNamespace
) -> None:
    _give_stock(db_session, seeded, "4", 10)
    _give_stock(db_session, seeded, "5", 1)

    result = _record(db_session, seeded, "ngày 05/11 xuất từ kho tổng sang kho 220\nLy Espresso: 2 bộ")

    assert result.written == 0
    assert not [r for r in _rows(db_session) if r.action == "OUT"]


def test_unmatched_counterpart_written_with_null(db_session: Session, seeded: SimpleNamespace) -> None:
    _give_stock(db_session, seeded, "2", 10)

    _record(db_session, seeded, "ngày 05/11 xuất từ kho tổng sang quán bà Tư\nCà phê kem béo: 1")

    out = [r for r in _rows(db_session) if r.action == "OUT"]
    assert out[0].counterpart_location_id is None


def test_event_time_older_than_7_days_writes_nothing(db_session: Session, seeded: SimpleNamespace) -> None:
    result = _record(db_session, seeded, "ngày 20/10 nhập hàng về kho tổng\nCà phê kem béo: 10")

    assert result.written == 0
    assert result.date_error == "ngày 20/10 đã quá 7 ngày"
    assert _rows(db_session) == []


def test_counterpart_matches_accented_alias(db_session: Session, seeded: SimpleNamespace) -> None:
    _give_stock(db_session, seeded, "2", 10)

    _record(db_session, seeded, "ngày 05/11 xuất từ kho tổng sang nội bộ\nCà phê kem béo: 1")

    out = [r for r in _rows(db_session) if r.action == "OUT"]
    assert out[0].counterpart_location_id == seeded.locations["DT"].id
