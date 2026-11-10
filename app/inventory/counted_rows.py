"""Điều kiện "dòng sổ được đếm lượt" của kho tổng, dùng chung cho Nhập Kho / Xuất Kho.

Khác `_COUNTED_ROWS` của dashboard/service.py (gắn chi nhánh) ở chỗ không sửa file đó; hai bản sẽ
hợp nhất khi làm lại Tổng quan. Bỏ: dòng hủy, dòng đã bị hủy, dòng cân bằng "Thực xuất T10…".
Dòng alias bảng là `l`. Tham số bind: :tenant, :loc, :tz, :balancing (xem `base_params`).
"""

from datetime import date

from app.inventory.dependencies import WarehouseScope

BALANCING_NOTE_PREFIX = "Thực xuất T10"

COUNTED_ROWS = """
    l.tenant_id = :tenant AND l.location_id = :loc
    AND l.reverses_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM inventory_log r WHERE r.reverses_id = l.id)
    AND coalesce(l.note, '') NOT LIKE :balancing
"""

# Ranh giới ngày theo múi giờ tenant, viết trên cột gốc để dùng được index (tenant_id, event_time)
FROM_START = "l.event_time >= (CAST(:from AS date)::timestamp AT TIME ZONE :tz)"
UPTO_END = "l.event_time < ((CAST(:to AS date) + 1)::timestamp AT TIME ZONE :tz)"


def base_params(scope: WarehouseScope, from_: date, to: date) -> dict[str, object]:
    return {
        "tenant": scope.tenant_id,
        "loc": scope.location.id,
        "tz": scope.timezone,
        "from": from_,
        "to": to,
        "balancing": f"{BALANCING_NOTE_PREFIX}%",
    }


def escape_like(q: str) -> str:
    """Escape ký tự đặc biệt của LIKE/ILIKE; dùng cùng ESCAPE '\\\\' trong câu SQL."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
