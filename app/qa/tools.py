"""Tool chỉ đọc cho Q&A agent: schema Pydantic (Gemini thấy) + hàm truy vấn view qa_* (Gemini không thấy).

Gemini chỉ điền tham số. Tenant, ngày hôm nay và kết nối do code đặt qua ToolScope; mọi truy vấn chạy trên
login qa_reader (chỉ SELECT 4 view qa_*), mỗi lần gọi tool là một transaction ngắn rồi ROLLBACK.
Lỗi tham số / nghiệp vụ không raise mà trả {"error": ...} để Gemini tự sửa ở lượt sau.
"""

import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.parser.aliases import canonical

MAX_TOOL_ROWS = 50
MAX_RANGE_DAYS = 92
MAX_ITEMS_FOUND = 10
MAX_RECENT_MOVES = 20
MIN_MATCH_SCORE = 0.5  # tỉ lệ từ người hỏi gõ có trong tên / tên gọi khác của mặt hàng
STATEMENT_TIMEOUT = "5s"
TOKEN_RE = re.compile(r"[a-z0-9]+")


class ToolError(Exception):
    """Lỗi người hỏi / Gemini sửa được (kho lạ, ngày sai…); nội dung tiếng Việt gửi lại cho Gemini."""


@dataclass(frozen=True)
class ToolScope:
    tenant_id: int
    today: date
    session_factory: Callable[[], Session]  # sessionmaker của login qa_reader


# ---- Schema Gemini thấy (tên lớp = tên tool, docstring = mô tả tool) ----


class FindItems(BaseModel):
    """Tìm mặt hàng trong danh mục theo tên (có dấu hay không dấu đều được). Gọi trước để lấy item_id."""

    name: str = Field(min_length=1, max_length=100, description="Tên mặt hàng như người hỏi viết")


class GetStock(BaseModel):
    """Tồn kho hiện tại theo từng kho (qty_base tính theo base_unit). Mặt hàng không có dòng nào = chưa từng
    có trong sổ, tồn 0."""

    item_ids: list[int] = Field(min_length=1, max_length=20, description="item_id lấy từ FindItems")
    location_code: str | None = Field(default=None, max_length=20, description="Mã kho; bỏ trống = mọi kho")


class GetMovements(BaseModel):
    """Lịch sử nhập/xuất của MỘT mặt hàng trong khoảng ngày: tổng theo loại và các dòng gần nhất."""

    item_id: int
    date_from: date
    date_to: date
    action: Literal["IN", "OUT"] | None = Field(
        default=None, description="IN = nhập, OUT = xuất; trống = cả hai"
    )


class TopItems(BaseModel):
    """Xếp hạng mặt hàng theo tổng số lượng nhập hoặc xuất trong khoảng ngày."""

    date_from: date
    date_to: date
    action: Literal["IN", "OUT"]
    location_code: str | None = Field(default=None, max_length=20, description="Kho ghi sổ; trống = mọi kho")
    counterpart_code: str | None = Field(
        default=None, max_length=20, description="Kho bên kia (nơi nhận khi xuất, nơi gửi khi nhập)"
    )
    limit: int = Field(default=5, ge=1, le=10)


class StaffActivity(BaseModel):
    """Mỗi nhân viên đã ghi bao nhiêu dòng sổ kho (tổng, nhập, xuất) trong khoảng ngày."""

    date_from: date
    date_to: date


TOOLS: dict[str, type[BaseModel]] = {
    schema.__name__: schema for schema in (FindItems, GetStock, GetMovements, TopItems, StaffActivity)
}


# ---- Chạy tool ----


def run_tool(name: str, args: dict[str, Any], scope: ToolScope) -> str:
    """Luôn trả JSON cho Gemini. Lỗi DB (mất kết nối, quá statement_timeout) thì raise: agent sẽ dừng."""
    schema = TOOLS.get(name)
    if schema is None:
        return _error(f"Không có công cụ {name}. Công cụ hợp lệ: {', '.join(TOOLS)}")
    try:
        params = schema.model_validate(args)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        return _error(f"Tham số không hợp lệ — {problems}")
    try:
        with read_only_session(scope.session_factory, scope.tenant_id) as session:
            result = HANDLERS[name](session, params, scope)
    except ToolError as error:
        return _error(str(error))
    return json.dumps(result, ensure_ascii=False, default=_json_value)


@contextmanager
def read_only_session(session_factory: Callable[[], Session], tenant_id: int) -> Iterator[Session]:
    """Một transaction ngắn: đặt tenant + timeout bằng SET LOCAL, ROLLBACK khi xong (xoá luôn SET LOCAL)."""
    with session_factory() as session:
        session.begin()
        try:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
            )
            session.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
            yield session
        finally:
            session.rollback()


def list_locations(scope: ToolScope) -> list[dict[str, Any]]:
    """Danh sách kho cho system prompt."""
    with read_only_session(scope.session_factory, scope.tenant_id) as session:
        return _rows(session, "SELECT code, name, kind FROM qa_locations ORDER BY location_id", {})


# ---- Hàm truy vấn ----


def _find_items(session: Session, params: FindItems, scope: ToolScope) -> dict[str, Any]:
    typed = _tokens(params.name)
    if not typed:
        raise ToolError("Tên mặt hàng phải có chữ hoặc số")
    rows = _rows(session, "SELECT item_id, code, name, category, base_unit, aliases FROM qa_items", {})
    scored = [(score, row) for row in rows if (score := _match_score(typed, row)) >= MIN_MATCH_SCORE]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    items = [{k: v for k, v in row.items() if k != "aliases"} for _, row in scored[:MAX_ITEMS_FOUND]]
    return {"items": items, "note": None if items else f"Không có mặt hàng nào khớp «{params.name}»"}


def _get_stock(session: Session, params: GetStock, scope: ToolScope) -> dict[str, Any]:
    sql = (
        "SELECT item_id, item_name, location_code, location_name, qty_base, base_unit, min_qty, "
        "last_event_time FROM qa_stock WHERE item_id = ANY(:ids)"
    )
    values: dict[str, Any] = {"ids": params.item_ids, "limit": MAX_TOOL_ROWS}
    if params.location_code:
        sql += " AND location_code = :location"
        values["location"] = _location_code(session, params.location_code)
    rows = _rows(session, sql + " ORDER BY item_name, location_name LIMIT :limit", values)
    for row in rows:
        row["below_min"] = row["min_qty"] > 0 and row["qty_base"] < row["min_qty"]
    found = {row["item_id"] for row in rows}
    return {"rows": rows, "item_ids_without_rows": [i for i in params.item_ids if i not in found]}


def _get_movements(session: Session, params: GetMovements, scope: ToolScope) -> dict[str, Any]:
    start, end = _period(params.date_from, params.date_to, scope.today)
    items = _rows(session, "SELECT name, base_unit FROM qa_items WHERE item_id = :id", {"id": params.item_id})
    if not items:
        raise ToolError(f"Không có mặt hàng item_id={params.item_id}; gọi FindItems để lấy item_id đúng")
    where = "item_id = :id AND event_time >= :start AND event_time < :end"
    values: dict[str, Any] = {"id": params.item_id, "start": start, "end": end, "limit": MAX_RECENT_MOVES}
    if params.action:
        where += " AND action = :action"
        values["action"] = params.action
    totals = _rows(
        session,
        f"SELECT action, COUNT(*) AS lines, SUM(qty_base) AS qty_base FROM qa_movements WHERE {where} "
        "GROUP BY action ORDER BY action",
        values,
    )
    recent = _rows(
        session,
        "SELECT event_time, action, qty, unit, qty_base, location_name, counterpart_name, staff_name "
        f"FROM qa_movements WHERE {where} ORDER BY event_time DESC, log_id DESC LIMIT :limit",
        values,
    )
    period = {"date_from": params.date_from, "date_to": params.date_to}
    return {"item": items[0], **period, "totals": totals, "recent": recent}


def _top_items(session: Session, params: TopItems, scope: ToolScope) -> dict[str, Any]:
    start, end = _period(params.date_from, params.date_to, scope.today)
    where = "action = :action AND event_time >= :start AND event_time < :end"
    values: dict[str, Any] = {"action": params.action, "start": start, "end": end, "limit": params.limit}
    if params.location_code:
        where += " AND location_code = :location"
        values["location"] = _location_code(session, params.location_code)
    if params.counterpart_code:
        where += " AND counterpart_code = :counterpart"
        values["counterpart"] = _location_code(session, params.counterpart_code)
    rows = _rows(
        session,
        "SELECT item_id, item_name, base_unit, SUM(qty_base) AS total_qty_base, COUNT(*) AS lines "
        f"FROM qa_movements WHERE {where} GROUP BY item_id, item_name, base_unit "
        "ORDER BY total_qty_base DESC, item_name LIMIT :limit",
        values,
    )
    return {"date_from": params.date_from, "date_to": params.date_to, "action": params.action, "items": rows}


def _staff_activity(session: Session, params: StaffActivity, scope: ToolScope) -> dict[str, Any]:
    start, end = _period(params.date_from, params.date_to, scope.today)
    rows = _rows(
        session,
        "SELECT COALESCE(staff_name, '(quản trị viên)') AS staff_name, COUNT(*) AS lines, "
        "COUNT(*) FILTER (WHERE action = 'IN') AS in_lines, "
        "COUNT(*) FILTER (WHERE action = 'OUT') AS out_lines "
        "FROM qa_movements WHERE event_time >= :start AND event_time < :end "
        "GROUP BY 1 ORDER BY lines DESC, staff_name LIMIT :limit",
        {"start": start, "end": end, "limit": MAX_TOOL_ROWS},
    )
    return {"date_from": params.date_from, "date_to": params.date_to, "staff": rows}


HANDLERS: dict[str, Callable[[Session, Any, ToolScope], dict[str, Any]]] = {
    "FindItems": _find_items,
    "GetStock": _get_stock,
    "GetMovements": _get_movements,
    "TopItems": _top_items,
    "StaffActivity": _staff_activity,
}


# ---- Hỗ trợ ----


def _rows(session: Session, sql: str, values: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(text(sql), values).mappings()]


def _period(date_from: date, date_to: date, today: date) -> tuple[datetime, datetime]:
    """[đầu ngày date_from, đầu ngày sau date_to) theo giờ địa phương."""
    if date_from > date_to:
        raise ToolError("date_from phải trước hoặc bằng date_to")
    if date_to > today:
        raise ToolError(f"date_to không được sau hôm nay ({today.isoformat()})")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ToolError(f"Khoảng ngày tối đa {MAX_RANGE_DAYS} ngày; chia nhỏ câu hỏi")
    tz = ZoneInfo(settings.TZ)
    return datetime.combine(date_from, time.min, tz), datetime.combine(
        date_to + timedelta(days=1), time.min, tz
    )


def _location_code(session: Session, code: str) -> str:
    locations = _rows(session, "SELECT code, name FROM qa_locations ORDER BY location_id", {})
    for location in locations:
        if location["code"].lower() == code.strip().lower():
            return location["code"]
    valid = ", ".join(f"{loc['code']} ({loc['name']})" for loc in locations)
    raise ToolError(f"Không có kho mã «{code}». Kho hợp lệ: {valid}")


def _tokens(name: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(canonical(name)))


def _match_score(typed: frozenset[str], row: dict[str, Any]) -> float:
    """Tỉ lệ từ đã gõ có trong tên; trùng khít tên hoặc tên gọi khác thì xếp trên cùng."""
    names = [row["name"], *(row["aliases"] or [])]
    if any(_tokens(name) == typed for name in names):
        return 2.0
    return max(len(typed & _tokens(name)) / len(typed) for name in names)


def _error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _json_value(value: object) -> str:
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo(settings.TZ)).isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Không chuyển được {type(value).__name__} sang JSON")
