from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas import CamelModel, Number


class DayCountRead(CamelModel):
    date: date
    in_count: int
    out_count: int


class InOutRead(CamelModel):
    from_: date = Field(alias="from")
    to: date
    days: list[DayCountRead]


class PeriodTotalRead(CamelModel):
    value: int
    delta_pct: int


class RecentTxRead(CamelModel):
    id: int
    at: datetime
    action: Literal["IN", "OUT", "WASTE", "ADJUST", "TRANSFER", "PRODUCE"]
    is_reversal: bool
    qty: Number
    unit: str
    item_name: str
    staff_name: str
    location_name: str
    counterpart: str | None  # tên kho đối tác của giao dịch chuyển kho
    source: Literal["regex", "ner", "llm", "manual", "opening", "undo"]
    confirmed: bool


class RecentTransactionsRead(CamelModel):
    items: list[RecentTxRead]


class LowStockItemRead(CamelModel):
    item_id: int
    name: str
    unit: str  # đơn vị gốc của mặt hàng (items.base_unit)
    qty: Number
    min_qty: Number
    avg_daily_out: Number


class LowStockRead(CamelModel):
    items: list[LowStockItemRead]


class CountRead(CamelModel):
    count: int


class TrackedItemRead(CamelModel):
    id: int
    name: str
    unit: str  # đơn vị gốc (items.base_unit)
    tracked: bool  # = items.pinned


class TrackedItemsRead(CamelModel):
    items: list[TrackedItemRead]


class ItemRef(CamelModel):
    id: int
    name: str
    unit: str


class LocationRef(CamelModel):
    id: int
    name: str


class StockPointRead(CamelModel):
    date: date
    qty: Number


class StockHistoryRead(CamelModel):
    item: ItemRef
    location: LocationRef
    min_qty: Number  # items.min_qty; 0 = chưa đặt mức tối thiểu
    points: list[StockPointRead]


class ParserWeekRead(CamelModel):
    week_start: date
    regex: int  # phần trăm, 4 số cộng lại = 100 (toàn 0 nếu tuần không có tin)
    ner: int
    llm: int
    failed: int
    total: int  # số tin lệnh trong tuần


class ParserQualityRead(CamelModel):
    weeks: list[ParserWeekRead]


class RegexRateRead(CamelModel):
    pct: int | None  # null = chưa có tin nhắn từ bot
    delta_pt: int | None  # điểm % so với kỳ trước; null nếu một trong hai kỳ không có tin


class RetypeRead(CamelModel):
    pct: int | None
    count: int


class StaffStatRead(CamelModel):
    id: int
    name: str
    role: Literal["staff", "manager"]
    messages: int
    syntax_ok_pct: int | None  # null = nhân viên chưa gửi tin lệnh nào
    undo_count: int


class StaffStatsRead(CamelModel):
    staff: list[StaffStatRead]
