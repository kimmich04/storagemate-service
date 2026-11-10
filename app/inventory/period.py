"""Kỳ báo cáo dùng chung cho 5 trang: THÁNG DƯƠNG + khoảng ngày trong tháng (plan mục 0, mục 8.0).

- `month=YYYY-MM`: mặc định tháng hiện tại; chọn được từ FIRST_MONTH đến tháng hiện tại.
- `from`, `to`: ngày BẤT KỲ trong tháng đã chọn, miễn from <= to và không quá hôm nay.
  Mặc định from = ngày 1, to = min(cuối tháng, hôm nay).
- "Hôm nay" tính theo múi giờ tenant (không còn dùng "ngày giao dịch mới nhất").
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Query
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory.dependencies import Scope, WarehouseScope
from app.inventory.exceptions import InvalidPeriodError
from app.schemas import CamelModel

# Tháng đầu tiên mà bộ lọc cho chọn (người dùng chốt 2026-11-09). Đổi ở đây nếu mốc thay đổi.
FIRST_MONTH = date(2026, 8, 1)

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def today_in(tz: str) -> date:
    """Ngày hôm nay theo múi giờ tenant. Test vá hàm này để cố định "hôm nay"."""
    return datetime.now(ZoneInfo(tz)).date()


@dataclass(frozen=True)
class Period:
    """Kỳ đã chuẩn hóa: from_ <= to nằm trong `month`, không quá `today`."""

    today: date
    month: str  # "YYYY-MM"
    from_: date
    to: date
    min_date: date  # ngày đầu tháng: biên dưới khi chọn ngày
    max_date: date  # min(cuối tháng, hôm nay): biên trên khi chọn ngày


class PeriodRead(CamelModel):
    """Khối `period` trong phản hồi của các API dữ liệu."""

    month: str
    from_: date = Field(alias="from")
    to: date


class MonthOptionRead(CamelModel):
    value: str  # "2026-10"
    label: str  # "Tháng 10/2026"
    has_data: bool


class PeriodOptionsRead(CamelModel):
    """[API-P0] Mọi thứ FE cần để vẽ bộ lọc tháng + khoảng ngày."""

    today: date
    month: str
    months: list[MonthOptionRead]
    from_: date = Field(alias="from")
    to: date
    min_date: date
    max_date: date


def _parse_month(value: str) -> date:
    return date(int(value[:4]), int(value[5:7]), 1)


def _check_day(name: str, day: date, period_min: date, period_max: date, today: date) -> None:
    if day > today:
        raise InvalidPeriodError(
            f"{name} {day:%d/%m/%Y} ở tương lai, chỉ chọn được đến hôm nay {today:%d/%m/%Y}"
        )
    if not period_min <= day <= period_max:
        raise InvalidPeriodError(f"{name} {day:%d/%m/%Y} phải nằm trong tháng {period_min:%m/%Y}")


def resolve_period(today: date, month: str | None, from_: date | None, to: date | None) -> Period:
    """Áp quy tắc mục 0; vi phạm → InvalidPeriodError (422). Không đụng DB nên test được trực tiếp."""
    current = today.replace(day=1)
    first = _parse_month(month) if month else current
    if first < FIRST_MONTH:
        raise InvalidPeriodError(f"Chỉ chọn được từ tháng {FIRST_MONTH:%m/%Y} trở đi")
    if first > current:
        raise InvalidPeriodError(f"Tháng {first:%m/%Y} ở tương lai, chỉ chọn được đến tháng {current:%m/%Y}")

    last_of_month = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    max_date = min(last_of_month, today)
    start = from_ if from_ is not None else first
    end = to if to is not None else max_date
    _check_day("Từ ngày", start, first, max_date, today)
    _check_day("Đến ngày", end, first, max_date, today)
    if start > end:
        raise InvalidPeriodError(f"Từ ngày {start:%d/%m/%Y} không được sau Đến ngày {end:%d/%m/%Y}")
    return Period(
        today=today,
        month=f"{first:%Y-%m}",
        from_=start,
        to=end,
        min_date=first,
        max_date=max_date,
    )


MonthParam = Annotated[
    str | None, Query(pattern=MONTH_PATTERN, description="YYYY-MM; bỏ trống = tháng hiện tại")
]
FromParam = Annotated[
    date | None,
    Query(alias="from", description="Từ ngày (trong tháng đã chọn); bỏ trống = ngày 1"),
]
ToParam = Annotated[
    date | None,
    Query(description="Đến ngày (trong tháng đã chọn); bỏ trống = min(cuối tháng, hôm nay)"),
]


def get_selected_period(
    scope: Scope, month: MonthParam = None, from_: FromParam = None, to: ToParam = None
) -> Period:
    """Dependency dùng chung: đọc month/from/to từ query và chuẩn hóa."""
    return resolve_period(today_in(scope.timezone), month, from_, to)


SelectedPeriod = Annotated[Period, Depends(get_selected_period)]


def to_read(period: Period) -> PeriodRead:
    return PeriodRead(month=period.month, from_=period.from_, to=period.to)


def _months_with_data(db: Session, scope: WarehouseScope) -> set[str]:
    """Tháng (từ FIRST_MONTH) có giao dịch ở kho tổng; không tính tồn đầu kỳ (opening) vì là số dư nạp vào."""
    rows = db.execute(
        text("""
            SELECT DISTINCT to_char((l.event_time AT TIME ZONE :tz)::date, 'YYYY-MM')
            FROM inventory_log l
            WHERE l.tenant_id = :tenant AND l.location_id = :loc AND l.parser_source <> 'opening'
              AND l.event_time >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
        """),
        {"tz": scope.timezone, "tenant": scope.tenant_id, "loc": scope.location.id, "start": FIRST_MONTH},
    ).all()
    return {r[0] for r in rows}


def period_options(db: Session, scope: WarehouseScope, period: Period) -> PeriodOptionsRead:
    """Danh sách tháng chọn được (FIRST_MONTH → tháng hiện tại, tăng dần) + kỳ đã chuẩn hóa."""
    with_data = _months_with_data(db, scope)
    months: list[MonthOptionRead] = []
    year, month = FIRST_MONTH.year, FIRST_MONTH.month
    while (year, month) <= (period.today.year, period.today.month):
        value = f"{year:04d}-{month:02d}"
        months.append(
            MonthOptionRead(value=value, label=f"Tháng {month}/{year}", has_data=value in with_data)
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return PeriodOptionsRead(
        today=period.today,
        month=period.month,
        months=months,
        from_=period.from_,
        to=period.to,
        min_date=period.min_date,
        max_date=period.max_date,
    )
