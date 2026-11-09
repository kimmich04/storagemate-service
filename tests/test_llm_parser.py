"""Tầng LLM: LlmPhieu → Phieu, và GeminiParser nuốt mọi lỗi thành "chưa hiểu" (không gọi Gemini thật)."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.parser.llm import GeminiParser, LlmLine, LlmPhieu, to_phieu
from app.parser.regex import NO_DATE_NOTE, UNKNOWN_LOC

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))  # thứ năm


def _parsed(**overrides: object) -> LlmPhieu:
    fields: dict = {
        "is_phieu": True,
        "action": "IN",
        "day": date(2026, 11, 4),
        "from_loc": None,
        "to_loc": "kho tong",
        "lines": [LlmLine(name=" Cà phê kem béo ", qty=10, unit=" Hộp ")],
    }
    return LlmPhieu(**{**fields, **overrides})


class FakeChain:
    def __init__(self, result: object = None, error: Exception | None = None, delay: float = 0) -> None:
        self.result, self.error, self.delay = result, error, delay
        self.messages: list = []

    async def ainvoke(self, messages: list) -> object:
        self.messages = messages
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def test_to_phieu_normalises_names_units_and_locations() -> None:
    phieu = to_phieu(_parsed(), NOW)

    assert phieu is not None
    assert (phieu.action, phieu.date, phieu.date_note) == ("IN", date(2026, 11, 4), None)
    assert (phieu.from_loc, phieu.to_loc) == (UNKNOWN_LOC, "kho tổng")
    line = phieu.lines[0]
    assert (line.name, line.qty, line.unit) == ("Cà phê kem béo", Decimal("10"), "hộp")
    assert line.raw == "Cà phê kem béo: 10 hộp"


def test_to_phieu_without_date_uses_today_and_notes_it() -> None:
    phieu = to_phieu(_parsed(day=None), NOW)

    assert (phieu.date, phieu.date_note) == (NOW.date(), NO_DATE_NOTE)


def test_to_phieu_keeps_decimal_quantity_exact() -> None:
    phieu = to_phieu(_parsed(lines=[LlmLine(name="Đường", qty=0.1, unit="kg")]), NOW)

    assert phieu.lines[0].qty == Decimal("0.1")


@pytest.mark.parametrize(
    "overrides",
    [{"is_phieu": False}, {"action": None}, {"lines": []}],
    ids=["not_a_phieu", "no_action", "no_lines"],
)
def test_to_phieu_returns_none_when_llm_is_unsure(overrides: dict) -> None:
    assert to_phieu(_parsed(**overrides), NOW) is None


@pytest.mark.parametrize("qty", [0, -3, 10**9])
def test_llm_line_rejects_bad_quantity(qty: float) -> None:
    with pytest.raises(ValidationError):
        LlmLine(name="x", qty=qty)


@pytest.mark.anyio
async def test_parser_returns_phieu_and_sends_date_and_delimited_message() -> None:
    chain = FakeChain(result=_parsed())

    phieu = await GeminiParser(chain, timeout=5).parse("hôm qua nhập 10 hộp cafe", NOW)

    assert phieu is not None and phieu.lines[0].qty == Decimal("10")
    system, human = chain.messages
    assert "05/11/2026" in system.content and "thứ năm" in system.content
    assert human.content == "<tin_nhan>\nhôm qua nhập 10 hộp cafe\n</tin_nhan>"


@pytest.mark.anyio
async def test_parser_accepts_dict_result() -> None:
    chain = FakeChain(result=_parsed().model_dump(mode="json"))

    assert await GeminiParser(chain, timeout=5).parse("x", NOW) is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "chain",
    [
        FakeChain(error=RuntimeError("quota 429")),
        FakeChain(result=None),
        FakeChain(result={"is_phieu": True, "action": "SELL", "lines": []}),
        FakeChain(result=_parsed(is_phieu=False)),
        FakeChain(result=_parsed(), delay=1),
    ],
    ids=["network_error", "empty_result", "schema_violation", "not_a_phieu", "timeout"],
)
async def test_parser_returns_none_on_any_failure(chain: FakeChain) -> None:
    assert await GeminiParser(chain, timeout=0.05).parse("x", NOW) is None
