"""Response của trang Tồn Kho (camelCase)."""

from typing import Literal

from app.inventory.period import PeriodRead
from app.schemas import CamelModel, Number


class CountRead(CamelModel):
    """[API-S1] [API-S2] [API-S3] Một con số của thẻ KPI."""

    count: int


class DestinationRead(CamelModel):
    """[API-S4] Một cột nơi nhận của nhóm cột Xuất. `id` null = xuất không ghi nơi nhận."""

    id: int | None
    name: str
    kind: Literal["warehouse", "branch", "partner", "unknown"]  # unknown = chưa rõ nơi nhận


class StockItemRead(CamelModel):
    """[API-S5] Một dòng của bảng chính."""

    item_id: int
    code: str | None
    name: str
    category: str | None
    unit: str  # đơn vị gốc (items.base_unit)
    opening: Number
    inbound: Number
    outbound: dict[str, Number]  # "<id kho nhận>" -> số lượng; khóa "null" = chưa rõ nơi nhận
    outbound_total: Number
    waste: Number
    variance: Number
    other: Number
    closing: Number


class StockRead(CamelModel):
    """[API-S5] Phản hồi của GET /api/stock."""

    period: PeriodRead
    total: int
    page: int
    page_size: int
    items: list[StockItemRead]
