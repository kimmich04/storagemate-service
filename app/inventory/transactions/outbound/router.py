"""🖥️ Xuất Kho: /api/transactions/out/* (O1..O5). Danh sách O6 nằm ở transactions/router.py (dùng chung).

Tham số nơi nhận (O2..O6): `destinationId` (lặp được) và `unknownDestination`.
Không truyền cả hai → mọi nơi nhận (kể cả chưa rõ). FE bỏ chọn hết nơi nhận thì không gọi các API này.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.database import DbSession
from app.inventory.dependencies import Scope
from app.inventory.period import SelectedPeriod, to_read
from app.inventory.transactions.outbound import service
from app.inventory.transactions.outbound.schemas import (
    OutByDestinationRead,
    OutByDestinationRowRead,
    OutDailyRead,
    OutDayRead,
    OutDestinationOptionRead,
    OutDestinationsRead,
    OutSeriesRead,
    OutTopItemRead,
    OutTopItemsRead,
    OutTotalRead,
    OutUnknownCountRead,
    OutUnknownRowRead,
)

router = APIRouter(prefix="/out")

DestinationIds = Annotated[
    list[int] | None,
    Query(alias="destinationId", description="Lọc nơi nhận; lặp được (?destinationId=2&destinationId=4)"),
]
UnknownDestination = Annotated[
    bool | None,
    Query(alias="unknownDestination", description="true = gồm các lượt xuất chưa rõ nơi nhận"),
]


@router.get("/destinations")
def get_destinations(db: DbSession, scope: Scope, period: SelectedPeriod) -> OutDestinationsRead:
    """[API-O1] Dropdown "Nơi nhận": mọi nơi có lượt xuất trong kỳ, kèm số lượt."""
    result = service.out_destinations(db, scope, period)
    return OutDestinationsRead(
        period=to_read(period),
        destinations=[
            OutDestinationOptionRead(id=d.id, name=d.name, kind=d.kind, count=d.count)
            for d in result.destinations
        ],
        unknown=None if result.unknown_count is None else OutUnknownCountRead(count=result.unknown_count),
    )


@router.get("/total")
def get_total(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    destination_ids: DestinationIds = None,
    unknown: UnknownDestination = None,
) -> OutTotalRead:
    """[API-O2] Ô (A) "Tổng lượt xuất của Kho Tổng" theo các nơi nhận đang chọn."""
    return OutTotalRead(count=service.out_total(db, scope, period, destination_ids, unknown))


@router.get("/by-destination")
def get_by_destination(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    destination_ids: DestinationIds = None,
    unknown: UnknownDestination = None,
    limit: Annotated[
        int | None, Query(ge=1, le=100, description="Chỉ lấy n nơi nhận nhiều lượt nhất")
    ] = None,
) -> OutByDestinationRead:
    """[API-O3] Bảng (B) "Xuất theo nơi nhận"."""
    result = service.out_by_destination(db, scope, period, destination_ids, unknown, limit)
    return OutByDestinationRead(
        period=to_read(period),
        destinations=[
            OutByDestinationRowRead(
                id=d.id,
                name=d.name,
                kind=d.kind,
                count=d.count,
                item_count=d.item_count,
                last_date=d.last_date,
            )
            for d in result.destinations
        ],
        unknown=None
        if result.unknown is None
        else OutUnknownRowRead(
            count=result.unknown.count,
            item_count=result.unknown.item_count,
            last_date=result.unknown.last_date,
        ),
    )


@router.get("/daily")
def get_daily(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    destination_ids: DestinationIds = None,
    unknown: UnknownDestination = None,
) -> OutDailyRead:
    """[API-O4] Biểu đồ (C) "Xu hướng xuất theo ngày" (cột xếp chồng theo nơi nhận)."""
    result = service.out_daily(db, scope, period, destination_ids, unknown)
    return OutDailyRead(
        period=to_read(period),
        series=[OutSeriesRead(key=s.key, name=s.name, kind=s.kind) for s in result.series],
        days=[OutDayRead(date=d.date, total=d.total, counts=d.counts) for d in result.days],
    )


@router.get("/top-items")
def get_top_items(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    destination_ids: DestinationIds = None,
    unknown: UnknownDestination = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> OutTopItemsRead:
    """[API-O5] Khối (D) "Top mặt hàng được xuất", xếp theo số lượt xuất."""
    items = service.out_top_items(db, scope, period, destination_ids, unknown, limit)
    return OutTopItemsRead(
        period=to_read(period),
        items=[
            OutTopItemRead(
                item_id=i.item_id, code=i.code, name=i.name, unit=i.unit, count=i.count, qty_base=i.qty_base
            )
            for i in items
        ],
    )
