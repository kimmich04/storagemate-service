"""🖥️ /api/transactions — gom Nhập Kho và Xuất Kho.

`GET /api/transactions` dùng chung, chọn service theo `type`. Phản hồi IN và OUT khác hình dạng.
# TODO: POST /api/transactions/{id}/reverse  tạo bản ghi bù trừ (theo plan cũ)
"""

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Query

from app.database import DbSession
from app.inventory.dependencies import Scope
from app.inventory.period import SelectedPeriod, to_read
from app.inventory.transactions.inbound import service as inbound_service
from app.inventory.transactions.inbound.router import router as inbound_router
from app.inventory.transactions.inbound.schemas import InTransactionRead, InTransactionsRead
from app.inventory.transactions.outbound import service as outbound_service
from app.inventory.transactions.outbound.router import DestinationIds, UnknownDestination
from app.inventory.transactions.outbound.router import router as outbound_router
from app.inventory.transactions.outbound.schemas import OutTransactionRead, OutTransactionsRead
from app.paging import PageQuery

router = APIRouter(prefix="/transactions", tags=["transactions"])
router.include_router(inbound_router)  # /in/daily
router.include_router(outbound_router)  # /out/*


class TransactionType(StrEnum):
    IN = "IN"
    OUT = "OUT"


@router.get("")
def get_transactions(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    type: Annotated[TransactionType, Query(description="IN = nhập, OUT = xuất")],  # noqa: A002
    destination_ids: DestinationIds = None,
    unknown: UnknownDestination = None,
    q: Annotated[str | None, Query(description="Tìm theo tên hoặc Mã VT, không phân biệt hoa thường")] = None,
    page: PageQuery = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
) -> InTransactionsRead | OutTransactionsRead:
    """[API-I2] type=IN: bảng "Danh sách lượt nhập". [API-O6] type=OUT: bảng (E) "Danh sách lượt xuất".

    Mới nhất trước, có phân trang. `destinationId`/`unknownDestination` chỉ có nghĩa với type=OUT.
    """
    if type is TransactionType.OUT:
        out = outbound_service.out_transactions(
            db, scope, period, destination_ids, unknown, q=q, page=page, page_size=page_size
        )
        return OutTransactionsRead(
            period=to_read(period),
            total=out.total,
            page=page,
            page_size=page_size,
            items=[OutTransactionRead.model_validate(r, from_attributes=True) for r in out.rows],
        )
    result = inbound_service.in_transactions(db, scope, period, q=q, page=page, page_size=page_size)
    return InTransactionsRead(
        period=to_read(period),
        total=result.total,
        page=page,
        page_size=page_size,
        items=[InTransactionRead.model_validate(r, from_attributes=True) for r in result.rows],
    )
