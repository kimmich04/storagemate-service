"""Lỗi nghiệp vụ của domain inventory."""

from app.exceptions import AppError


class InvalidPeriodError(AppError):
    """Tham số kỳ (month/from/to) vi phạm ràng buộc nghiệp vụ → 422 `{code, message}`."""

    status_code = 422
    code = "invalid_period"
