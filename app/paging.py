"""Phân trang dùng chung cho các danh sách SQL thuần có cột `count(*) OVER() AS total`."""

from typing import Annotated

from fastapi import Query
from sqlalchemy import Row, TextClause
from sqlalchemy.orm import Session

MAX_PAGE = 100_000  # chặn offset khổng lồ; 100k trang × 200 dòng vẫn dư cho dữ liệu của một cửa hàng

PageQuery = Annotated[int, Query(ge=1, le=MAX_PAGE)]


def fetch_page(
    db: Session, stmt: TextClause, params: dict[str, object], total_col: int
) -> tuple[list[Row], int]:
    """Chạy câu truy vấn một trang và trả (các dòng, tổng số dòng của toàn bộ kết quả).

    `params` có `limit`/`offset`; `total_col` là vị trí cột `count(*) OVER()` trong SELECT.
    Trang vượt cuối cho ra 0 dòng nên không đọc được tổng từ chính nó: chạy lại trang đầu (1 dòng)
    để lấy tổng thật, tránh báo "0 kết quả" khi bộ lọc thu hẹp mà trang cũ còn giữ lại.
    """
    rows = db.execute(stmt, params).all()
    if rows:
        return rows, rows[0][total_col]
    if params["offset"] == 0:
        return rows, 0
    first = db.execute(stmt, params | {"limit": 1, "offset": 0}).first()
    return rows, first[total_col] if first else 0
