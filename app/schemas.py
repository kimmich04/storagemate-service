"""Base Pydantic dùng chung: response camelCase để khớp kiểu TypeScript của dashboard."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# Decimal (NUMERIC) trả ra JSON dạng số, không phải chuỗi, để FE tính toán trực tiếp
Number = Annotated[Decimal, PlainSerializer(float, return_type=float)]
