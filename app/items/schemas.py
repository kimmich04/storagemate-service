"""Pydantic: ItemCreate, ItemUpdate, ItemRead, UnitConversion."""

from app.schemas import CamelModel, Number


class CategoryRead(CamelModel):
    """[API-C0] Một nhóm hàng kèm số mặt hàng."""

    name: str
    count: int


class LocationOptionRead(CamelModel):
    """[API-D1] Một kho trong dropdown "Kho"; `item_count` = mặt hàng có dòng sổ ở kho đó."""

    id: int
    name: str
    kind: str  # warehouse | branch
    item_count: int


class ItemLocationsRead(CamelModel):
    """[API-D1] Kho tổng + chi nhánh, và số mặt hàng chưa có dòng sổ nào (lựa chọn "Chưa có giao dịch")."""

    locations: list[LocationOptionRead]
    no_transactions_count: int


class UnitRead(CamelModel):
    """Một quy đổi đóng gói: 1 `name` = `factor` đơn vị gốc (đã bỏ dòng của chính đơn vị gốc)."""

    name: str
    factor: Number


class ItemRead(CamelModel):
    """[API-D2] Một dòng của bảng danh mục."""

    id: int
    code: str | None
    name: str
    category: str | None
    unit: str  # đơn vị gốc
    min_qty: Number
    units: list[UnitRead]
    matched_alias: str | None  # chỉ có khi từ khóa khớp tên gọi khác mà không khớp tên/Mã VT


class ItemsPageRead(CamelModel):
    """[API-D2] Phản hồi của GET /api/items."""

    total: int
    page: int
    page_size: int
    items: list[ItemRead]
