"""Tool Q&A trên DB test, chạy bằng vai qa_reader: quyền chỉ đọc, cách ly tenant, kết quả từng tool."""

import json
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.inventory.models import InventoryLog
from app.items.models import Item
from app.parser.normalize import fold
from app.qa.tools import ToolScope, read_only_session, run_tool
from app.staff.models import Location, Tenant

VN = ZoneInfo("Asia/Ho_Chi_Minh")
TODAY = date(2026, 11, 5)


def _log(
    db: Session,
    seeded: SimpleNamespace,
    item: Item,
    action: str,
    qty: int,
    when: datetime,
    location: str = "KT",
    counterpart: str | None = None,
) -> None:
    sign = 1 if action == "IN" else -1
    db.add(
        InventoryLog(
            tenant_id=seeded.tenant.id,
            location_id=seeded.locations[location].id,
            item_id=item.id,
            action=action,
            qty=Decimal(qty),
            unit=item.base_unit,
            qty_base=Decimal(qty),
            delta_base=Decimal(sign * qty),
            counterpart_location_id=seeded.locations[counterpart].id if counterpart else None,
            event_time=when,
            staff_id=seeded.staff.id,
            parser_source="regex",
        )
    )
    db.flush()


def _item(seeded: SimpleNamespace, code: str = "1") -> Item:
    return seeded.items[code]


@pytest.fixture
def scope(qa_session_factory: Callable[[], Session], seeded: SimpleNamespace) -> ToolScope:
    return ToolScope(tenant_id=seeded.tenant.id, today=TODAY, session_factory=qa_session_factory)


def _call(scope: ToolScope, tool: str, **args: object) -> dict:
    return json.loads(run_tool(tool, args, scope))


@pytest.mark.parametrize("table", ["staff", "admins", "inbound_messages", "inventory_log", "items"])
def test_qa_reader_cannot_read_base_tables(scope: ToolScope, table: str) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        with read_only_session(scope.session_factory, scope.tenant_id) as session:
            session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))


def test_qa_reader_cannot_write_ledger(scope: ToolScope, seeded: SimpleNamespace) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        with read_only_session(scope.session_factory, scope.tenant_id) as session:
            session.execute(text("INSERT INTO inventory_log DEFAULT VALUES"))


def test_views_return_nothing_without_tenant_setting(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    with qa_session_factory() as session:
        session.begin()
        count = session.execute(text("SELECT count(*) FROM qa_items")).scalar_one()
        session.rollback()

    assert count == 0


def test_role_is_restored_after_a_tool_call(scope: ToolScope, db_session: Session) -> None:
    _call(scope, "FindItems", name="ca phe")

    assert db_session.execute(text("SELECT count(*) FROM inbound_messages")).scalar_one() == 0


def test_get_stock_sums_ledger_rows_per_location(
    scope: ToolScope, db_session: Session, seeded: SimpleNamespace
) -> None:
    item = _item(seeded)
    _log(db_session, seeded, item, "IN", 10, datetime(2026, 11, 3, 9, 0, tzinfo=VN))
    _log(db_session, seeded, item, "OUT", 3, datetime(2026, 11, 4, 9, 0, tzinfo=VN), counterpart="K220")

    result = _call(scope, "GetStock", item_ids=[item.id])

    [row] = result["rows"]
    assert (row["location_code"], row["qty_base"]) == ("KT", "7")
    assert result["item_ids_without_rows"] == []


def test_other_tenant_rows_are_invisible(
    scope: ToolScope, db_session: Session, seeded: SimpleNamespace
) -> None:
    other = Tenant(name="Khác")
    db_session.add(other)
    db_session.flush()
    location = Location(tenant_id=other.id, code="KT", name="Kho khác", kind="warehouse", aliases=[])
    item = Item(tenant_id=other.id, code="X1", name="Trứng gà khác", base_unit="Quả")
    db_session.add_all([location, item])
    db_session.flush()
    db_session.add(
        InventoryLog(
            tenant_id=other.id, location_id=location.id, item_id=item.id, action="IN", qty=5, unit="Quả",
            qty_base=5, delta_base=5, event_time=datetime(2026, 11, 4, tzinfo=VN), admin_id=None,
            staff_id=seeded.staff.id, parser_source="regex",
        )
    )  # fmt: skip
    db_session.flush()

    stock = _call(scope, "GetStock", item_ids=[item.id])
    found = _call(scope, "FindItems", name="Trứng gà khác")

    assert stock == {"rows": [], "item_ids_without_rows": [item.id]}
    assert item.id not in {i["item_id"] for i in found["items"]}


def test_find_items_matches_without_diacritics(scope: ToolScope, seeded: SimpleNamespace) -> None:
    item = _item(seeded)

    result = _call(scope, "FindItems", name=fold(item.name))

    assert result["items"][0]["item_id"] == item.id


def test_find_items_matches_alias(scope: ToolScope, db_session: Session, seeded: SimpleNamespace) -> None:
    item = _item(seeded, "3")
    db_session.execute(
        text("INSERT INTO item_aliases (tenant_id, item_id, alias) VALUES (:t, :i, 'mon bi mat zz')"),
        {"t": seeded.tenant.id, "i": item.id},
    )

    result = _call(scope, "FindItems", name="Món bí mật ZZ")

    assert result["items"][0]["item_id"] == item.id


def test_find_items_reports_no_match(scope: ToolScope) -> None:
    result = _call(scope, "FindItems", name="xyzxyz")

    assert result["items"] == [] and "xyzxyz" in result["note"]


def test_get_movements_cuts_days_at_local_midnight(
    scope: ToolScope, db_session: Session, seeded: SimpleNamespace
) -> None:
    item = _item(seeded)
    _log(db_session, seeded, item, "IN", 4, datetime(2026, 11, 4, 23, 30, tzinfo=VN))
    _log(db_session, seeded, item, "IN", 6, datetime(2026, 11, 5, 0, 30, tzinfo=VN))

    result = _call(scope, "GetMovements", item_id=item.id, date_from="2026-11-04", date_to="2026-11-04")

    assert result["totals"] == [{"action": "IN", "lines": 1, "qty_base": "4"}]
    assert [r["event_time"] for r in result["recent"]] == ["2026-11-04T23:30+07:00"]


def test_top_items_ranks_by_quantity_and_filters_destination(
    scope: ToolScope, db_session: Session, seeded: SimpleNamespace
) -> None:
    first, second = _item(seeded, "1"), _item(seeded, "3")
    when = datetime(2026, 11, 4, 9, 0, tzinfo=VN)
    _log(db_session, seeded, first, "IN", 50, when)
    _log(db_session, seeded, second, "IN", 50, when)
    _log(db_session, seeded, first, "OUT", 5, when, counterpart="K220")
    _log(db_session, seeded, second, "OUT", 9, when, counterpart="K220")
    _log(db_session, seeded, first, "OUT", 20, when, counterpart="PQ")

    to_220 = _call(scope, "TopItems", date_from="2026-11-01", date_to="2026-11-05", action="OUT",
                   counterpart_code="k220")  # fmt: skip

    assert [(r["item_id"], r["total_qty_base"]) for r in to_220["items"]] == [
        (second.id, "9"),
        (first.id, "5"),
    ]


def test_staff_activity_counts_lines_per_staff(
    scope: ToolScope, db_session: Session, seeded: SimpleNamespace
) -> None:
    when = datetime(2026, 11, 4, 9, 0, tzinfo=VN)
    _log(db_session, seeded, _item(seeded), "IN", 5, when)
    _log(db_session, seeded, _item(seeded), "OUT", 1, when)

    result = _call(scope, "StaffActivity", date_from="2026-11-01", date_to="2026-11-05")

    assert result["staff"] == [{"staff_name": "Lan", "lines": 2, "in_lines": 1, "out_lines": 1}]


@pytest.mark.parametrize(
    ("name", "args", "message"),
    [
        ("GetMovements", {"item_id": 1, "date_from": "2026-11-06", "date_to": "2026-11-06"}, "sau hôm nay"),
        ("GetMovements", {"item_id": 1, "date_from": "2026-11-05", "date_to": "2026-11-01"}, "date_from"),
        ("StaffActivity", {"date_from": "2026-01-01", "date_to": "2026-11-05"}, "tối đa 92"),
        ("GetStock", {"item_ids": [1], "location_code": "HN"}, "Kho hợp lệ: KT"),
        (
            "GetMovements",
            {"item_id": 999999, "date_from": "2026-11-01", "date_to": "2026-11-05"},
            "FindItems",
        ),
        ("GetStock", {"item_ids": []}, "Tham số không hợp lệ"),
        ("DeleteAll", {}, "Không có công cụ"),
    ],
    ids=["future", "reversed", "too_long", "unknown_location", "unknown_item", "bad_args", "unknown_tool"],
)
def test_bad_requests_come_back_as_error_for_gemini(
    scope: ToolScope, name: str, args: dict, message: str
) -> None:
    result = json.loads(run_tool(name, args, scope))

    assert message in result["error"]
