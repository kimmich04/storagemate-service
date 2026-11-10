"""Response của trang Tổng quan (camelCase)."""

from datetime import date
from typing import Literal

from app.inventory.period import PeriodRead
from app.schemas import CamelModel, Number


class KpiRead(CamelModel):
    """[API-T1] [API-T2] [API-T3] [API-T4] Một ô KPI: giá trị kỳ đang chọn + % so với tháng liền trước."""

    value: int
    delta_pct: int | None  # null = tháng trước không có dữ liệu (FE hiện "–")


class InStockRead(CamelModel):
    """[API-T5] Ô "Còn tồn": số mặt hàng còn tồn đầu kỳ → cuối kỳ, trên tổng số mặt hàng có sổ."""

    opening: int
    closing: int
    total: int


class DayInOutRead(CamelModel):
    date: date
    in_count: int
    out_count: int


class InOutRead(CamelModel):
    """[API-T6] Biểu đồ cột lượt nhập / xuất theo ngày."""

    period: PeriodRead
    days: list[DayInOutRead]


class RecentTxRead(CamelModel):
    id: int
    kind: Literal["in", "out"]
    name: str
    unit: str  # đơn vị của dòng (người gõ), đi kèm `qty`
    qty: Number
    event_date: date
    destination_name: str | None  # chỉ có với kind = "out" và đã rõ nơi nhận


class RecentTransactionsRead(CamelModel):
    """[API-T8] Giao dịch gần đây (trộn nhập và xuất)."""

    items: list[RecentTxRead]
