"""🖥️ /api/dashboard — số liệu trang Tổng quan. Mỗi component một endpoint."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.dashboard import service
from app.dashboard.dependencies import Scope
from app.dashboard.overview.router import router as overview_router
from app.dashboard.schemas import (
    CountRead,
    ItemRef,
    LocationRef,
    LowStockItemRead,
    LowStockRead,
    ParserQualityRead,
    ParserWeekRead,
    RegexRateRead,
    RetypeRead,
    StockHistoryRead,
    StockPointRead,
    TrackedItemRead,
    TrackedItemsRead,
)
from app.database import DbSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


EndDate = Annotated[date | None, Query(description="Ngày cuối; bỏ trống = ngày có dữ liệu mới nhất")]
WeeksQuery = Annotated[int, Query(ge=1, le=4, description="Số tuần gần nhất (thứ Hai – Chủ nhật)")]


# /in-out, /kpis/stock-in, /kpis/stock-out, /recent-transactions và các KPI mới của Tổng quan
# nay nằm ở overview/router.py (kho tổng, kỳ month/from/to).
router.include_router(overview_router)


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
