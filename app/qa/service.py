"""Q&A agent cho manager: Gemini tự chọn tool chỉ đọc, đọc kết quả, lặp tới khi trả lời được.

Vòng lặp tự viết (không dùng langchain create_agent) để giới hạn lượt rõ ràng và test bằng model giả.
Mọi lỗi (Gemini, timeout, hết lượt, DB) → None: worker dùng lại câu "chưa hiểu" như tầng LLM parser.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.parser.llm import WEEKDAYS
from app.qa.prompts import SYSTEM_PROMPT
from app.qa.tools import TOOLS, ToolScope, list_locations, run_tool

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 2000  # giới hạn text của sendMessage


class QaResponder(Protocol):
    async def answer(
        self, question: str, *, tenant_id: int, staff_name: str, now: datetime
    ) -> str | None: ...


class QaAgent:
    """`model` = chat model đã bind_tools(TOOLS); `session_factory` = sessionmaker của login qa_reader."""

    def __init__(
        self, model: Any, session_factory: Callable[[], Session], *, max_steps: int, timeout: float
    ) -> None:
        self._model = model
        self._session_factory = session_factory
        self._max_steps = max_steps
        self._timeout = timeout

    async def answer(self, question: str, *, tenant_id: int, staff_name: str, now: datetime) -> str | None:
        scope = ToolScope(tenant_id=tenant_id, today=now.date(), session_factory=self._session_factory)
        called: list[str] = []
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout):
                reply = await self._loop(question, staff_name, now, scope, called)
        except Exception as error:  # biên với Gemini + DB: mọi lỗi = "chưa hiểu"
            # Chỉ log loại lỗi: thông điệp lỗi của SDK có thể chứa URL/khoá.
            logger.warning("Q&A không trả lời được (%s); tool đã gọi: %s", type(error).__name__, called)
            return None
        logger.info("Q&A: %d tool %s, %.1f giây", len(called), called, time.monotonic() - started)
        return reply

    async def _loop(
        self, question: str, staff_name: str, now: datetime, scope: ToolScope, called: list[str]
    ) -> str | None:
        messages: list[BaseMessage] = [
            SystemMessage(_system_prompt(staff_name, now, scope)),
            HumanMessage(f"<cau_hoi>\n{question}\n</cau_hoi>"),
        ]
        for _ in range(self._max_steps):
            ai: AIMessage = await self._model.ainvoke(messages)
            messages.append(ai)  # giữ nguyên tin của Gemini (kèm thought signature) cho lượt sau
            if not ai.tool_calls:
                return _final_text(ai.text)
            for call in ai.tool_calls:
                called.append(call["name"])
                result = run_tool(call["name"], call["args"], scope)
                messages.append(ToolMessage(result, tool_call_id=call["id"] or "", name=call["name"]))
        logger.warning("Q&A hết %d lượt mà chưa trả lời; tool đã gọi: %s", self._max_steps, called)
        return None


def _system_prompt(staff_name: str, now: datetime, scope: ToolScope) -> str:
    locations = "\n".join(f"- {loc['code']} — {loc['name']}" for loc in list_locations(scope))
    return SYSTEM_PROMPT.format(
        staff_name=staff_name,
        today=f"{now:%d/%m/%Y}",
        weekday=WEEKDAYS[now.weekday()],
        locations=locations or "(chưa có kho nào)",
    )


def _final_text(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    return text if len(text) <= MAX_REPLY_CHARS else text[: MAX_REPLY_CHARS - 1] + "…"


def build_agent(session_factory: Callable[[], Session]) -> QaAgent | None:
    """None khi chưa cấu hình GEMINI_API_KEY + LLM_MODEL → Q&A tắt."""
    if not settings.GEMINI_API_KEY or not settings.LLM_MODEL:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI  # nặng: chỉ nạp khi thật sự dùng

    chat = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        max_retries=0,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    return QaAgent(
        chat.bind_tools(list(TOOLS.values())),
        session_factory,
        max_steps=settings.QA_MAX_STEPS,
        timeout=settings.QA_TIMEOUT_SECONDS,
    )
