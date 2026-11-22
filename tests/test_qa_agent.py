"""Vòng lặp Q&A agent với chat model giả (không gọi Gemini); tool chạy thật trên DB test, vai qa_reader."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from sqlalchemy.orm import Session

from app.parser.normalize import fold
from app.qa.service import MAX_REPLY_CHARS, QaAgent
from tests.fakes import FakeChat

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))  # thứ năm


def _tool_call(tool: str, call_id: str = "c1", **args: object) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": call_id}])


def _agent(
    model: object, session_factory: Callable[[], Session], max_steps: int = 5, timeout: float = 5
) -> QaAgent:
    return QaAgent(model, session_factory, max_steps=max_steps, timeout=timeout)


async def _ask(agent: QaAgent, seeded: SimpleNamespace, question: str = "còn bao nhiêu trứng") -> str | None:
    return await agent.answer(question, tenant_id=seeded.tenant.id, staff_name="Hà", now=NOW)


async def test_calls_tool_then_answers_with_its_result(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    item = seeded.items["1"]
    first = _tool_call("FindItems", name=fold(item.name))
    chat = FakeChat(first, AIMessage(content="Kho tổng còn 0 hộp."))

    reply = await _ask(_agent(chat, qa_session_factory), seeded)

    assert reply == "Kho tổng còn 0 hộp."
    second_turn = chat.seen[1]
    assert second_turn[2] is first  # tin của Gemini được đưa lại nguyên vẹn (thought signature)
    tool_result = second_turn[3]
    assert isinstance(tool_result, ToolMessage) and tool_result.tool_call_id == "c1"
    assert f'"item_id": {item.id}' in tool_result.content


async def test_system_prompt_has_today_and_locations(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    chat = FakeChat(AIMessage(content="ok"))

    await _ask(_agent(chat, qa_session_factory), seeded, "tồn trứng")

    system, human = chat.seen[0]
    assert "05/11/2026" in system.content and "thứ năm" in system.content
    assert "- KT — Kho tổng SG" in system.content and "Hà" in system.content
    assert human.content == "<cau_hoi>\ntồn trứng\n</cau_hoi>"


async def test_runs_several_tool_calls_from_one_turn(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    both = AIMessage(
        content="",
        tool_calls=[
            {"name": "FindItems", "args": {"name": "trung"}, "id": "a"},
            {
                "name": "StaffActivity",
                "args": {"date_from": "2026-11-01", "date_to": "2026-11-05"},
                "id": "b",
            },
        ],
    )
    chat = FakeChat(both, AIMessage(content="xong"))

    await _ask(_agent(chat, qa_session_factory), seeded)

    assert [m.tool_call_id for m in chat.seen[1] if isinstance(m, ToolMessage)] == ["a", "b"]


async def test_bad_tool_args_are_sent_back_and_loop_continues(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    chat = FakeChat(_tool_call("GetStock", item_ids=[]), AIMessage(content="Bạn hỏi món nào?"))

    reply = await _ask(_agent(chat, qa_session_factory), seeded)

    assert reply == "Bạn hỏi món nào?"
    assert '"error"' in chat.seen[1][-1].content


async def test_gives_up_after_max_steps(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    chat = FakeChat(*(_tool_call("FindItems", f"c{i}", name="trung") for i in range(3)))

    assert await _ask(_agent(chat, qa_session_factory, max_steps=2), seeded) is None
    assert len(chat.seen) == 2


async def test_model_error_returns_none(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    chat = FakeChat(RuntimeError("quota 429"))

    assert await _ask(_agent(chat, qa_session_factory), seeded) is None


async def test_timeout_returns_none(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace
) -> None:
    class SlowChat:
        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            await asyncio.sleep(1)
            return AIMessage(content="muộn")

    assert await _ask(_agent(SlowChat(), qa_session_factory, timeout=0.05), seeded) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("  ", None),
        ("x" * (MAX_REPLY_CHARS + 50), "x" * (MAX_REPLY_CHARS - 1) + "…"),
        ([{"type": "text", "text": "Còn "}, {"type": "text", "text": "5 quả"}], "Còn 5 quả"),
    ],
    ids=["empty", "too_long", "content_parts"],
)
async def test_final_text_is_cleaned(
    qa_session_factory: Callable[[], Session], seeded: SimpleNamespace, content: object, expected: str | None
) -> None:
    chat = FakeChat(AIMessage(content=content))

    assert await _ask(_agent(chat, qa_session_factory), seeded) == expected
