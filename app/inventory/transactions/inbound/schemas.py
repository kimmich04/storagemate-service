"""Response của trang Nhập Kho (camelCase)."""

from datetime import date

from app.inventory.period import PeriodRead
from app.schemas import CamelModel, Number


class InDayRead(CamelModel):
    date: date
    count: int


class InDailyRead(CamelModel):
    """[API-I1] Số lượt nhập theo ngày; đủ mọi ngày trong kỳ, ngày trống = 0."""

    period: PeriodRead
    days: list[InDayRead]


class InTransactionRead(CamelModel):
    """[API-I2] Một lượt nhập. `qty` theo đơn vị `unit` của lượt đó (không quy về đơn vị gốc)."""

    id: int
    item_id: int
    code: str | None
    name: str
    unit: str
    qty: Number
    event_date: date


class InTransactionsRead(CamelModel):
    """[API-I2] Phản hồi của GET /api/transactions?type=IN."""

    period: PeriodRead
    total: int
    page: int
    page_size: int
    items: list[InTransactionRead]
