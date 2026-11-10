"""Khu bot + nhân viên: staff, kpis/regex-rate, kpis/retype, parser-quality.

Bảng staff / inbound_messages đang trống → mỗi test tự tạo dữ liệu mẫu trong transaction rollback.
Mốc: dữ liệu sổ kết thúc thứ Bảy 31/10/2026 → tuần gần nhất = 26/10–1/11, tuần trước = 19/10–25/10.
"""

import itertools

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_ext = itertools.count(1)


def _staff(db: Session, name: str, loc: int, role: str = "staff") -> int:
    return db.execute(
        text(
            "INSERT INTO staff (tenant_id, default_location_id, name, role) "
            "VALUES (1, :loc, :name, CAST(:role AS staff_role)) RETURNING id"
        ),
        {"loc": loc, "name": name, "role": role},
    ).scalar_one()


def _item(db: Session) -> int:
    return db.execute(text("SELECT item_id FROM current_stock WHERE location_id = 1 LIMIT 1")).scalar_one()


def _ledger(
    db: Session, staff: int, day: str, source: str, inbound: int | None = None, **extra: object
) -> int:
    action, delta, reverses = ("OUT", -1, extra["reverses"]) if source == "undo" else ("IN", 1, None)
    return db.execute(
        text("""
            INSERT INTO inventory_log (tenant_id, location_id, item_id, action, qty, unit, qty_base,
                                       delta_base, event_time, staff_id, inbound_id, parser_source,
                                       reverses_id)
            VALUES (1, 1, :item, CAST(:action AS inv_action), 1, 'x', 1, :delta, CAST(:t AS timestamptz),
                    :staff, :inbound, CAST(:src AS parser_source), :rev)
            RETURNING id
        """),
        {
            "item": _item(db),
            "action": action,
            "delta": delta,
            "t": f"{day} 10:00+07",
            "staff": staff,
            "inbound": inbound,
            "src": source,
            "rev": reverses,
        },
    ).scalar_one()


def _msg(db: Session, staff: int, day: str, kind: str) -> int | None:
    """kind: regex/ner/llm (có dòng sổ), pending_ner (NER đọc, nhân viên bấm Sai), failed, other (hỏi đáp)."""
    inbound = db.execute(
        text("""
            INSERT INTO inbound_messages (channel, external_id, chat_id, event_name, payload, sent_at,
                                          tenant_id, staff_id, status)
            VALUES ('zalo', :ext, 'chat', 'message.text.received', '{}', CAST(:t AS timestamptz),
                    1, :staff, CAST(:status AS inbound_status))
            RETURNING id
        """),
        {
            "ext": f"t{next(_ext)}",
            "t": f"{day} 10:00+07",
            "staff": staff,
            "status": "failed" if kind == "failed" else "done",
        },  # fmt: skip
    ).scalar_one()
    if kind in ("regex", "ner", "llm"):
        return _ledger(db, staff, day, kind, inbound)
    if kind == "pending_ner":
        db.execute(
            text("""
                INSERT INTO pending_actions (tenant_id, staff_id, chat_id, inbound_id, parsed, parser_source,
                                             status, expires_at)
                VALUES (1, :staff, 'chat', :inbound, '{}', 'ner', 'rejected', now())
            """),
            {"staff": staff, "inbound": inbound},
        )
    return None


@pytest.fixture
def seeded(db: Session) -> dict[str, int]:
    """Kho tổng: Lan (staff), Minh (manager). Chi nhánh 220: Vy (không được tính vào kho tổng)."""
    lan, minh, vy = _staff(db, "Lan", 1), _staff(db, "Minh", 1, "manager"), _staff(db, "Vy", 2)
    # Tuần 26/10: regex 3, llm 1, ner 1 (bị bấm Sai), failed 1 → 6 tin lệnh; thêm 1 tin hỏi đáp
    first_regex = _msg(db, lan, "2026-10-28", "regex")
    for kind in ("regex", "regex", "failed", "other"):
        _msg(db, lan, "2026-10-28", kind)
    _msg(db, minh, "2026-10-30", "llm")
    _msg(db, minh, "2026-10-29", "pending_ner")
    for _ in range(5):
        _msg(db, vy, "2026-10-29", "regex")
    # Tuần 19/10: regex 1, ner 3
    for kind in ("regex", "ner", "ner", "ner"):
        _msg(db, lan, "2026-10-22", kind)
    # Lan hủy 1 giao dịch ngày 31/10
    _ledger(db, lan, "2026-10-31", "undo", reverses=first_regex)
    return {"lan": lan, "minh": minh, "vy": vy}


def _get(http: TestClient, path: str, **params: object) -> dict:
    res = http.get(f"/api/dashboard/{path}", params=params)
    assert res.status_code == 200, res.text
    return res.json()


# ----- không có dữ liệu bot -----
def test_empty_bot_data_returns_null_and_zeros(http: TestClient) -> None:
    assert _get(http, "kpis/regex-rate") == {"pct": None, "deltaPt": None}
    assert _get(http, "kpis/retype") == {"pct": None, "count": 0}
    assert _get(http, "staff") == {"staff": []}
    weeks = _get(http, "parser-quality")["weeks"]
    assert [w["weekStart"] for w in weeks] == ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
    assert all(w == {**w, "regex": 0, "ner": 0, "llm": 0, "failed": 0, "total": 0} for w in weeks)


# ----- parser-quality -----
def test_parser_quality_percentages_sum_to_100(http: TestClient, seeded: dict) -> None:
    weeks = _get(http, "parser-quality", weeks=2)["weeks"]
    assert weeks[0] == {"weekStart": "2026-10-19", "regex": 25, "ner": 75, "llm": 0, "failed": 0, "total": 4}
    # 3/6 regex = 50; ner, llm, failed mỗi loại 16,67 → hai loại được làm tròn lên 17 để tổng đúng 100
    last = weeks[1]
    assert last["weekStart"] == "2026-10-26" and last["total"] == 6 and last["regex"] == 50
    assert sorted([last["ner"], last["llm"], last["failed"]]) == [16, 17, 17]
    assert last["regex"] + last["ner"] + last["llm"] + last["failed"] == 100


# ----- kpis -----
def test_regex_rate_and_delta(http: TestClient, seeded: dict) -> None:
    assert _get(http, "kpis/regex-rate", weeks=1) == {"pct": 50, "deltaPt": 25}  # 3/6 so với 1/4
    assert _get(http, "kpis/regex-rate", weeks=2) == {"pct": 40, "deltaPt": None}  # 4/10, 2 tuần trước trống


def test_retype(http: TestClient, seeded: dict) -> None:
    assert _get(http, "kpis/retype", weeks=1) == {"pct": 17, "count": 1}  # 1/6
    assert _get(http, "kpis/retype", weeks=2) == {"pct": 10, "count": 1}  # 1/10


def test_branch_only_counts_its_own_staff(http: TestClient, seeded: dict) -> None:
    assert _get(http, "kpis/regex-rate", weeks=1, location_id=2) == {"pct": 100, "deltaPt": None}
    assert _get(http, "kpis/retype", weeks=1, location_id=2) == {"pct": 0, "count": 0}


# ----- staff -----
def test_staff_table(http: TestClient, seeded: dict) -> None:
    rows = _get(http, "staff", range=7)["staff"]
    # Lan: 5 tin (3 regex + 1 failed + 1 hỏi đáp) → 3/4 tin lệnh là regex; hủy 1 giao dịch
    # Minh: 2 tin (llm + ner bị bấm Sai) → 0/2 regex. Sắp theo số tin giảm dần.
    assert [
        (r["id"], r["name"], r["role"], r["messages"], r["syntaxOkPct"], r["undoCount"]) for r in rows
    ] == [
        (seeded["lan"], "Lan", "staff", 5, 75, 1),
        (seeded["minh"], "Minh", "manager", 2, 0, 0),
    ]
    lan14 = _get(http, "staff", range=14)["staff"][0]
    assert lan14["messages"] == 9 and lan14["syntaxOkPct"] == 50  # thêm tuần 19/10: 4/8 tin lệnh là regex


def test_staff_of_branch(http: TestClient, seeded: dict) -> None:
    rows = _get(http, "staff", location_id=2)["staff"]
    assert [(r["name"], r["messages"], r["syntaxOkPct"]) for r in rows] == [("Vy", 5, 100)]


def test_staff_without_commands_has_null_syntax_pct(http: TestClient, db: Session) -> None:
    hoa = _staff(db, "Hòa", 1)
    assert _get(http, "staff")["staff"] == [
        {"id": hoa, "name": "Hòa", "role": "staff", "messages": 0, "syntaxOkPct": None, "undoCount": 0}
    ]


@pytest.mark.parametrize("path", ["kpis/regex-rate", "kpis/retype", "parser-quality"])
@pytest.mark.parametrize("weeks", [0, 5])
def test_bad_weeks(http: TestClient, path: str, weeks: int) -> None:
    assert http.get(f"/api/dashboard/{path}", params={"weeks": weeks}).status_code == 422
