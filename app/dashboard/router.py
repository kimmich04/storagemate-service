"""🖥️ /api/dashboard — số liệu trang Tổng quan. Mỗi component một endpoint."""

from datetime import date
from enum import IntEnum
from typing import Annotated

from fastapi import APIRouter, Query

from app.dashboard import service
from app.dashboard.dependencies import Scope
from app.dashboard.schemas import (
    CountRead,
    DayCountRead,
    InOutRead,
    ItemRef,
    LocationRef,
    LowStockItemRead,
    LowStockRead,
    ParserQualityRead,
    ParserWeekRead,
    PeriodTotalRead,
    RecentTransactionsRead,
    RecentTxRead,
    RegexRateRead,
    RetypeRead,
    StaffStatRead,
    StaffStatsRead,
    StockHistoryRead,
    StockPointRead,
    TrackedItemRead,
    TrackedItemsRead,
)
from app.database import DbSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class RangeDays(IntEnum):
    """Số ngày gần nhất mà bộ lọc 7/14/30 của FE cho phép."""

    WEEK = 7
    TWO_WEEKS = 14
    MONTH = 30


RangeQuery = Annotated[RangeDays, Query(description="Số ngày gần nhất")]
EndDate = Annotated[date | None, Query(description="Ngày cuối; bỏ trống = ngày có dữ liệu mới nhất")]
WeeksQuery = Annotated[int, Query(ge=1, le=4, description="Số tuần gần nhất (thứ Hai – Chủ nhật)")]


@router.get("/in-out")
def get_in_out(
    db: DbSession, scope: Scope, range: RangeQuery = RangeDays.WEEK, to: EndDate = None
) -> InOutRead:
    """Số lượt nhập/xuất theo ngày; luôn đủ `range` ngày, ngày trống = 0."""
    end = service.resolve_end_date(db, scope, to)
    days = service.daily_counts(db, scope, end, int(range))
    return InOutRead(
        from_=days[0].date,
        to=end,
        days=[DayCountRead(date=d.date, in_count=d.in_count, out_count=d.out_count) for d in days],
    )


@router.get("/kpis/stock-in")
def get_stock_in_kpi(
    db: DbSession, scope: Scope, range: RangeQuery = RangeDays.WEEK, to: EndDate = None
) -> PeriodTotalRead:
    """Ô Lượt nhập: tổng lượt nhập trong kỳ + % thay đổi so với kỳ trước."""
    end = service.resolve_end_date(db, scope, to)
    stock_in, _ = service.stock_in_out_totals(db, scope, end, int(range))
    return PeriodTotalRead(value=stock_in.value, delta_pct=stock_in.delta_pct)


@router.get("/kpis/stock-out")
def get_stock_out_kpi(
    db: DbSession, scope: Scope, range: RangeQuery = RangeDays.WEEK, to: EndDate = None
) -> PeriodTotalRead:
    """Ô Lượt xuất: tổng lượt xuất trong kỳ + % thay đổi so với kỳ trước."""
    end = service.resolve_end_date(db, scope, to)
    _, stock_out = service.stock_in_out_totals(db, scope, end, int(range))
    return PeriodTotalRead(value=stock_out.value, delta_pct=stock_out.delta_pct)


@router.get("/recent-transactions")
def get_recent_transactions(
    db: DbSession, scope: Scope, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> RecentTransactionsRead:
    """Giao dịch gần đây: `limit` giao dịch mới nhất của kho, không phụ thuộc bộ lọc ngày."""
    rows = service.recent_transactions(db, scope, limit)
    return RecentTransactionsRead(items=[RecentTxRead.model_validate(r) for r in rows])


@router.get("/kpis/below-min")
def get_below_min_kpi(db: DbSession, scope: Scope) -> CountRead:
    """Ô Dưới mức tối thiểu: số mặt hàng có tồn hiện tại < min_qty (không theo bộ lọc ngày)."""
    return CountRead(count=service.below_min_count(db, scope))


@router.get("/low-stock")
def get_low_stock(db: DbSession, scope: Scope, limit: Annotated[int, Query(ge=1, le=20)] = 5) -> LowStockRead:
    """Sắp hết hàng: `limit` mặt hàng có tồn / min_qty thấp nhất. FE tự suy ra Dưới mức / Sắp chạm / Đủ."""
    rows = service.low_stock(db, scope, limit)
    return LowStockRead(items=[LowStockItemRead.model_validate(r) for r in rows])


@router.get("/tracked-items")
def get_tracked_items(
    db: DbSession,
    scope: Scope,
    tracked: Annotated[bool | None, Query(description="true = chỉ mặt hàng được theo dõi (pinned)")] = None,
) -> TrackedItemsRead:
    """Danh sách mặt hàng cho biểu đồ tồn. Bỏ trống `tracked` = tất cả mặt hàng có sổ ở kho."""
    rows = service.tracked_items(db, scope, tracked)
    return TrackedItemsRead(items=[TrackedItemRead.model_validate(r) for r in rows])


@router.get("/stock/{item_id}/history")
def get_stock_history(
    db: DbSession,
    scope: Scope,
    item_id: int,
    days: Annotated[int, Query(ge=1, le=90, description="Số ngày gần nhất")] = 30,
    to: EndDate = None,
) -> StockHistoryRead:
    """Đường tồn của một mặt hàng ở kho đang xem: tồn cuối mỗi ngày, đủ `days` điểm."""
    end = service.resolve_end_date(db, scope, to)
    h = service.stock_history(db, scope, item_id, end, days)
    return StockHistoryRead(
        item=ItemRef(id=h.item_id, name=h.item_name, unit=h.unit),
        location=LocationRef(id=scope.location.id, name=scope.location.name),
        min_qty=h.min_qty,
        points=[StockPointRead(date=p.date, qty=p.qty) for p in h.points],
    )


@router.get("/staff")
def get_staff_stats(
    db: DbSession, scope: Scope, range: RangeQuery = RangeDays.WEEK, to: EndDate = None
) -> StaffStatsRead:
    """Bảng Nhân viên: số tin, % cú pháp đúng (regex), số lần hủy trong `range` ngày."""
    end = service.resolve_end_date(db, scope, to)
    rows = service.staff_stats(db, scope, end, int(range))
    return StaffStatsRead(staff=[StaffStatRead.model_validate(r) for r in rows])


@router.get("/kpis/regex-rate")
def get_regex_rate_kpi(
    db: DbSession, scope: Scope, weeks: WeeksQuery = 4, to: EndDate = None
) -> RegexRateRead:
    """Ô Hiểu ngay bằng regex: % tin lệnh đọc bằng regex + chênh điểm % so với kỳ trước."""
    end = service.resolve_end_date(db, scope, to)
    pct, delta = service.regex_rate(db, scope, end, weeks)
    return RegexRateRead(pct=pct, delta_pt=delta)


@router.get("/kpis/retype")
def get_retype_kpi(db: DbSession, scope: Scope, weeks: WeeksQuery = 4, to: EndDate = None) -> RetypeRead:
    """Ô Tin phải gõ lại: % và số tin lệnh bot không hiểu (status failed)."""
    end = service.resolve_end_date(db, scope, to)
    pct, count = service.retype(db, scope, end, weeks)
    return RetypeRead(pct=pct, count=count)


@router.get("/parser-quality")
def get_parser_quality(
    db: DbSession, scope: Scope, weeks: WeeksQuery = 4, to: EndDate = None
) -> ParserQualityRead:
    """Bot hiểu tin nhắn bằng gì: mỗi tuần một thanh % regex / NER / LLM / không hiểu."""
    end = service.resolve_end_date(db, scope, to)
    rows = service.parser_quality(db, scope, end, weeks)
    return ParserQualityRead(weeks=[ParserWeekRead.model_validate(r) for r in rows])
