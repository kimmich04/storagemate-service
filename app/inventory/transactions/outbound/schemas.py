"""Response của trang Xuất Kho (camelCase)."""

from datetime import date

from app.inventory.period import PeriodRead
from app.schemas import CamelModel, Number


class OutDestinationOptionRead(CamelModel):
    """[API-O1] Một nơi nhận trong dropdown, kèm số lượt xuất trong kỳ."""

    id: int
    name: str
    kind: str  # branch | partner | ...
    count: int


class OutUnknownCountRead(CamelModel):
    count: int


class OutDestinationsRead(CamelModel):
    """[API-O1] Mọi nơi có lượt xuất trong kỳ; `unknown` = xuất không ghi nơi nhận (null nếu không có)."""

    period: PeriodRead
    destinations: list[OutDestinationOptionRead]
    unknown: OutUnknownCountRead | None


class OutTotalRead(CamelModel):
    """[API-O2] Ô (A): tổng lượt xuất của các nơi nhận đang chọn."""

    count: int


class OutByDestinationRowRead(CamelModel):
    """[API-O3] Một dòng bảng (B)."""

    id: int
    name: str
    kind: str
    count: int
    item_count: int  # số mặt hàng khác nhau được xuất cho nơi này
    last_date: date


class OutUnknownRowRead(CamelModel):
    count: int
    item_count: int
    last_date: date


class OutByDestinationRead(CamelModel):
    """[API-O3] Bảng (B): chỉ các nơi đang chọn, sắp theo số lượt giảm dần."""

    period: PeriodRead
    destinations: list[OutByDestinationRowRead]
    unknown: OutUnknownRowRead | None


class OutSeriesRead(CamelModel):
    key: str  # id nơi nhận dạng chuỗi | "other" | "unknown"
    name: str
    kind: str  # branch | partner | other | unknown


class OutDayRead(CamelModel):
    date: date
    total: int
    counts: dict[str, int]  # key của series -> số lượt; ngày trống = {}


class OutDailyRead(CamelModel):
    """[API-O4] Biểu đồ (C): cột xếp chồng theo nơi nhận; đủ mọi ngày trong kỳ."""

    period: PeriodRead
    series: list[OutSeriesRead]
    days: list[OutDayRead]


class OutTopItemRead(CamelModel):
    item_id: int
    code: str | None
    name: str
    unit: str  # đơn vị gốc của mặt hàng (items.base_unit)
    count: int  # số lượt xuất (tiêu chí xếp hạng)
    qty_base: Number  # tổng số lượng theo đơn vị gốc của chính mặt hàng này


class OutTopItemsRead(CamelModel):
    """[API-O5] Khối (D): xếp theo số lượt xuất, không so sánh số lượng giữa các đơn vị khác nhau."""

    period: PeriodRead
    items: list[OutTopItemRead]


class OutTransactionRead(CamelModel):
    """[API-O6] Một lượt xuất. `qty` theo đơn vị `unit` của lượt đó. Nơi nhận null = chưa rõ."""

    id: int
    item_id: int
    code: str | None
    name: str
    unit: str
    qty: Number
    event_date: date
    destination_id: int | None
    destination_name: str | None
    destination_kind: str | None


class OutTransactionsRead(CamelModel):
    """[API-O6] Phản hồi của GET /api/transactions?type=OUT."""

    period: PeriodRead
    total: int
    page: int
    page_size: int
    items: list[OutTransactionRead]
