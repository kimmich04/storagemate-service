"""Số liệu dashboard đọc thẳng từ inventory_log. Luôn lọc tenant_id + location_id tường minh."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dashboard.dependencies import DashboardScope
from app.exceptions import NotFoundError
from app.inventory.dependencies import WarehouseScope

# Dòng "Thực xuất T10 = tồn đầu + nhập − hủy − điều chuyển…" (kho 220, 31/10) là số tính ngược để cân tồn
# cuối tháng, KHÔNG phải lượt xuất thật → không đếm. Nếu nạp lại dữ liệu thành ADJUST thì bỏ hằng này.
BALANCING_NOTE_PREFIX = "Thực xuất T10"

# Một "lượt" = dòng IN/OUT của kho đang xem; bỏ dòng hủy và dòng đã bị hủy.
_COUNTED_ROWS = """
    l.tenant_id = :tenant AND l.location_id = :loc
    AND l.action IN ('IN', 'OUT')
    AND l.reverses_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM inventory_log r WHERE r.reverses_id = l.id)
    AND coalesce(l.note, '') NOT LIKE :balancing
"""


@dataclass(frozen=True)
class DayCount:
    date: date
    in_count: int
    out_count: int


def resolve_end_date(db: Session, scope: DashboardScope, to: date | None) -> date:
    """Mốc cuối: tham số `to`, hoặc ngày có dòng sổ mới nhất của kho (rỗng → hôm nay)."""
    if to is not None:
        return to
    latest = db.execute(
        text(
            "SELECT max((event_time AT TIME ZONE :tz)::date) FROM inventory_log "
            "WHERE tenant_id = :tenant AND location_id = :loc"
        ),
        {"tz": scope.timezone, "tenant": scope.tenant_id, "loc": scope.location.id},
    ).scalar()
    return latest or datetime.now(ZoneInfo(scope.timezone)).date()


def daily_counts(db: Session, scope: DashboardScope, end: date, range_days: int) -> list[DayCount]:
    """Đúng `range_days` phần tử, ngày không có giao dịch = 0."""
    start = end - timedelta(days=range_days - 1)
    rows = db.execute(
        text(f"""
            WITH days AS (
                SELECT d::date AS day
                FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') d
            ), counts AS (
                SELECT (l.event_time AT TIME ZONE :tz)::date AS day,
                       count(*) FILTER (WHERE l.action = 'IN')  AS in_count,
                       count(*) FILTER (WHERE l.action = 'OUT') AS out_count
                FROM inventory_log l
                WHERE {_COUNTED_ROWS}
                  AND (l.event_time AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY 1
            )
            SELECT days.day, coalesce(c.in_count, 0), coalesce(c.out_count, 0)
            FROM days LEFT JOIN counts c USING (day)
            ORDER BY days.day
        """),
        {
            "start": start,
            "end": end,
            "tz": scope.timezone,
            "tenant": scope.tenant_id,
            "loc": scope.location.id,
            "balancing": f"{BALANCING_NOTE_PREFIX}%",
        },
    ).all()
    return [DayCount(date=r[0], in_count=r[1], out_count=r[2]) for r in rows]


@dataclass(frozen=True)
class PeriodTotal:
    value: int
    delta_pct: int  # % so với kỳ trước cùng độ dài; kỳ trước = 0 thì trả 0


def _delta_pct(cur: int, prev: int) -> int:
    return 0 if prev == 0 else round((cur - prev) / prev * 100)


def stock_in_out_totals(
    db: Session, scope: DashboardScope, end: date, range_days: int
) -> tuple[PeriodTotal, PeriodTotal]:
    """(nhập, xuất) của kỳ gần nhất + so với kỳ trước; dùng chung daily_counts với in-out."""
    days = daily_counts(db, scope, end, range_days * 2)
    prev, cur = days[:range_days], days[range_days:]
    in_cur, in_prev = sum(d.in_count for d in cur), sum(d.in_count for d in prev)
    out_cur, out_prev = sum(d.out_count for d in cur), sum(d.out_count for d in prev)
    return (
        PeriodTotal(in_cur, _delta_pct(in_cur, in_prev)),
        PeriodTotal(out_cur, _delta_pct(out_cur, out_prev)),
    )


@dataclass(frozen=True)
class RecentTx:
    id: int
    at: datetime
    action: str
    is_reversal: bool
    qty: Decimal
    unit: str
    item_name: str
    staff_name: str
    location_name: str
    counterpart: str | None
    source: str
    confirmed: bool


def recent_transactions(db: Session, scope: DashboardScope, limit: int) -> list[RecentTx]:
    """N giao dịch mới nhất của kho (mọi action). Bỏ tồn đầu kỳ (opening) và dòng cân tồn cuối tháng."""
    rows = db.execute(
        text("""
            SELECT l.id, l.event_time, l.action::text, l.reverses_id IS NOT NULL, l.qty, l.unit,
                   i.name, coalesce(s.name, a.name), loc.name, cp.name, l.parser_source::text,
                   (l.parser_source NOT IN ('ner', 'llm') OR l.pending_action_id IS NOT NULL)
            FROM inventory_log l
            JOIN items i ON i.id = l.item_id
            JOIN locations loc ON loc.id = l.location_id
            LEFT JOIN locations cp ON cp.id = l.counterpart_location_id
            LEFT JOIN staff s ON s.id = l.staff_id
            LEFT JOIN admins a ON a.id = l.admin_id
            WHERE l.tenant_id = :tenant AND l.location_id = :loc
              AND l.parser_source <> 'opening'
              AND coalesce(l.note, '') NOT LIKE :balancing
            ORDER BY l.event_time DESC, l.id DESC
            LIMIT :limit
        """),
        {
            "tenant": scope.tenant_id,
            "loc": scope.location.id,
            "balancing": f"{BALANCING_NOTE_PREFIX}%",
            "limit": limit,
        },
    ).all()
    tz = ZoneInfo(scope.timezone)
    return [RecentTx(r[0], r[1].astimezone(tz), *r[2:7], r[7] or "", *r[8:]) for r in rows]


AVG_OUT_WINDOW_DAYS = 30  # số ngày dùng để tính lượng xuất trung bình mỗi ngày

# Tồn hiện tại của kho = view current_stock (SUM delta_base của MỌI dòng, kể cả tồn đầu, kiểm kê, cân tồn).
# Chỉ xét mặt hàng có dòng sổ ở kho này và đã đặt mức tối thiểu (min_qty > 0).
_STOCK_WITH_MIN = """
    s.tenant_id = :tenant AND s.location_id = :loc
    AND i.tenant_id = :tenant AND i.min_qty > 0 AND i.archived_at IS NULL
"""


@dataclass(frozen=True)
class LowStockItem:
    item_id: int
    name: str
    unit: str
    qty: Decimal
    min_qty: Decimal
    avg_daily_out: Decimal


def low_stock(db: Session, scope: DashboardScope, limit: int) -> list[LowStockItem]:
    """Mặt hàng có tỉ lệ tồn / mức tối thiểu thấp nhất, kèm lượng xuất TB/ngày trong 30 ngày gần nhất."""
    end = resolve_end_date(db, scope, None)
    rows = db.execute(
        text(f"""
            WITH outs AS (
                SELECT l.item_id, sum(l.qty_base) AS out_qty
                FROM inventory_log l
                WHERE {_COUNTED_ROWS} AND l.action = 'OUT'
                  AND (l.event_time AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY l.item_id
            )
            SELECT i.id, i.name, i.base_unit, s.qty_base, i.min_qty,
                   round(coalesce(o.out_qty, 0) / :days, 3)
            FROM current_stock s
            JOIN items i ON i.id = s.item_id
            LEFT JOIN outs o ON o.item_id = s.item_id
            WHERE {_STOCK_WITH_MIN}
            ORDER BY s.qty_base / i.min_qty, i.name
            LIMIT :limit
        """),
        {
            "tenant": scope.tenant_id,
            "loc": scope.location.id,
            "tz": scope.timezone,
            "balancing": f"{BALANCING_NOTE_PREFIX}%",
            "start": end - timedelta(days=AVG_OUT_WINDOW_DAYS - 1),
            "end": end,
            "days": AVG_OUT_WINDOW_DAYS,
            "limit": limit,
        },
    ).all()
    return [LowStockItem(*r) for r in rows]


def below_min_count(db: Session, scope: DashboardScope) -> int:
    """Số mặt hàng có tồn hiện tại < mức tối thiểu."""
    return db.execute(
        text(f"""
            SELECT count(*) FROM current_stock s JOIN items i ON i.id = s.item_id
            WHERE {_STOCK_WITH_MIN} AND s.qty_base < i.min_qty
        """),
        {"tenant": scope.tenant_id, "loc": scope.location.id},
    ).scalar_one()


@dataclass(frozen=True)
class TrackedItem:
    id: int
    name: str
    unit: str
    tracked: bool


def tracked_items(db: Session, scope: DashboardScope, tracked: bool | None) -> list[TrackedItem]:
    """Mặt hàng có sổ ở kho đang xem (cho dropdown biểu đồ tồn). `tracked` = items.pinned; None = tất cả."""
    rows = db.execute(
        text("""
            SELECT i.id, i.name, i.base_unit, i.pinned
            FROM items i
            WHERE i.tenant_id = :tenant AND i.archived_at IS NULL
              AND EXISTS (SELECT 1 FROM current_stock s
                          WHERE s.tenant_id = :tenant AND s.location_id = :loc AND s.item_id = i.id)
              AND (CAST(:tracked AS boolean) IS NULL OR i.pinned = CAST(:tracked AS boolean))
            ORDER BY lower(i.name), i.id
        """),
        {"tenant": scope.tenant_id, "loc": scope.location.id, "tracked": tracked},
    ).all()
    return [TrackedItem(*r) for r in rows]


@dataclass(frozen=True)
class StockPoint:
    date: date
    qty: Decimal


@dataclass(frozen=True)
class StockHistory:
    item_id: int
    item_name: str
    unit: str
    min_qty: Decimal
    points: list[StockPoint]


def stock_history(db: Session, scope: DashboardScope, item_id: int, end: date, days: int) -> StockHistory:
    """Tồn cuối mỗi ngày của một mặt hàng ở kho đang xem = cộng dồn delta_base (mọi dòng) đến hết ngày đó."""
    item = db.execute(
        text("SELECT id, name, base_unit, min_qty FROM items WHERE id = :item AND tenant_id = :tenant"),
        {"item": item_id, "tenant": scope.tenant_id},
    ).first()
    has_ledger = (
        item is not None
        and db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM inventory_log "
                "WHERE tenant_id = :tenant AND location_id = :loc AND item_id = :item)"
            ),
            {"item": item_id, "tenant": scope.tenant_id, "loc": scope.location.id},
        ).scalar_one()
    )
    if item is None or not has_ledger:
        raise NotFoundError("Mặt hàng không có ở kho này")

    rows = db.execute(
        text("""
            WITH days AS (
                SELECT d::date AS day
                FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') d
            ), ledger AS (
                SELECT (event_time AT TIME ZONE :tz)::date AS day, delta_base
                FROM inventory_log
                WHERE tenant_id = :tenant AND location_id = :loc AND item_id = :item
            ), opening AS (
                SELECT coalesce(sum(delta_base), 0) AS qty FROM ledger WHERE day < :start
            ), per_day AS (
                SELECT day, sum(delta_base) AS delta FROM ledger
                WHERE day BETWEEN :start AND :end GROUP BY day
            )
            SELECT days.day,
                   (SELECT qty FROM opening) + sum(coalesce(p.delta, 0)) OVER (ORDER BY days.day)
            FROM days LEFT JOIN per_day p USING (day)
            ORDER BY days.day
        """),
        {
            "start": end - timedelta(days=days - 1),
            "end": end,
            "tz": scope.timezone,
            "tenant": scope.tenant_id,
            "loc": scope.location.id,
            "item": item_id,
        },
    ).all()
    return StockHistory(item[0], item[1], item[2], item[3], [StockPoint(r[0], r[1]) for r in rows])


# ===== Khu bot + nhân viên: tin nhắn của nhân viên thuộc kho đang xem =====
PARSER_CATEGORIES = ("regex", "ner", "llm", "failed")


@dataclass(frozen=True)
class BotMessage:
    staff_id: int
    day: date
    category: str | None  # regex/ner/llm/failed; None = không phải lệnh nhập/xuất (hỏi đáp, OK, Hủy…)


def _bot_messages(db: Session, scope: DashboardScope, start: date, end: date) -> list[BotMessage]:
    """Tin của nhân viên có default_location_id = kho đang xem. Nhóm = nguồn parser của dòng sổ (hoặc
    giao dịch chờ xác nhận) sinh từ tin đó; status failed = "Không hiểu"."""
    rows = db.execute(
        text("""
            SELECT m.staff_id,
                   (coalesce(m.sent_at, m.received_at) AT TIME ZONE :tz)::date,
                   CASE WHEN m.status = 'failed' THEN 'failed' ELSE coalesce(
                       (SELECT l.parser_source::text FROM inventory_log l
                        WHERE l.inbound_id = m.id AND l.parser_source IN ('regex', 'ner', 'llm')
                        ORDER BY l.id LIMIT 1),
                       (SELECT p.parser_source::text FROM pending_actions p
                        WHERE p.inbound_id = m.id AND p.parser_source IN ('regex', 'ner', 'llm')
                        ORDER BY p.id LIMIT 1)
                   ) END
            FROM inbound_messages m
            JOIN staff s ON s.id = m.staff_id
            WHERE m.tenant_id = :tenant AND s.tenant_id = :tenant AND s.default_location_id = :loc
              AND (coalesce(m.sent_at, m.received_at) AT TIME ZONE :tz)::date BETWEEN :start AND :end
        """),
        {
            "tz": scope.timezone,
            "tenant": scope.tenant_id,
            "loc": scope.location.id,
            "start": start,
            "end": end,
        },
    ).all()
    return [BotMessage(*r) for r in rows]


def week_start(d: date) -> date:
    """Thứ Hai của tuần chứa ngày d (tuần lịch thứ Hai – Chủ nhật)."""
    return d - timedelta(days=d.weekday())


def _pct(part: int, total: int) -> int | None:
    """None = không có tin nào để tính (FE hiện "Chưa có tin nhắn từ bot")."""
    return None if total == 0 else round(part * 100 / total)


def _split_100(counts: dict[str, int]) -> dict[str, int]:
    """Phần trăm nguyên cộng lại đúng 100 (chia phần dư lớn nhất trước); tổng 0 → toàn 0."""
    total = sum(counts.values())
    if total == 0:
        return dict.fromkeys(counts, 0)
    exact = {k: v * 100 / total for k, v in counts.items()}
    result = {k: int(v) for k, v in exact.items()}
    by_remainder = sorted(exact, key=lambda k: exact[k] - result[k], reverse=True)
    for k in by_remainder[: 100 - sum(result.values())]:
        result[k] += 1
    return result


@dataclass(frozen=True)
class ParserWeek:
    week_start: date
    regex: int
    ner: int
    llm: int
    failed: int
    total: int


def parser_quality(db: Session, scope: DashboardScope, end: date, weeks: int) -> list[ParserWeek]:
    """Mỗi tuần: % tin lệnh được đọc bằng regex / NER / LLM / không hiểu (tổng 100)."""
    first = week_start(end) - timedelta(weeks=weeks - 1)
    msgs = [m for m in _bot_messages(db, scope, first, end) if m.category]
    result = []
    for i in range(weeks):
        ws = first + timedelta(weeks=i)
        counts = dict.fromkeys(PARSER_CATEGORIES, 0)
        for m in msgs:
            if week_start(m.day) == ws:
                counts[m.category] += 1
        pct = _split_100(counts)
        result.append(
            ParserWeek(ws, pct["regex"], pct["ner"], pct["llm"], pct["failed"], sum(counts.values()))
        )
    return result


def regex_rate(db: Session, scope: DashboardScope, end: date, weeks: int) -> tuple[int | None, int | None]:
    """(% tin lệnh đọc bằng regex trong `weeks` tuần gần nhất, chênh điểm % so với `weeks` tuần trước đó)."""
    cur_start = week_start(end) - timedelta(weeks=weeks - 1)
    prev_start = cur_start - timedelta(weeks=weeks)
    msgs = [m for m in _bot_messages(db, scope, prev_start, end) if m.category]
    cur = [m for m in msgs if m.day >= cur_start]
    prev = [m for m in msgs if m.day < cur_start]
    cur_pct = _pct(sum(m.category == "regex" for m in cur), len(cur))
    prev_pct = _pct(sum(m.category == "regex" for m in prev), len(prev))
    delta = None if cur_pct is None or prev_pct is None else cur_pct - prev_pct
    return cur_pct, delta


def retype(db: Session, scope: DashboardScope, end: date, weeks: int) -> tuple[int | None, int]:
    """(% tin lệnh phải gõ lại, số tin) trong `weeks` tuần gần nhất. Gõ lại = tin có status failed."""
    start = week_start(end) - timedelta(weeks=weeks - 1)
    msgs = [m for m in _bot_messages(db, scope, start, end) if m.category]
    failed = sum(m.category == "failed" for m in msgs)
    return _pct(failed, len(msgs)), failed


@dataclass(frozen=True)
class StaffStat:
    id: int
    name: str
    role: str
    messages: int
    syntax_ok_pct: int | None
    undo_count: int


def staff_stats(
    db: Session, scope: DashboardScope | WarehouseScope, start: date, end: date
) -> list[StaffStat]:
    """[API-T9] Nhân viên đang hoạt động của kho (từ `start` đến `end`, theo ngày múi giờ tenant):
    số tin, % tin lệnh đọc thẳng bằng regex, số lần hủy giao dịch."""
    staff = db.execute(
        text(
            "SELECT id, name, role::text FROM staff "
            "WHERE tenant_id = :tenant AND default_location_id = :loc AND active"
        ),
        {"tenant": scope.tenant_id, "loc": scope.location.id},
    ).all()
    undo = dict(
        db.execute(
            text("""
                SELECT staff_id, count(*) FROM inventory_log
                WHERE tenant_id = :tenant AND reverses_id IS NOT NULL AND staff_id IS NOT NULL
                  AND (event_time AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY staff_id
            """),
            {"tenant": scope.tenant_id, "tz": scope.timezone, "start": start, "end": end},
        ).all()
    )
    msgs = _bot_messages(db, scope, start, end)
    result = []
    for sid, name, role in staff:
        mine = [m for m in msgs if m.staff_id == sid]
        commands = [m for m in mine if m.category]
        ok = _pct(sum(m.category == "regex" for m in commands), len(commands))
        result.append(StaffStat(sid, name, role, len(mine), ok, undo.get(sid, 0)))
    return sorted(result, key=lambda s: (-s.messages, s.name))
