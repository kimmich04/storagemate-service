"""Danh mục mặt hàng: dựng tên lưu DB từ catalog. CRUD / tìm theo alias: spec sau."""

from collections.abc import Iterable

from app.parser.catalog import CatalogItem


def db_names(catalog: Iterable[CatalogItem]) -> dict[str, str]:
    """code → tên lưu bảng items. DB bắt UNIQUE(tenant, lower(name)); catalog có tên trùng khác ĐVT
    (vd «Bột kem trứng» Gói/Túi) → món sau thêm «(ĐVT)», món sau nữa thêm cả mã."""
    names: dict[str, str] = {}
    used: set[str] = set()
    for item in catalog:
        name = item.name
        for candidate in (item.name, f"{item.name} ({item.base_unit})", f"{item.name} ({item.code})"):
            if candidate.lower() not in used:
                name = candidate
                break
        used.add(name.lower())
        names[item.code] = name
    return names
